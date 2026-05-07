"""Plugin management REST endpoints."""
import asyncio
import json
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from androbugger.auth.middleware import get_current_user, require_role
from androbugger.config import settings
from androbugger.db.database import get_db
from androbugger.plugins import loader as plugin_loader

router = APIRouter(prefix="/api/plugins", tags=["plugins"])

# 5-minute module-level cache for marketplace results
_marketplace_cache: dict = {"ts": 0.0, "data": None}
_MARKETPLACE_TTL = 300  # seconds


@router.get("")
async def list_plugins(user: Annotated[dict, Depends(get_current_user)]):
    registry = plugin_loader.get_registry()
    return {"plugins": [lp.to_dict() for lp in registry.values()]}


@router.post("/{plugin_id}/enable")
async def enable_plugin(
    plugin_id: str,
    user: Annotated[dict, Depends(require_role("admin"))],
):
    if not plugin_loader.enable_plugin(plugin_id):
        raise HTTPException(status_code=404, detail="Plugin not found or has no loaded instance")
    return {"ok": True, "status": "enabled"}


@router.post("/{plugin_id}/disable")
async def disable_plugin(
    plugin_id: str,
    user: Annotated[dict, Depends(require_role("admin"))],
):
    if not plugin_loader.disable_plugin(plugin_id):
        raise HTTPException(status_code=404, detail="Plugin not found")
    return {"ok": True, "status": "disabled"}


@router.post("/{plugin_id}/reload")
async def reload_plugin(
    plugin_id: str,
    user: Annotated[dict, Depends(require_role("admin"))],
):
    if not plugin_loader.reload_plugin(plugin_id):
        raise HTTPException(status_code=404, detail="Plugin not found")
    lp = plugin_loader.get_plugin(plugin_id)
    return {"ok": True, "plugin": lp.to_dict() if lp else {}}


# ── Marketplace ────────────────────────────────────────────────────────────────

@router.get("/marketplace")
async def marketplace(user: Annotated[dict, Depends(require_role("developer"))]):
    """Search GitHub for androbugger-plugin repositories (cached 5 min)."""
    global _marketplace_cache

    now = time.monotonic()
    if _marketplace_cache["data"] is not None and (now - _marketplace_cache["ts"]) < _MARKETPLACE_TTL:
        return {"repos": _marketplace_cache["data"], "cached": True}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.github.com/search/repositories",
                params={"q": "topic:androbugger-plugin", "sort": "stars", "per_page": 20},
                headers={"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"},
            )
            resp.raise_for_status()
            items = resp.json().get("items", [])
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"GitHub API error: {exc}") from exc

    repos = [
        {
            "name": r["full_name"],
            "description": r.get("description") or "",
            "url": r["html_url"],
            "clone_url": r["clone_url"],
            "stars": r.get("stargazers_count", 0),
            "updated_at": r.get("updated_at", ""),
        }
        for r in items
    ]
    _marketplace_cache = {"ts": now, "data": repos}
    return {"repos": repos, "cached": False}


# ── Install ────────────────────────────────────────────────────────────────────

class InstallPluginRequest(BaseModel):
    github_url: str


