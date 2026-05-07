"""Device discovery, connection pool, and status broadcasting."""
import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime

import adbutils

from androbugger.device import adb as adb_module
from androbugger.device.models import DeviceInfo

logger = logging.getLogger(__name__)

# Connected devices keyed by serial
_devices: dict[str, DeviceInfo] = {}
_status_callbacks: list[Callable[[dict], None]] = []


def add_status_callback(cb: Callable[[dict], None]) -> None:
    _status_callbacks.append(cb)


def remove_status_callback(cb: Callable[[dict], None]) -> None:
    _status_callbacks.discard(cb) if hasattr(_status_callbacks, "discard") else None
    try:
        _status_callbacks.remove(cb)
    except ValueError:
        pass


def _broadcast(event: dict) -> None:
    for cb in list(_status_callbacks):
        try:
            cb(event)
        except Exception:
            pass


def _get_client() -> adbutils.AdbClient:
    return adbutils.AdbClient(host="127.0.0.1", port=5037)


async def _enrich_device(serial: str, connection_type: str, ip: str | None = None) -> DeviceInfo:
    """Build a DeviceInfo by pulling props from the device."""
    try:
        props = await adb_module.getprop(serial)
    except Exception:
        props = {}

    return DeviceInfo(
        serial=serial,
        model=props.get("ro.product.model") or props.get("ro.product.name"),
        firmware_version=props.get("ro.build.version.incremental"),
        connection_type=connection_type,  # type: ignore[arg-type]
        ip_address=ip,
        android_version=props.get("ro.build.version.release"),
        build_fingerprint=props.get("ro.build.fingerprint"),
        connected_at=datetime.now(UTC),
        last_seen=datetime.now(UTC),
    )


async def discover_usb() -> list[str]:
    """Return serials of all USB-connected devices."""
    loop = asyncio.get_event_loop()
    client = _get_client()
    serials = await loop.run_in_executor(None, lambda: [d.serial for d in client.list()])
    return [s for s in serials if ":" not in s]  # exclude TCP devices


async def connect_tcp(ip: str, port: int = 5555) -> DeviceInfo:
    """Connect to a wireless ADB device and return DeviceInfo."""
    loop = asyncio.get_event_loop()
    client = _get_client()
    serial = f"{ip}:{port}"
    await loop.run_in_executor(None, lambda: client.connect(serial))
    info = await _enrich_device(serial, "tcp", ip)
    _devices[serial] = info
    _broadcast({"type": "connected", "device": info.to_dict()})
    return info


async def disconnect(serial: str) -> None:
    loop = asyncio.get_event_loop()
    client = _get_client()
    await loop.run_in_executor(None, lambda: client.disconnect(serial))
    if serial in _devices:
        info = _devices.pop(serial)
        _broadcast({"type": "disconnected", "device": info.to_dict()})


def list_connected() -> list[DeviceInfo]:
    return list(_devices.values())


def get_device(serial: str) -> DeviceInfo:
    if serial not in _devices:
        raise KeyError(f"Device {serial} not connected")
    return _devices[serial]


async def poll_devices() -> None:
    """Background task: poll connected devices, emit connect/disconnect events."""
    while True:
        try:
            loop = asyncio.get_event_loop()
            client = _get_client()
            current: list[adbutils.AdbDeviceInfo] = await loop.run_in_executor(
                None, client.list
            )
            current_serials = {d.serial for d in current}
            known_serials = set(_devices.keys())

            # New connections
            for d in current:
                if d.serial not in known_serials:
                    conn_type = "tcp" if ":" in d.serial else "usb"
                    ip = d.serial.split(":")[0] if conn_type == "tcp" else None
                    try:
                        info = await _enrich_device(d.serial, conn_type, ip)
                        _devices[d.serial] = info
                        _broadcast({"type": "connected", "device": info.to_dict()})
                        logger.info("Device connected: %s", d.serial)
                    except Exception as exc:
                        logger.warning("Could not enrich device %s: %s", d.serial, exc)

            # Disconnections
            for serial in known_serials - current_serials:
                info = _devices.pop(serial, None)
                if info:
                    _broadcast({"type": "disconnected", "device": info.to_dict()})
                    logger.info("Device disconnected: %s", serial)

            # Update last_seen
            for serial in current_serials & set(_devices.keys()):
                _devices[serial].last_seen = datetime.now(UTC)

        except Exception as exc:
            logger.warning("Device poll error: %s", exc)

        await asyncio.sleep(5.0)
