"""Admin REST endpoints: users, audit log, system stats."""
import csv
import io
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

from androbugger.auth.middleware import require_role
from androbugger.auth.users import create_user
from androbugger.config import settings
from androbugger.db.database import get_db

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ── Stats ──────────────────────────────────────────────────────────────────────

@router.get("/stats")
async def admin_stats(user: Annotated[dict, Depends(require_role("admin"))]):
    async with get_db() as db:
        users_row = await (await db.execute("SELECT COUNT(*) FROM users")).fetchone()
        sessions_row = await (await db.execute("SELECT COUNT(*) FROM diagnostic_sessions")).fetchone()
        resolved_row = await (await db.execute(
            "SELECT COUNT(*) FROM diagnostic_sessions WHERE status='resolved'"
        )).fetchone()
        audit_row = await (await db.execute("SELECT COUNT(*) FROM audit_log")).fetchone()
        recent_rows = await (await db.execute(
            """SELECT DATE(timestamp) as day, COUNT(*) as count
               FROM audit_log
               WHERE timestamp >= ?
               GROUP BY day ORDER BY day""",
            ((datetime.now(UTC) - timedelta(days=7)).isoformat(),),
        )).fetchall()
        providers_row = await (await db.execute(
            "SELECT provider_type, model_name, is_enabled FROM llm_providers"
        )).fetchall()

    return {
        "user_count": users_row[0],
        "session_count": sessions_row[0],
        "resolved_count": resolved_row[0],
        "audit_entry_count": audit_row[0],
        "activity_7d": [dict(r) for r in recent_rows],
        "llm_providers": [dict(r) for r in providers_row],
    }


# ── Users ──────────────────────────────────────────────────────────────────────

class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str = "technician"


class UpdateRoleRequest(BaseModel):
    role: str


_VALID_ROLES = {"technician", "qa_engineer", "developer", "admin"}


@router.get("/users")
async def list_users(user: Annotated[dict, Depends(require_role("admin"))]):
    async with get_db() as db:
        rows = await (await db.execute(
            "SELECT id, username, role, created_at, last_login, force_password_change FROM users ORDER BY created_at"
        )).fetchall()
    return {"users": [dict(r) for r in rows]}


@router.post("/users")
async def admin_create_user(
    body: CreateUserRequest,
    user: Annotated[dict, Depends(require_role("admin"))],
):
    if body.role not in _VALID_ROLES:
        raise HTTPException(status_code=422, detail=f"Invalid role: {body.role}")
    try:
        new_user = await create_user(body.username, body.password, body.role)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"user": new_user}


@router.patch("/users/{user_id}/role")
async def update_user_role(
    user_id: str,
    body: UpdateRoleRequest,
    user: Annotated[dict, Depends(require_role("admin"))],
):
    if body.role not in _VALID_ROLES:
        raise HTTPException(status_code=422, detail=f"Invalid role: {body.role}")
    if user_id == user["id"]:
        raise HTTPException(status_code=400, detail="Cannot change your own role")
    async with get_db() as db:
        result = await db.execute("UPDATE users SET role=? WHERE id=?", (body.role, user_id))
        await db.commit()
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True}


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    user: Annotated[dict, Depends(require_role("admin"))],
):
    if user_id == user["id"]:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    async with get_db() as db:
        result = await db.execute("DELETE FROM users WHERE id=?", (user_id,))
        await db.commit()
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True}


# ── Audit log ──────────────────────────────────────────────────────────────────

