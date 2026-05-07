"""Dumpsys section parsers."""
import re

from androbugger.parser.models import ActivityInfo, BatteryStats, GfxInfo, MemInfo, ProcessMemInfo


def parse_meminfo(text: str) -> MemInfo:
    total_ram = 0
    free_ram = 0
    used_ram = 0
    per_process: list[ProcessMemInfo] = []

    for line in text.splitlines():
        line = line.strip()
        if m := re.match(r"Total RAM:\s*([\d,]+)k", line):
            total_ram = int(m.group(1).replace(",", ""))
        elif m := re.match(r"Free RAM:\s*([\d,]+)k", line):
            free_ram = int(m.group(1).replace(",", ""))
        elif m := re.match(r"Used RAM:\s*([\d,]+)k", line):
            used_ram = int(m.group(1).replace(",", ""))
        elif m := re.match(r"\s*([\d,]+)k:\s+(.+?)\s+\(pid", line):
            pss = int(m.group(1).replace(",", ""))
            proc = m.group(2).strip()
            per_process.append(ProcessMemInfo(process=proc, pss_kb=pss, rss_kb=0))

    return MemInfo(
        total_ram_kb=total_ram,
        free_ram_kb=free_ram,
        used_ram_kb=used_ram,
        per_process=per_process[:50],  # cap at 50 processes
    )


def parse_batterystats(text: str) -> BatteryStats:
    screen_on_ms = 0
    top_consumers: list[dict] = []
    wake_locks: list[dict] = []

    for line in text.splitlines():
        line = line.strip()
        if m := re.search(r"Screen on:\s*([\d,]+)ms", line):
            screen_on_ms = int(m.group(1).replace(",", ""))
        elif "wake_lock_in" in line.lower():
            parts = line.split()
            if len(parts) >= 4:
                wake_locks.append({"raw": line[:200]})
        elif m := re.match(r"Uid\s+(\w+)\s+\((.+?)\).*?(\d+\.\d+)%", line):
            top_consumers.append({
                "uid": m.group(1),
                "package": m.group(2),
                "drain_pct": float(m.group(3)),
            })

    return BatteryStats(
        screen_on_time_ms=screen_on_ms,
        top_consumers=top_consumers[:20],
        wake_locks=wake_locks[:20],
    )


def parse_activity(text: str) -> ActivityInfo:
    running_activities: list[str] = []
    recent_tasks: list[str] = []
    crashed_processes: list[dict] = []

    in_running = False
    in_tasks = False
    for line in text.splitlines():
        line_s = line.strip()
        if "Running activities" in line or "mResumedActivity" in line:
            in_running = True
            in_tasks = False
        elif "Recent tasks" in line or "mRecentTasks" in line:
            in_tasks = True
            in_running = False
        elif line_s == "" or line_s.startswith("---"):
            in_running = False
            in_tasks = False

        if in_running and "TaskRecord" in line_s:
            running_activities.append(line_s[:200])
        if in_tasks and "TaskRecord" in line_s:
            recent_tasks.append(line_s[:200])

        # Crash entries
        if m := re.search(r"Process\s+(\S+)\s+\(pid\s+(\d+)\).*crash", line, re.IGNORECASE):
            crashed_processes.append({"process": m.group(1), "pid": int(m.group(2))})

    return ActivityInfo(
        running_activities=running_activities[:20],
        recent_tasks=recent_tasks[:20],
        crashed_processes=crashed_processes[:20],
    )


def parse_gfxinfo(text: str) -> GfxInfo:
    janky_pct = 0.0
    per_activity: list[dict] = []
    current_activity = None

    for line in text.splitlines():
        line_s = line.strip()
        if m := re.match(r"Window:\s*(.+)", line_s):
            current_activity = m.group(1)
        elif m := re.search(r"Janky frames:\s*(\d+)\s*\((.+?)%\)", line_s):
            pct = float(m.group(2))
            if current_activity:
                per_activity.append({
                    "activity": current_activity,
                    "janky_frames_pct": pct,
                })
                if pct > janky_pct:
                    janky_pct = pct
            else:
                janky_pct = pct

    return GfxInfo(janky_frames_pct=janky_pct, per_activity=per_activity[:20])
