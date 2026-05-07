"""Logcat line parser — threadtime format."""
import re
from collections import defaultdict

from androbugger.parser.models import LogcatEntry

# MM-DD HH:MM:SS.mmm  PID  TID LEVEL TAG  : MSG
_LINE_RE = re.compile(
    r"^(\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\s+(\d+)\s+(\d+)\s+([VDIWEF])\s+([\S]+)\s*:\s(.*)$"
)
_LEVEL_ORDER = {"V": 0, "D": 1, "I": 2, "W": 3, "E": 4, "F": 5}


def parse_line(line: str, line_number: int = 0) -> LogcatEntry | None:
    m = _LINE_RE.match(line.rstrip())
    if not m:
        return None
    return LogcatEntry(
        ts=m.group(1),
        pid=int(m.group(2)),
        tid=int(m.group(3)),
        level=m.group(4),
        tag=m.group(5).strip(),
        msg=m.group(6),
        raw=line,
        line_number=line_number,
    )


def parse_buffer(text: str) -> list[LogcatEntry]:
    entries = []
    for i, line in enumerate(text.splitlines(), start=1):
        entry = parse_line(line, i)
        if entry:
            entries.append(entry)
    return entries


def filter_by_level(entries: list[LogcatEntry], min_level: str) -> list[LogcatEntry]:
    threshold = _LEVEL_ORDER.get(min_level.upper(), 0)
    return [e for e in entries if _LEVEL_ORDER.get(e.level, 0) >= threshold]


def group_by_tag(entries: list[LogcatEntry]) -> dict[str, list[LogcatEntry]]:
    result: dict[str, list[LogcatEntry]] = defaultdict(list)
    for e in entries:
        result[e.tag].append(e)
    return dict(result)


def error_frequency(entries: list[LogcatEntry]) -> list[dict]:
    """Return top error/warning entries sorted by frequency."""
    counts: dict[tuple[str, str], list[LogcatEntry]] = defaultdict(list)
    for e in filter_by_level(entries, "W"):
        counts[(e.tag, e.level)].append(e)
    results = [
        {"tag": tag, "level": level, "count": len(es), "sample_msg": es[0].msg}
        for (tag, level), es in counts.items()
    ]
    return sorted(results, key=lambda x: x["count"], reverse=True)
