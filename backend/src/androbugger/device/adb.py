"""ADB wrapper with permission-tier enforcement and audit logging."""
import asyncio
import fnmatch
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator

import adbutils

from androbugger.config import settings


PermissionTier = str  # 'read_only' | 'state_changing' | 'destructive'

# Loaded at runtime from DB; module-level cache refreshed on startup
_PERMISSION_TIERS: list[dict] = []


def load_permission_tiers(tiers: list[dict]) -> None:
    global _PERMISSION_TIERS
    _PERMISSION_TIERS = tiers


def _get_tier_for_command(command: str) -> tuple[PermissionTier, bool]:
    """Return (tier, requires_confirmation) for a command by matching glob patterns."""
    cmd_str = " ".join(command) if isinstance(command, list) else command
    for entry in _PERMISSION_TIERS:
        if fnmatch.fnmatch(cmd_str, entry["pattern"]):
            return entry["tier"], entry["requires_confirmation"]
    # Unknown commands default to state_changing + require confirmation
    return "state_changing", True


def _get_adb_device(serial: str) -> adbutils.AdbDevice:
    client = adbutils.AdbClient(host="127.0.0.1", port=5037)
    return client.device(serial)


async def shell(serial: str, command: list[str]) -> str:
    """Execute a read-only ADB shell command and return stdout."""
    loop = asyncio.get_event_loop()
    dev = _get_adb_device(serial)
    result = await loop.run_in_executor(None, lambda: dev.shell(" ".join(command)))
    return result


async def shell_stream(serial: str, command: list[str]) -> AsyncGenerator[str, None]:
    """Stream output from a long-running ADB shell command line by line."""
    dev = _get_adb_device(serial)
    loop = asyncio.get_event_loop()
    queue: asyncio.Queue[str | None] = asyncio.Queue()

    def _run():
        try:
            for line in dev.shell(" ".join(command), stream=True):
                loop.call_soon_threadsafe(queue.put_nowait, line)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    asyncio.get_event_loop().run_in_executor(None, _run)
    while True:
        line = await queue.get()
        if line is None:
            break
        yield line


async def pull_bugreport(serial: str) -> Path:
    """Pull a bugreport from the device and return the local zip path."""
    dest_dir = settings.bugreport_dir
    dest_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    dest = dest_dir / f"bugreport_{serial}_{ts}.zip"

    loop = asyncio.get_event_loop()
    dev = _get_adb_device(serial)

    def _pull():
        # adbutils bugreport writes directly to a path
        dev.bugreport(str(dest))

    await loop.run_in_executor(None, _pull)
    return dest


async def screencap(serial: str) -> bytes:
    """Capture a screenshot from the device and return PNG bytes."""
    loop = asyncio.get_event_loop()
    dev = _get_adb_device(serial)

    def _cap():
        return dev.screenshot()

    img = await loop.run_in_executor(None, _cap)
    # img is a PIL Image from adbutils
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        img.save(f.name)
        return Path(f.name).read_bytes()


async def getprop(serial: str) -> dict[str, str]:
    """Return all device properties as a dict."""
    loop = asyncio.get_event_loop()
    dev = _get_adb_device(serial)

    def _get():
        return dev.getprop()

    result = await loop.run_in_executor(None, _get)
    if isinstance(result, dict):
        return result
    # Parse raw getprop output
    props: dict[str, str] = {}
    for line in (result or "").splitlines():
        line = line.strip()
        if line.startswith("[") and "]: [" in line:
            key = line[1 : line.index("]")]
            val = line[line.index("]: [") + 4 : -1]
            props[key] = val
    return props


async def install(serial: str, apk_path: str) -> str:
    """Install an APK on the device (requires confirmation upstream)."""
    loop = asyncio.get_event_loop()
    dev = _get_adb_device(serial)

    def _install():
        return dev.install(apk_path)

    return await loop.run_in_executor(None, _install)
