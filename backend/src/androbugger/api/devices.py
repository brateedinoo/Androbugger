"""Device management REST endpoints and WebSocket status feed."""
import json
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from androbugger.auth.middleware import get_current_user
from androbugger.db.audit import log as audit_log
from androbugger.db.database import get_db
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


@router.get("/health")
async def device_health(user: Annotated[dict, Depends(get_current_user)]):
    """Per-device health summary: last session, recent failure rate, outlier flag."""
    devices = manager.list_connected()
    serials = [d.serial for d in devices]
    if not serials:
        return {"health": {}}

    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    health: dict[str, dict] = {}

    async with get_db() as db:
        # Fleet-wide 7-day failure rate for outlier comparison
        fleet_row = await (await db.execute(
            """SELECT COUNT(*) as total,
                      SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) as failed
               FROM diagnostic_sessions WHERE started_at >= ?""",
            (cutoff,),
        )).fetchone()
        fleet_total = fleet_row["total"] or 1
        fleet_fail_rate = (fleet_row["failed"] or 0) / fleet_total

        for serial in serials:
            # Last session
            last_row = await (await db.execute(
                """SELECT id, status, started_at, completed_at, root_cause, device_model
                   FROM diagnostic_sessions WHERE device_serial=?
                   ORDER BY started_at DESC LIMIT 1""",
                (serial,),
            )).fetchone()

            # 7-day stats
            stats_row = await (await db.execute(
                """SELECT COUNT(*) as total,
                          SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) as failed,
                          SUM(CASE WHEN status='resolved' THEN 1 ELSE 0 END) as resolved
                   FROM diagnostic_sessions WHERE device_serial=? AND started_at >= ?""",
                (serial, cutoff),
            )).fetchone()

            total_7d = stats_row["total"] or 0
            fail_7d = stats_row["failed"] or 0
            device_fail_rate = fail_7d / total_7d if total_7d else 0
            is_outlier = total_7d > 2 and device_fail_rate > fleet_fail_rate * 1.5

            health[serial] = {
                "last_session": dict(last_row) if last_row else None,
                "sessions_7d": total_7d,
                "failures_7d": fail_7d,
                "resolved_7d": stats_row["resolved"] or 0,
                "fail_rate_7d": round(device_fail_rate, 3),
                "fleet_fail_rate": round(fleet_fail_rate, 3),
                "is_outlier": is_outlier,
            }

    return {"health": health}


@router.get("/{serial}/info")
async def device_info(serial: str, user: Annotated[dict, Depends(get_current_user)]):
    try:
        device = manager.get_device(serial)
        return {"device": device.to_dict()}
    except KeyError:
        raise HTTPException(status_code=404, detail="Device not found")


@router.post("/{serial}/hardware-check")
async def hardware_check(serial: str, user: Annotated[dict, Depends(get_current_user)]):
    import uuid
    import dataclasses
    from androbugger.device.hardware import run_hardware_check
    from androbugger.parser.hardware_summary import parse_hardware_results

    raw = await run_hardware_check(serial)
    summary = parse_hardware_results(raw)
    check_id = str(uuid.uuid4())

    import json
    results_payload = {
        "subsystems": [dataclasses.asdict(s) for s in summary.subsystems],
    }

    async with get_db() as db:
        await db.execute(
            """INSERT INTO hardware_checks (id, session_id, device_serial, checked_at, overall_status, results_json)
               VALUES (?, NULL, ?, ?, ?, ?)""",
            (check_id, serial, summary.checked_at, summary.overall_status,
             json.dumps(results_payload)),
        )
        await db.commit()

    await audit_log(
        action="hardware_check",
        severity="info",
        user_id=user["id"],
        device_serial=serial,
        detail={"check_id": check_id, "overall_status": summary.overall_status},
    )

    return {
        "check_id": check_id,
        "overall_status": summary.overall_status,
        "checked_at": summary.checked_at,
        "subsystems": [dataclasses.asdict(s) for s in summary.subsystems],
    }


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
