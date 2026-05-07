"""Parse raw hardware collector output into pass/warning/fail summaries."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal


@dataclass
class SubsystemStatus:
    name: str
    status: Literal["pass", "warning", "fail"]
    details: str
    anomalies: list[str] = field(default_factory=list)


@dataclass
class HardwareSummary:
    overall_status: Literal["pass", "warning", "fail"]
    subsystems: list[SubsystemStatus]
    checked_at: str


def parse_hardware_results(raw: dict[str, str]) -> HardwareSummary:
    subsystems = [
        _parse_sensors(raw.get("sensors", "")),
        _parse_display(raw.get("display", "")),
        _parse_touch(raw.get("touch", "")),
        _parse_storage(raw.get("storage", "")),
        _parse_network(raw.get("network", "")),
        _parse_usb(raw.get("usb", "")),
    ]

    if any(s.status == "fail" for s in subsystems):
        overall: Literal["pass", "warning", "fail"] = "fail"
    elif any(s.status == "warning" for s in subsystems):
        overall = "warning"
    else:
        overall = "pass"

    return HardwareSummary(
        overall_status=overall,
        subsystems=subsystems,
        checked_at=datetime.now(UTC).isoformat(),
    )


def _parse_sensors(raw: str) -> SubsystemStatus:
    anomalies: list[str] = []
    if not raw.strip():
        return SubsystemStatus("sensors", "fail", "No sensor data returned", ["No output from sensorservice"])

    lower = raw.lower()
    if "no sensor" in lower or "sensor list is empty" in lower:
        anomalies.append("Sensor list reported empty")
        return SubsystemStatus("sensors", "fail", "No sensors detected", anomalies)

    # Count sensor entries
    sensor_count = len(re.findall(r"^\s*\d+\s+\|", raw, re.MULTILINE))
    details = f"{sensor_count} sensor(s) registered" if sensor_count else "Sensor service responding"
    return SubsystemStatus("sensors", "pass", details, anomalies)


def _parse_display(raw: str) -> SubsystemStatus:
    anomalies: list[str] = []
    if not raw.strip():
        return SubsystemStatus("display", "fail", "No display data returned", ["Empty display dump"])

    # Extract resolution
    size_match = re.search(r"Physical size: (\d+x\d+)", raw)
    density_match = re.search(r"Physical density: (\d+)", raw)
    details_parts = []
    if size_match:
        details_parts.append(f"size={size_match.group(1)}")
    if density_match:
        details_parts.append(f"density={density_match.group(1)}dpi")

    if "mScreenState=OFF" in raw:
        anomalies.append("Screen is currently off")

    details = ", ".join(details_parts) if details_parts else "Display service responding"
    return SubsystemStatus("display", "pass", details, anomalies)


def _parse_touch(raw: str) -> SubsystemStatus:
    anomalies: list[str] = []
    if not raw.strip():
        return SubsystemStatus("touch", "fail", "No touch data returned", ["Empty getevent/input dump"])

    has_abs_mt = "ABS_MT" in raw or "BTN_TOUCH" in raw
    if not has_abs_mt:
        anomalies.append("No ABS_MT touch events detected")
        return SubsystemStatus("touch", "fail", "No multitouch events found", anomalies)

    # Count input devices
    device_count = len(re.findall(r"^add device", raw, re.MULTILINE))
    details = f"{device_count} input device(s) with touch support" if device_count else "Touch events present"
    return SubsystemStatus("touch", "pass", details, anomalies)


def _parse_storage(raw: str) -> SubsystemStatus:
    anomalies: list[str] = []
    if not raw.strip():
        return SubsystemStatus("storage", "fail", "No storage data returned", ["Empty df/diskstats output"])

    max_use_pct = 0
    partitions_checked: list[str] = []

    # Parse df output lines like: /dev/block/sda5  10G  9.5G  500M  95% /data
    for m in re.finditer(r"(\S+)\s+\S+\s+\S+\s+\S+\s+(\d+)%\s+(\S+)", raw):
        _device, pct_str, mount = m.group(1), m.group(2), m.group(3)
        pct = int(pct_str)
        if pct > max_use_pct:
            max_use_pct = pct
        if pct >= 85:
            partitions_checked.append(f"{mount} at {pct}%")

    details = f"Max partition usage: {max_use_pct}%"

    if max_use_pct >= 95:
        for p in partitions_checked:
            anomalies.append(f"Critical: {p}")
        return SubsystemStatus("storage", "fail", details, anomalies)

    if max_use_pct >= 85:
        for p in partitions_checked:
            anomalies.append(f"High usage: {p}")
        return SubsystemStatus("storage", "warning", details, anomalies)

    return SubsystemStatus("storage", "pass", details, anomalies)


def _parse_network(raw: str) -> SubsystemStatus:
    anomalies: list[str] = []
    if not raw.strip():
        return SubsystemStatus("network", "fail", "No network data returned", ["Empty connectivity dump"])

    if "100% packet loss" in raw:
        anomalies.append("Ping to 8.8.8.8 failed (100% packet loss)")
        return SubsystemStatus("network", "fail", "No internet connectivity", anomalies)

    # Extract ping RTT
    rtt_match = re.search(r"rtt min/avg/max/mdev = ([\d.]+)/([\d.]+)/([\d.]+)", raw)
    if rtt_match:
        avg_rtt = float(rtt_match.group(2))
        details = f"Ping avg RTT: {avg_rtt:.1f}ms"
        if avg_rtt > 500:
            anomalies.append(f"High latency: {avg_rtt:.0f}ms avg RTT")
            return SubsystemStatus("network", "warning", details, anomalies)
        return SubsystemStatus("network", "pass", details, anomalies)

    # No ping results but connectivity dump exists — could be no route
    if "CONNECTED" in raw or "connected" in raw.lower():
        return SubsystemStatus("network", "pass", "Network connected", anomalies)

    anomalies.append("Connectivity state unclear from dump")
    return SubsystemStatus("network", "warning", "Connectivity state unknown", anomalies)


def _parse_usb(raw: str) -> SubsystemStatus:
    anomalies: list[str] = []
    if not raw.strip():
        return SubsystemStatus("usb", "fail", "No USB data returned", ["Empty usb dump"])

    lower = raw.lower()
    if "configured" in lower:
        return SubsystemStatus("usb", "pass", "USB configured", anomalies)

    if "disconnected" in lower:
        anomalies.append("USB state: disconnected")
        return SubsystemStatus("usb", "fail", "USB disconnected", anomalies)

    # Extract USB function
    func_match = re.search(r"mCurrentFunctions=(\w+)", raw)
    details = f"USB function: {func_match.group(1)}" if func_match else "USB service responding"
    return SubsystemStatus("usb", "pass", details, anomalies)
