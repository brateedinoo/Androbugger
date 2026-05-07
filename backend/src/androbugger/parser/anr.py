"""ANR trace file parser."""
import re

from androbugger.parser.models import ANRTrace, ThreadDump

_HEADER_RE = re.compile(
    r"Subject:\s*(.*?)\s*\nDate:\s*(.+)",
    re.DOTALL,
)
_PROCESS_RE = re.compile(r"Cmd line:\s*(.+)")
_PID_RE = re.compile(r"pid:\s*(\d+)")
_REASON_RE = re.compile(r"(?:ANR in|Input dispatching timed out|reason:)\s*(.+)")
_THREAD_RE = re.compile(r'^"(.+?)"\s+.*?sysTid=(\d+)\s*(.*?)$', re.MULTILINE)
_FRAME_RE = re.compile(r"^\s+at\s+(.+)$", re.MULTILINE)


def parse_anr_file(text: str) -> ANRTrace:
    process = ""
    pid = 0
    reason = ""
    timestamp = ""

    if m := _PROCESS_RE.search(text):
        process = m.group(1).strip()
    if m := _PID_RE.search(text):
        pid = int(m.group(1))
    if m := _REASON_RE.search(text):
        reason = m.group(1).strip()
    if m := re.search(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", text):
        timestamp = m.group(1)

    # Split threads
    main_stack: list[str] = []
    other_threads: list[ThreadDump] = []

    # Look for "main" thread block
    blocks = re.split(r'\n(?=")', text)
    for block in blocks:
        name_m = re.match(r'"(.+?)"', block)
        if not name_m:
            continue
        name = name_m.group(1)
        state_m = re.search(r'state=(\w+)', block)
        state = state_m.group(1) if state_m else "?"
        frames = [line.strip() for line in block.splitlines() if line.strip().startswith("at ")]
        if name in ("main", process.split(":")[-1].strip()):
            main_stack = frames
        else:
            other_threads.append(ThreadDump(name=name, state=state, stack=frames))

    return ANRTrace(
        process=process,
        pid=pid,
        reason=reason,
        timestamp=timestamp,
        main_thread_stack=main_stack,
        other_threads=other_threads,
    )
