"""Parsed data dataclasses for all bugreport sections."""
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class LogcatEntry:
    ts: str  # MM-DD HH:MM:SS.mmm
    pid: int
    tid: int
    level: str  # V D I W E F
    tag: str
    msg: str
    raw: str = ""
    line_number: int = 0


@dataclass
class ThreadDump:
    name: str
    state: str
    stack: list[str] = field(default_factory=list)


@dataclass
class ANRTrace:
    process: str
    pid: int
    reason: str
    timestamp: str
    main_thread_stack: list[str] = field(default_factory=list)
    other_threads: list[ThreadDump] = field(default_factory=list)


@dataclass
class FrameInfo:
    frame_num: int
    pc: str
    library: str
    function: str
    offset: str = ""


@dataclass
class Tombstone:
    process: str
    pid: int
    tid: int
    signal: str
    signal_name: str
    fault_addr: str
    registers: dict[str, str] = field(default_factory=dict)
    backtrace: list[FrameInfo] = field(default_factory=list)
    memory_map: list[str] = field(default_factory=list)
    open_files: list[str] = field(default_factory=list)
    timestamp: str = ""


@dataclass
class ProcessMemInfo:
    process: str
    pss_kb: int
    rss_kb: int


@dataclass
class MemInfo:
    total_ram_kb: int
    free_ram_kb: int
    used_ram_kb: int
    per_process: list[ProcessMemInfo] = field(default_factory=list)


@dataclass
class BatteryStats:
    screen_on_time_ms: int
    top_consumers: list[dict] = field(default_factory=list)
    wake_locks: list[dict] = field(default_factory=list)


@dataclass
class ActivityInfo:
    running_activities: list[str] = field(default_factory=list)
    recent_tasks: list[str] = field(default_factory=list)
    crashed_processes: list[dict] = field(default_factory=list)


@dataclass
class GfxInfo:
    janky_frames_pct: float = 0.0
    per_activity: list[dict] = field(default_factory=list)


@dataclass
class DmesgEntry:
    timestamp_secs: float
    level: str
    facility: str
    msg: str


@dataclass
class ThermalEvent:
    ts: float
    zone: str
    temp_c: float
    action: str


@dataclass
class OOMKill:
    ts: float
    process: str
    pid: int
    score_adj: int
    pages_freed: int


@dataclass
class SELinuxDenial:
    ts: float
    scontext: str
    tcontext: str
    tclass: str
    action: str


@dataclass
class ParsedBugreport:
    logcat: list[LogcatEntry] = field(default_factory=list)
    anr_traces: list[ANRTrace] = field(default_factory=list)
    tombstones: list[Tombstone] = field(default_factory=list)
    meminfo: MemInfo | None = None
    battery_stats: BatteryStats | None = None
    activity_info: ActivityInfo | None = None
    gfx_info: GfxInfo | None = None
    dmesg: list[DmesgEntry] = field(default_factory=list)
    thermal_events: list[ThermalEvent] = field(default_factory=list)
    oom_kills: list[OOMKill] = field(default_factory=list)
    selinux_denials: list[SELinuxDenial] = field(default_factory=list)
    sections: dict[str, str] = field(default_factory=dict)
    device_uptime_seconds: int = 0


@dataclass
class CrashLoop:
    process: str
    crash_count: int
    time_window: str


@dataclass
class TopError:
    tag: str
    count: int
    level: str
    sample_msg: str


@dataclass
class DiagnosticSummary:
    top_errors: list[TopError] = field(default_factory=list)
    anr_events: list[ANRTrace] = field(default_factory=list)
    tombstones: list[Tombstone] = field(default_factory=list)
    oom_events: list[OOMKill] = field(default_factory=list)
    thermal_events: list[ThermalEvent] = field(default_factory=list)
    crash_loops: list[CrashLoop] = field(default_factory=list)
    selinux_denials: list[SELinuxDenial] = field(default_factory=list)
    device_uptime_seconds: int = 0
    low_memory_events_count: int = 0
    severity: Literal["critical", "warning", "info"] = "info"
