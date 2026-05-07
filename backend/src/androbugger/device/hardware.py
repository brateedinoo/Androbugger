"""Hardware diagnostic collectors — 6 subsystems via asyncio.gather."""
from __future__ import annotations

import asyncio
import logging

from androbugger.device.adb import shell

logger = logging.getLogger(__name__)


async def collect_sensors(serial: str) -> str:
    try:
        return await shell(serial, ["dumpsys", "sensorservice"])
    except Exception as exc:
        logger.debug("sensors collect failed: %s", exc)
        return ""


async def collect_display(serial: str) -> str:
    try:
        display = await shell(serial, ["dumpsys", "display"])
        size = await shell(serial, ["wm", "size"])
        density = await shell(serial, ["wm", "density"])
        return f"{display}\n{size}\n{density}"
    except Exception as exc:
        logger.debug("display collect failed: %s", exc)
        return ""


async def collect_touch(serial: str) -> str:
    try:
        getevent = await shell(serial, ["getevent", "-i"])
        dumpsys_input = await shell(serial, ["dumpsys", "input"])
        return f"{getevent}\n{dumpsys_input}"
    except Exception as exc:
        logger.debug("touch collect failed: %s", exc)
        return ""


async def collect_storage(serial: str) -> str:
    try:
        df = await shell(serial, ["df", "-h"])
        diskstats = await shell(serial, ["dumpsys", "diskstats"])
        return f"{df}\n{diskstats}"
    except Exception as exc:
        logger.debug("storage collect failed: %s", exc)
        return ""


async def collect_network(serial: str) -> str:
    try:
        connectivity = await shell(serial, ["dumpsys", "connectivity"])
        ping = await shell(serial, ["ping", "-c", "3", "-W", "5", "8.8.8.8"])
        return f"{connectivity}\n{ping}"
    except Exception as exc:
        logger.debug("network collect failed: %s", exc)
        return ""


async def collect_usb(serial: str) -> str:
    try:
        return await shell(serial, ["dumpsys", "usb"])
    except Exception as exc:
        logger.debug("usb collect failed: %s", exc)
        return ""


async def run_hardware_check(serial: str) -> dict[str, str]:
    """Run all 6 collectors concurrently and return raw text per subsystem."""
    results = await asyncio.gather(
        collect_sensors(serial),
        collect_display(serial),
        collect_touch(serial),
        collect_storage(serial),
        collect_network(serial),
        collect_usb(serial),
        return_exceptions=False,
    )
    return {
        "sensors": results[0],
        "display": results[1],
        "touch": results[2],
        "storage": results[3],
        "network": results[4],
        "usb": results[5],
    }
