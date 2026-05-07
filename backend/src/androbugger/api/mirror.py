"""WebSocket screen mirroring endpoint — streams JPEG frames from screencap polling."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["mirror"])


@router.websocket("/ws/mirror/{serial}")
async def ws_mirror(serial: str, websocket: WebSocket) -> None:
    await websocket.accept()

    # Parse optional query params
    fps = int(websocket.query_params.get("fps", "2"))
    quality = int(websocket.query_params.get("quality", "75"))

    from androbugger.device.scrcpy import get_or_create_manager, release_manager

    # Use a queue to bridge the callback (sync) to the WS send (async)
    queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=4)

    def on_frame(jpeg: bytes) -> None:
        try:
            queue.put_nowait(jpeg)
        except asyncio.QueueFull:
            pass  # drop frame if client is slow

    mgr = await get_or_create_manager(serial, fps=fps, quality=quality)
    mgr.add_frame_callback(on_frame)

    try:
        while True:
            # Send the next frame as a binary message
            frame = await asyncio.wait_for(queue.get(), timeout=10.0)
            await websocket.send_bytes(frame)
    except (TimeoutError, WebSocketDisconnect):
        pass
    except Exception:
        pass
    finally:
        await release_manager(serial, on_frame)
