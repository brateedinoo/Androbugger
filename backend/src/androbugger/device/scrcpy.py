"""Screencap-based screen mirroring — one polling loop per device serial."""
from __future__ import annotations

import asyncio
import io
import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)

# Module-level registry: one manager per serial
_managers: dict[str, "ScrcpyManager"] = {}
_managers_lock = asyncio.Lock()


def _png_to_jpeg(png_bytes: bytes, quality: int = 75) -> bytes:
    """Convert PNG bytes to JPEG bytes using Pillow."""
    from PIL import Image
    img = Image.open(io.BytesIO(png_bytes))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


class ScrcpyManager:
    """Polls screencap for one device and fans out JPEG frames to subscribers."""

    def __init__(self, serial: str, fps: int = 2, quality: int = 75) -> None:
        self.serial = serial
        self.fps = max(1, min(fps, 5))
        self.quality = max(20, min(quality, 90))
        self._callbacks: list[Callable[[bytes], None]] = []
        self._task: asyncio.Task | None = None
        self._running = False

    async def start_polling(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._poll_loop(), name=f"scrcpy-{self.serial}")

    def add_frame_callback(self, cb: Callable[[bytes], None]) -> None:
        if cb not in self._callbacks:
            self._callbacks.append(cb)

    def remove_frame_callback(self, cb: Callable[[bytes], None]) -> None:
        if cb in self._callbacks:
            self._callbacks.remove(cb)

    def subscriber_count(self) -> int:
        return len(self._callbacks)

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _poll_loop(self) -> None:
        from androbugger.device.adb import screencap
        interval = 1.0 / self.fps
        while self._running:
            try:
                png = await screencap(self.serial)
                if png:
                    jpeg = await asyncio.get_event_loop().run_in_executor(
                        None, _png_to_jpeg, png, self.quality
                    )
                    for cb in list(self._callbacks):
                        try:
                            cb(jpeg)
                        except Exception:
                            pass
            except Exception as exc:
                logger.debug("screencap error for %s: %s", self.serial, exc)
            await asyncio.sleep(interval)


async def get_or_create_manager(serial: str, fps: int = 2, quality: int = 75) -> ScrcpyManager:
    async with _managers_lock:
        if serial not in _managers:
            mgr = ScrcpyManager(serial, fps=fps, quality=quality)
            _managers[serial] = mgr
            await mgr.start_polling()
        return _managers[serial]


async def release_manager(serial: str, cb: Callable[[bytes], None]) -> None:
    async with _managers_lock:
        mgr = _managers.get(serial)
        if mgr is None:
            return
        mgr.remove_frame_callback(cb)
        if mgr.subscriber_count() == 0:
            await mgr.stop()
            del _managers[serial]
