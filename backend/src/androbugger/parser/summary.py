"""Deterministic diagnostic summary generator — no LLM involved."""
from collections import Counter

from androbugger.parser.models import (
    CrashLoop,
    DiagnosticSummary,
    ParsedBugreport,
    TopError,
)


def generate_summary(parsed: ParsedBugreport) -> DiagnosticSummary:
    # Top 10 error/warning tags by frequency
    counter: Counter = Counter()
    tag_level: dict[str, str] = {}
    tag_sample: dict[str, str] = {}
    for entry in parsed.logcat:
        if entry.level in ("E", "F", "W"):
            key = (entry.tag, entry.level)
            counter[key] += 1
            tag_level[entry.tag] = entry.level
            if entry.tag not in tag_sample:
                tag_sample[entry.tag] = entry.msg[:200]

    top_errors = [
        TopError(tag=tag, count=count, level=tag_level.get(tag, "?"), sample_msg=tag_sample.get(tag, ""))
        for (tag, _), count in counter.most_common(10)
    ]

    # ANR events (all, since we don't have timestamps to filter by 24h in parsed form)
    anr_events = parsed.anr_traces

    # Crash loops: same process crashing 3+ times
    crash_counter: Counter = Counter()
    for entry in parsed.logcat:
        if entry.level == "E" and "FATAL" in entry.msg.upper():
            if entry.tag == "AndroidRuntime":
                crash_counter[entry.tag + ":" + entry.pid.__str__()] += 1

    crash_loops = [
        CrashLoop(process=k, crash_count=v, time_window="bugreport window")
        for k, v in crash_counter.items()
        if v >= 3
    ]

    # Low memory events
    low_mem_count = sum(
        1 for e in parsed.logcat
        if "low memory" in e.msg.lower() or "lowmemorykiller" in e.tag.lower()
    )

    # Severity
    if parsed.tombstones or crash_loops:
        severity = "critical"
    elif parsed.anr_traces or parsed.oom_kills or parsed.thermal_events:
        severity = "warning"
    else:
        severity = "info"

    # Uptime
    uptime = parsed.device_uptime_seconds

    return DiagnosticSummary(
        top_errors=top_errors,
        anr_events=anr_events,
        tombstones=parsed.tombstones,
        oom_events=parsed.oom_kills,
        thermal_events=parsed.thermal_events,
        crash_loops=crash_loops,
        selinux_denials=parsed.selinux_denials[:20],
        device_uptime_seconds=uptime,
        low_memory_events_count=low_mem_count,
        severity=severity,
    )
