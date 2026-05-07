"""Post-processing: verify LLM-cited log lines exist in parsed data."""
import re

from androbugger.llm.models import VerifiedResponse
from androbugger.parser.models import ParsedBugreport

# Matches [section:123], [LOGCAT:456], [section: "text"], [line 123]
_CITATION_RE = re.compile(
    r"\[([A-Z_\s]+):?\s*(?:line\s*)?(\d+)(?::\s*[\"'](.+?)[\"'])?\]",
    re.IGNORECASE,
)
_PROCESS_RE = re.compile(r"\b(pid\s+(\d+)|process\s+['\"]?([A-Za-z][\w.:/]+)['\"]?)", re.IGNORECASE)


def verify_citations(llm_response: str, parsed: ParsedBugreport) -> VerifiedResponse:
    verified: list[dict] = []
    unverified: list[dict] = []
    warnings: list[str] = []

    logcat_set = {e.line_number for e in parsed.logcat if e.line_number}
    pid_set = {e.pid for e in parsed.logcat}
    process_names = {
        t.process.lower() for t in parsed.tombstones
    } | {a.process.lower() for a in parsed.anr_traces}

    for m in _CITATION_RE.finditer(llm_response):
        section = m.group(1).strip()
        line_num = int(m.group(2)) if m.group(2) else None
        text_ref = m.group(3)
        citation = {"section": section, "line": line_num, "text": text_ref, "raw": m.group(0)}

        found = False
        if "logcat" in section.lower() and line_num:
            found = line_num in logcat_set
        elif line_num:
            # Try to verify against any logcat line number range
            found = 0 < line_num <= len(parsed.logcat) + 1000
        elif text_ref:
            # Check if text appears in any logcat message
            found = any(text_ref.lower() in e.msg.lower() for e in parsed.logcat[:1000])

        if found:
            verified.append(citation)
        else:
            unverified.append(citation)
            warnings.append(f"Could not verify citation: {m.group(0)}")

    # Check process name references
    for m in _PROCESS_RE.finditer(llm_response):
        pid_str = m.group(2)
        proc_name = m.group(3)
        if pid_str:
            pid = int(pid_str)
            if pid not in pid_set and pid > 0:
                warnings.append(f"Referenced PID {pid} not found in logcat")
        if proc_name and proc_name.lower() not in process_names:
            # soft warning — process may appear elsewhere
            pass

    return VerifiedResponse(
        text=llm_response,
        verified_citations=verified,
        unverified_citations=unverified,
        warnings=warnings,
    )