@router.get("/audit")
async def list_audit(
    user: Annotated[dict, Depends(require_role("admin"))],
    action: str | None = None,
    severity: str | None = None,
    user_id: str | None = None,
    device_serial: str | None = None,
    days: int = 30,
    page: int = 1,
    per_page: int = 50,
):
    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    conditions = ["timestamp >= ?"]
    params: list = [cutoff]
    if action:
        conditions.append("action LIKE ?")
        params.append(f"%{action}%")
    if severity:
        conditions.append("severity=?")
        params.append(severity)
    if user_id:
        conditions.append("user_id=?")
        params.append(user_id)
    if device_serial:
        conditions.append("device_serial=?")
        params.append(device_serial)

    where = "WHERE " + " AND ".join(conditions)
    offset = (page - 1) * per_page

    async with get_db() as db:
        total_row = await (await db.execute(f"SELECT COUNT(*) FROM audit_log {where}", params)).fetchone()
        rows = await (await db.execute(
            f"SELECT * FROM audit_log {where} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            params + [per_page, offset],
        )).fetchall()

    return {
        "entries": [dict(r) for r in rows],
        "total": total_row[0],
        "page": page,
        "per_page": per_page,
    }


@router.get("/audit/export")
async def export_audit_csv(
    user: Annotated[dict, Depends(require_role("admin"))],
    days: int = 30,
):
    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    async with get_db() as db:
        rows = await (await db.execute(
            "SELECT * FROM audit_log WHERE timestamp >= ? ORDER BY timestamp DESC",
            (cutoff,),
        )).fetchall()

    buf = io.StringIO()
    if rows:
        writer = csv.DictWriter(buf, fieldnames=rows[0].keys())
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))

    return Response(
        content=buf.getvalue().encode(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="audit-{days}d.csv"'},
    )


@router.delete("/audit/prune")
async def prune_audit(user: Annotated[dict, Depends(require_role("admin"))]):
    """Delete audit entries older than the configured retention period."""
    cutoff = (datetime.now(UTC) - timedelta(days=settings.audit_retention_days)).isoformat()
    async with get_db() as db:
        result = await db.execute("DELETE FROM audit_log WHERE timestamp < ?", (cutoff,))
        await db.commit()
    return {"deleted": result.rowcount}


# ── LLM providers ──────────────────────────────────────────────────────────────

_CLOUD_MODELS: dict[str, list[str]] = {
    "anthropic": [
        "anthropic/claude-opus-4-7",
        "anthropic/claude-sonnet-4-6",
        "anthropic/claude-haiku-4-5-20251001",
    ],
    "openai": ["openai/gpt-4o", "openai/gpt-4o-mini", "openai/o1", "openai/o3-mini"],
}


async def _fetch_provider_models(provider_type: str, endpoint_url: str) -> dict:
    if provider_type in _CLOUD_MODELS:
        return {"models": _CLOUD_MODELS[provider_type]}
    if not endpoint_url:
        return {"models": [], "error": "No endpoint URL configured"}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{endpoint_url.rstrip('/')}/api/tags")
            resp.raise_for_status()
            data = resp.json()
            models = sorted(m["name"] for m in data.get("models", []))
            return {"models": models}
    except Exception as exc:
        return {"models": [], "error": f"Could not reach {endpoint_url}: {exc}"}


class UpdateProviderRequest(BaseModel):
    enabled: bool | None = None
    endpoint_url: str | None = None
    model_name: str | None = None
    max_tokens: int | None = None
    is_default: bool | None = None


class CreateProviderRequest(BaseModel):
    provider_type: str
    model_name: str
    endpoint_url: str | None = None
    is_local: bool = True
    max_tokens: int = 4096


async def _reload_provider_cache(db) -> None:
    from androbugger.llm import router as llm_router
    rows = await (await db.execute("SELECT * FROM llm_providers")).fetchall()
    llm_router.refresh_provider_cache([dict(r) for r in rows])


@router.get("/llm-providers")
async def list_llm_providers(user: Annotated[dict, Depends(require_role("admin"))]):
    async with get_db() as db:
        rows = await (await db.execute("SELECT * FROM llm_providers")).fetchall()
    return {"providers": [dict(r) for r in rows]}


@router.get("/llm-provider-models")
async def preview_provider_models(
    provider_type: str = Query(...),
    endpoint_url: str = Query(""),
    user: Annotated[dict, Depends(require_role("admin"))] = None,
):
    return await _fetch_provider_models(provider_type, endpoint_url)


@router.get("/llm-providers/{provider_id}/models")
async def get_provider_models(
    provider_id: str,
    endpoint_url_override: str | None = Query(None),
    user: Annotated[dict, Depends(require_role("admin"))] = None,
):
    async with get_db() as db:
        row = await (await db.execute(
            "SELECT * FROM llm_providers WHERE id=?", (provider_id,)
        )).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Provider not found")
    p = dict(row)
    endpoint_url = endpoint_url_override if endpoint_url_override is not None else (p.get("endpoint_url") or "")
    return await _fetch_provider_models(p["provider_type"], endpoint_url)


@router.post("/llm-providers")
async def create_llm_provider(
    body: CreateProviderRequest,
    user: Annotated[dict, Depends(require_role("admin"))],
):
    provider_id = str(uuid.uuid4())
    async with get_db() as db:
        await db.execute(
            """INSERT INTO llm_providers
               (id, provider_type, model_name, endpoint_url, is_local, is_default, is_enabled, priority, max_tokens)
               VALUES (?, ?, ?, ?, ?, FALSE, TRUE, 0, ?)""",
            (provider_id, body.provider_type, body.model_name, body.endpoint_url, body.is_local, body.max_tokens),
        )
        await db.commit()
        await _reload_provider_cache(db)
    return {"id": provider_id, "ok": True}


@router.patch("/llm-providers/{provider_id}")
async def update_llm_provider(
    provider_id: str,
    body: UpdateProviderRequest,
    user: Annotated[dict, Depends(require_role("admin"))],
):
    async with get_db() as db:
        row = await (await db.execute(
            "SELECT id FROM llm_providers WHERE id=?", (provider_id,)
        )).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Provider not found")

        updates: list[str] = []
        params: list = []

        if body.enabled is not None:
            updates.append("is_enabled=?")
            params.append(body.enabled)
        if body.endpoint_url is not None:
            updates.append("endpoint_url=?")
            params.append(body.endpoint_url)
        if body.model_name is not None:
            updates.append("model_name=?")
            params.append(body.model_name)
        if body.max_tokens is not None:
            updates.append("max_tokens=?")
            params.append(body.max_tokens)
        if body.is_default is True:
            await db.execute("UPDATE llm_providers SET is_default=FALSE")
            updates.append("is_default=?")
            params.append(True)

        if updates:
            params.append(provider_id)
            await db.execute(f"UPDATE llm_providers SET {', '.join(updates)} WHERE id=?", params)
        await db.commit()
        await _reload_provider_cache(db)
    return {"ok": True}


@router.delete("/llm-providers/{provider_id}")
async def delete_llm_provider(
    provider_id: str,
    user: Annotated[dict, Depends(require_role("admin"))],
):
    async with get_db() as db:
        count_row = await (await db.execute("SELECT COUNT(*) FROM llm_providers")).fetchone()
        if count_row[0] <= 1:
            raise HTTPException(status_code=400, detail="Cannot delete the only remaining provider")
        result = await db.execute("DELETE FROM llm_providers WHERE id=?", (provider_id,))
        await db.commit()
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Provider not found")
        await _reload_provider_cache(db)
    return {"ok": True}


# ── Fine-tuning ────────────────────────────────────────────────────────────────

@router.get("/finetune/stats")
async def finetune_stats(user: Annotated[dict, Depends(require_role("admin"))]):
    from androbugger.llm.finetune import get_finetune_stats
    return await get_finetune_stats()


class FinetuneExportRequest(BaseModel):
    output_path: str = "/tmp/androbugger-training.jsonl"
    min_quality: float = 0.0


@router.post("/finetune/export")
async def finetune_export(
    body: FinetuneExportRequest,
    user: Annotated[dict, Depends(require_role("admin"))],
):
    from androbugger.llm.finetune import export_training_data_for_user
    result = export_training_data_for_user(
        body.output_path,
        user_id=user["id"],
        min_quality=body.min_quality,
    )
    return {
        "record_count": result.record_count,
        "skipped_count": result.skipped_count,
        "path": result.path,
    }
