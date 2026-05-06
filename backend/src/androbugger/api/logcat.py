"""Live logcat WebSocket streaming endpoint."""
import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from androbugger.device import adb as adb_module
from androbugger.parser.logcat import parse_line

router = APIRouter(tags=["logcat"])


@router.websocket("/ws/logcat/{serial}")
async def ws_logcat(websocket: WebSocket, serial: str):
    await websocket.accept()
    stop_event = asyncio.Event()

    async def _recv_filters():
        """Handle client filter messages without blocking the log stream."""
        try:
            while not stop_event.is_set():
                _ = await websocket.receive_text()
        except WebSocketDisconnect:
            stop_event.set()

    asyncio.create_task(_recv_filters())

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
    except Exception:
        pass
    finally:
        stop_event.set()
