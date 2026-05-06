"""Device management REST endpoints and WebSocket status feed."""
import json
import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from androbugger.auth.middleware import get_current_user
from androbugger.db.audit import log as audit_log
from androbugger.device import manager

router = APIRouter(prefix="/api/devices", tags=["devices"])


class ConnectRequest(BaseModel):
    ip_address: str | None = None
    serial: str | None = None
    port: int = 5555


class DisconnectRequest(BaseModel):
    serial: str


@router.get("")
async def list_devices(user: Annotated[dict, Depends(get_current_user)]):
    devices = manager.list_connected()
    return {"devices": [d.to_dict() for d in devices]}


@router.post("/connect")
async def connect_device(body: ConnectRequest, user: Annotated[dict, Depends(get_current_user)]):
    if body.ip_address:
        try:
            device = await manager.connect_tcp(body.ip_address, body.port)
            await audit_log(
                "device_connect", "info",
                user_id=user["id"],
                device_serial=device.serial,
                detail={"type": "tcp", "ip": body.ip_address},
            )
            return {"device": device.to_dict()}
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    else:
        # USB devices are auto-discovered; just return current list
        devices = manager.list_connected()
        return {"devices": [d.to_dict() for d in devices]}


@router.post("/disconnect")
async def disconnect_device(body: DisconnectRequest, user: Annotated[dict, Depends(get_current_user)]):
    await manager.disconnect(body.serial)
    await audit_log("device_disconnect", "info", user_id=user["id"], device_serial=body.serial)
    return {"ok": True}


@router.get("/{serial}/info")
async def device_info(serial: str, user: Annotated[dict, Depends(get_current_user)]):
    try:
        device = manager.get_device(serial)
        return {"device": device.to_dict()}
    except KeyError:
        raise HTTPException(status_code=404, detail="Device not found")


# WebSocket: real-time device connect/disconnect events
_ws_clients: list[WebSocket] = []


def broadcast_device_event(event: dict) -> None:
    """Called by manager's status callback to push events to all WS clients."""
    payload = json.dumps(event)
    for ws in list(_ws_clients):
        try:
            asyncio.get_event_loop().create_task(ws.send_text(payload))
        except Exception:
            pass


@router.websocket("/ws/devices")
async def ws_devices(websocket: WebSocket):
    await websocket.accept()
    _ws_clients.append(websocket)
    # Send current device list on connect
    devices = manager.list_connected()
    await websocket.send_text(json.dumps({"type": "init", "devices": [d.to_dict() for d in devices]}))
    try:
        while True:
            await websocket.receive_text()  # keep alive
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in _ws_clients:
            _ws_clients.remove(websocket)
