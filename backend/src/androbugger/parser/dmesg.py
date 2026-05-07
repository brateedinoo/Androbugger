"""Kernel log (dmesg) parser."""
import re

from androbugger.parser.models import DmesgEntry, OOMKill, SELinuxDenial, ThermalEvent

_LINE_RE = re.compile(r"<(\d+)>\[\s*([\d.]+)\]\s*(.*)")
_THERMAL_RE = re.compile(
    r"thermal\w*:\s*(\S+)\s+(?:temperature|temp)[^:]*:\s*([\d.]+)",
    re.IGNORECASE,
)
_OOM_RE = re.compile(
    r"Killed process (\d+) \((.+?)\).*?score_adj (\d+).*?freed (\d+)kB",
    re.IGNORECASE,
)
_SELINUX_RE = re.compile(
    r"avc:\s+denied\s+\{(.+?)\}.*?scontext=(\S+).*?tcontext=(\S+).*?tclass=(\S+)",
    re.IGNORECASE,
)

_FACILITY_LEVELS = {
    "0": "emerg", "1": "alert", "2": "crit", "3": "err",
    "4": "warning", "5": "notice", "6": "info", "7": "debug",
}


def parse_dmesg(text: str) -> list[DmesgEntry]:
    entries = []
    for line in text.splitlines():
        if m := _LINE_RE.match(line):
            level_code = m.group(1)
            ts = float(m.group(2))
            msg = m.group(3)
            entries.append(DmesgEntry(
                timestamp_secs=ts,
                level=_FACILITY_LEVELS.get(level_code, level_code),
                facility="kernel",
                msg=msg,
            ))
    return entries


def extract_thermal_events(entries: list[DmesgEntry]) -> list[ThermalEvent]:
    events = []
    for e in entries:
        if "thermal" in e.msg.lower():
            if m := _THERMAL_RE.search(e.msg):
                events.append(ThermalEvent(
                    ts=e.timestamp_secs,
                    zone=m.group(1),
                    temp_c=float(m.group(2)),
                    action="throttle",
                ))
            elif "throttling" in e.msg.lower() or "cooling" in e.msg.lower():
                events.append(ThermalEvent(
                    ts=e.timestamp_secs,
                    zone="unknown",
                    temp_c=0.0,
                    action=e.msg[:100],
                ))
    return events


def extract_oom_kills(entries: list[DmesgEntry]) -> list[OOMKill]:
    kills = []
    for e in entries:
        if "killed process" in e.msg.lower():
            if m := _OOM_RE.search(e.msg):
                kills.append(OOMKill(
                    ts=e.timestamp_secs,
                    pid=int(m.group(1)),
                    process=m.group(2),
                    score_adj=int(m.group(3)),
                    pages_freed=int(m.group(4)) // 4,  # kB → pages (approx)
                ))
    return kills


def extract_selinux_denials(entries: list[DmesgEntry]) -> list[SELinuxDenial]:
    denials = []
    for e in entries:
        if m := _SELINUX_RE.search(e.msg):
            denials.append(SELinuxDenial(
                ts=e.timestamp_secs,
                scontext=m.group(2),
                tcontext=m.group(3),
                tclass=m.group(4),
                action=m.group(1).strip(),
            ))
    return denials
