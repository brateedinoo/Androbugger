"""Live logcat WebSocket streaming endpoint."""
import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from androbugger.auth.middleware import decode_access_token
from androbugger.auth.roles import role_gte
from androbugger.device import adb as adb_module
from androbugger.device import manager
from androbugger.parser.logcat import parse_line

router = APIRouter(tags=["logcat"])
logger = logging.getLogger(__name__)


async def _send_error(websocket: WebSocket, message: str) -> None:
    """Best-effort: send a structured error before closing. Never raises."""
    try:
        await websocket.send_text(json.dumps({"error": message}))
    except Exception:
        pass


@router.websocket("/ws/logcat/{serial}")
async def ws_logcat(websocket: WebSocket, serial: str):
    # Auth via ?token=... query param (browsers can't set headers on WebSocket).
    token = websocket.query_params.get("token", "")
    user = decode_access_token(token)
    if user is None or not role_gte(user["role"], "technician"):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Unauthorized")
        return

    await websocket.accept()

    # Pre-flight: surface a clear error if the device isn't known to the manager
    # so users don't see a misleading raw adb error.
    try:
        manager.get_device(serial)
    except KeyError:
        await _send_error(websocket, f"Device {serial} is not connected")
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        return

    # Tell the client the stream is ready — distinguishes "WS open but no data yet"
    # from "WS failed silently".
    try:
        await websocket.send_text(json.dumps({"status": "connected"}))
    except WebSocketDisconnect:
        return

    stop_event = asyncio.Event()

    async def _recv_filters() -> None:
        """Drain inbound messages and detect client disconnect."""
        try:
            while not stop_event.is_set():
                _ = await websocket.receive_text()
        except WebSocketDisconnect:
            stop_event.set()
        except Exception:
            stop_event.set()

    recv_task = asyncio.create_task(_recv_filters())

    line_number = 0
    try:
        async for raw_line in adb_module.shell_stream(serial, ["logcat", "-v", "threadtime"]):
            if stop_event.is_set():
                break
            line_number += 1
            entry = parse_line(raw_line, line_number)
            if entry:
                payload = {
                    "ts": entry.ts,
                    "pid": entry.pid,
                    "tid": entry.tid,
                    "level": entry.level,
                    "tag": entry.tag,
                    "msg": entry.msg,
                    "raw": entry.raw,
                    "line_number": entry.line_number,
                }
            else:
                payload = {"raw": raw_line, "line_number": line_number}
            try:
                await websocket.send_text(json.dumps(payload))
            except WebSocketDisconnect:
                break
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.exception("logcat stream error for serial=%s", serial)
        await _send_error(websocket, str(exc))
    finally:
        stop_event.set()
        recv_task.cancel()
        try:
            await recv_task
        except (asyncio.CancelledError, Exception):
            pass