@router.post("/install")
async def install_plugin(
    body: InstallPluginRequest,
    user: Annotated[dict, Depends(require_role("admin"))],
):
    """Clone a GitHub plugin repo, validate it, then move it to the plugin directory."""
    url = body.github_url.strip()
    if not url.startswith("https://github.com/"):
        raise HTTPException(status_code=422, detail="github_url must start with https://github.com/")

    # Run git clone in a thread pool to avoid blocking the event loop
    tmp = tempfile.mkdtemp(prefix="androbugger_plugin_install_")
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                ["git", "clone", "--depth=1", url, tmp],
                capture_output=True,
                text=True,
                timeout=30,
            ),
        )
        if result.returncode != 0:
            raise HTTPException(status_code=400, detail=f"git clone failed: {result.stderr[:300]}")

        cloned_path = Path(tmp)

        # Run validation in temp dir (registers into internal registry under tmp name)
        plugin_loader._load_plugin_dir(cloned_path)
        # Determine the plugin id from manifest.json
        import json
        manifest_file = cloned_path / "manifest.json"
        if not manifest_file.exists():
            raise HTTPException(status_code=400, detail="Plugin missing manifest.json")
        try:
            manifest_data = json.loads(manifest_file.read_text())
        except Exception:
            raise HTTPException(status_code=400, detail="Plugin manifest.json is not valid JSON")
        plugin_id = manifest_data.get("id") or cloned_path.name

        # Check validation result from registry
        lp = plugin_loader.get_plugin(plugin_id) or plugin_loader.get_plugin(cloned_path.name)
        if lp and lp.status == "failed":
            errs = "; ".join(lp.validation_errors or [lp.load_error or "unknown error"])
            raise HTTPException(status_code=400, detail=f"Plugin validation failed: {errs}")

        # Move validated plugin to plugin_dir
        dest = settings.plugin_dir / cloned_path.name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(tmp, str(dest))

        # Reload registry from the real plugin_dir so the plugin persists
        plugin_loader.load_all_plugins(settings.plugin_dir)
        lp_final = plugin_loader.get_plugin(plugin_id)

        return {
            "ok": True,
            "plugin_id": plugin_id,
            "name": manifest_data.get("name", plugin_id),
            "version": manifest_data.get("version", "?"),
            "status": lp_final.status if lp_final else "enabled",
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── Plugin versioning & runtime config ────────────────────────────────────────

@router.get("/{plugin_id}/config")
async def get_plugin_config(
    plugin_id: str,
    user: Annotated[dict, Depends(require_role("developer"))],
):
    """Return merged config: manifest metadata defaults + DB overrides."""
    lp = plugin_loader.get_plugin(plugin_id)
    if not lp:
        raise HTTPException(404, "Plugin not found")

    defaults: dict = {}
    manifest_path = Path(lp.manifest_path) if lp.manifest_path else None
    if manifest_path and manifest_path.exists():
        try:
            mdata = json.loads(manifest_path.read_text())
            defaults = mdata.get("metadata", {})
        except Exception:
            pass

    async with get_db() as db:
        row = await (await db.execute(
            "SELECT config_json FROM plugin_configs WHERE plugin_id=?", (plugin_id,)
        )).fetchone()

    overrides = json.loads(row["config_json"]) if row else {}
    merged = {**defaults, **overrides}
    return {"plugin_id": plugin_id, "config": merged, "defaults": defaults, "overrides": overrides}


class PluginConfigUpdate(BaseModel):
    config: dict


@router.put("/{plugin_id}/config")
async def update_plugin_config(
    plugin_id: str,
    body: PluginConfigUpdate,
    user: Annotated[dict, Depends(require_role("admin"))],
):
    lp = plugin_loader.get_plugin(plugin_id)
    if not lp:
        raise HTTPException(404, "Plugin not found")

    now = datetime.now(timezone.utc).isoformat()
    async with get_db() as db:
        await db.execute(
            "INSERT INTO plugin_configs (plugin_id, config_json, updated_by, updated_at)"
            " VALUES (?,?,?,?)"
            " ON CONFLICT(plugin_id) DO UPDATE SET config_json=excluded.config_json,"
            "   updated_by=excluded.updated_by, updated_at=excluded.updated_at",
            (plugin_id, json.dumps(body.config), user["id"], now),
        )
        await db.commit()

    # Reload plugin so new config takes effect
    if lp.manifest_path:
        plugin_loader._load_plugin_dir(Path(lp.manifest_path).parent)

    return {"ok": True}


@router.post("/{plugin_id}/update")
async def update_plugin(
    plugin_id: str,
    user: Annotated[dict, Depends(require_role("admin"))],
):
    """Pull latest from git and reload the plugin."""
    lp = plugin_loader.get_plugin(plugin_id)
    if not lp:
        raise HTTPException(404, "Plugin not found")

    plugin_dir = Path(lp.manifest_path).parent if lp.manifest_path else None
    if not plugin_dir or not (plugin_dir / ".git").exists():
        raise HTTPException(400, "Plugin directory is not a git repository")

    old_version: str = "unknown"
    try:
        mdata = json.loads((plugin_dir / "manifest.json").read_text())
        old_version = mdata.get("version", "unknown")
    except Exception:
        pass

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        lambda: subprocess.run(
            ["git", "pull"],
            cwd=str(plugin_dir),
            capture_output=True,
            text=True,
            timeout=30,
        ),
    )
    if result.returncode != 0:
        raise HTTPException(400, f"git pull failed: {result.stderr[:200]}")

    new_version: str = old_version
    try:
        mdata = json.loads((plugin_dir / "manifest.json").read_text())
        new_version = mdata.get("version", old_version)
    except Exception:
        pass

    plugin_loader._load_plugin_dir(plugin_dir)

    return {
        "ok": True,
        "plugin_id": plugin_id,
        "old_version": old_version,
        "new_version": new_version,
        "changed": old_version != new_version,
        "git_output": result.stdout.strip()[:200],
    }

