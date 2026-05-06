"""Plugin management REST endpoints."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from androbugger.auth.middleware import get_current_user, require_role
from androbugger.plugins import loader as plugin_loader

router = APIRouter(prefix="/api/plugins", tags=["plugins"])


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
