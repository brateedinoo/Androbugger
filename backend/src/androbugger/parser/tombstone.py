"""Native crash tombstone parser."""
import re
from androbugger.parser.models import Tombstone, FrameInfo

_PID_TID_RE = re.compile(r"pid:\s*(\d+),\s*tid:\s*(\d+),\s*name:\s*(.+?)\s*(?:>>>|$)")
_SIGNAL_RE = re.compile(r"signal\s+(\d+)\s+\((\w+)\),\s*code.*?fault addr\s+([\w]+)")
_REGISTER_RE = re.compile(r"^\s+([\w]+)\s+([\da-fA-F]+)", re.MULTILINE)
_FRAME_RE = re.compile(
    r"#(\d{2})\s+pc\s+([\da-fA-F]+)\s+(\S+?)(?:\s+\((.+?)(?:\+(\d+))?\))?$",
    re.MULTILINE,
)
_TIMESTAMP_RE = re.compile(r"Tombstone written to.*?(\d{4}-\d{2}-\d{2}.*)")


def parse_tombstone(text: str) -> Tombstone:
    process = ""
    pid = 0
    tid = 0
    signal = ""
    signal_name = ""
    fault_addr = ""
    timestamp = ""

    if m := _PID_TID_RE.search(text):
        pid = int(m.group(1))
        tid = int(m.group(2))
        process = m.group(3).strip()

    if m := _SIGNAL_RE.search(text):
        signal = m.group(1)
        signal_name = m.group(2)
        fault_addr = m.group(3)

    if m := _TIMESTAMP_RE.search(text):
        timestamp = m.group(1).strip()

    # Registers
    registers: dict[str, str] = {}
    in_regs = False
    for line in text.splitlines():
        if "registers:" in line.lower():
            in_regs = True
            continue
        if in_regs:
            if not line.strip():
                in_regs = False
                continue
            parts = line.split()
            for i in range(0, len(parts) - 1, 2):
                registers[parts[i]] = parts[i + 1]

    # Backtrace
    backtrace = []
    for m in _FRAME_RE.finditer(text):
        backtrace.append(
            FrameInfo(
                frame_num=int(m.group(1)),
                pc=m.group(2),
                library=m.group(3),
                function=m.group(4) or "",
                offset=m.group(5) or "",
            )
        )

    # Memory map (lines after "memory map:")
    memory_map: list[str] = []
    in_map = False
    for line in text.splitlines():
        if "memory map:" in line.lower():
            in_map = True
            continue
        if in_map:
            if line.strip():
                memory_map.append(line.strip())
            else:
                break

    # Open files
    open_files: list[str] = []
    in_files = False
    for line in text.splitlines():
        if "open files:" in line.lower():
            in_files = True
            continue
        if in_files:
            if line.strip():
                open_files.append(line.strip())
            else:
                break

    return Tombstone(
        process=process,
        pid=pid,
        tid=tid,
        signal=signal,
        signal_name=signal_name,
        fault_addr=fault_addr,
        registers=registers,
        backtrace=backtrace,
        memory_map=memory_map,
        open_files=open_files,
        timestamp=timestamp,
    )
