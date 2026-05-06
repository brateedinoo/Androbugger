"""Prompt templates for Android diagnostic analysis."""
import json
from dataclasses import asdict

from androbugger.parser.models import DiagnosticSummary


DIAGNOSTIC_SYSTEM_PROMPT = """\
You are an expert Android system engineer specializing in diagnosing failures in Android-based \
Interactive Flat Panel (IFP) displays. You analyze Android bugreports, crash logs, ANR traces, \
tombstones, and system service dumps to identify root causes.

When analyzing diagnostic data, you MUST:
1. Identify the root cause category — choose exactly one from:
   MEMORY_PRESSURE | PROCESS_CRASH | BINDER_DEADLOCK | THERMAL_THROTTLE |
   CONFIGURATION_ERROR | FIRMWARE_BUG | APP_CRASH | SELINUX_DENIAL | OTHER
2. Cite specific evidence from the logs. Format citations as:
   [section:line_number] or [section: "exact text from log"]
3. Declare a confidence level: LOW | MEDIUM | HIGH
4. Separate observations (what the data shows) from conclusions (what it means)
5. Recommend specific, actionable fix steps

Output format (strict markdown):
## Root Cause
[ONE sentence identifying the root cause]

**Category:** [CATEGORY]
**Confidence:** [LOW|MEDIUM|HIGH]

## Evidence
[Bullet list of cited log evidence with section references]

## Analysis
[2-5 paragraphs explaining what happened and why]

## Recommended Actions
[Numbered list of specific fix steps]

## Notes
[Optional: caveats, additional investigation needed, related patterns]
"""


def build_diagnostic_prompt(
    summary: DiagnosticSummary,
    parsed_sections: dict[str, str],
    knowledge_context: list[dict] | None = None,
    device_info: dict | None = None,
) -> list[dict]:
    """Assemble system + user messages for diagnostic analysis."""
    messages: list[dict] = [{"role": "system", "content": DIAGNOSTIC_SYSTEM_PROMPT}]

    parts: list[str] = []

    if device_info:
        parts.append(
            f"## Device Information\n"
            f"- Model: {device_info.get('model', 'Unknown')}\n"
            f"- Firmware: {device_info.get('firmware_version', 'Unknown')}\n"
            f"- Android: {device_info.get('android_version', 'Unknown')}\n"
        )

    # Deterministic summary
    parts.append("## Diagnostic Summary (Deterministic)\n")
    parts.append(f"**Severity:** {summary.severity.upper()}")
    parts.append(f"**Uptime:** {summary.device_uptime_seconds}s")
    parts.append(f"**Low Memory Events:** {summary.low_memory_events_count}")

    if summary.top_errors:
        parts.append("\n### Top Error Tags")
        for e in summary.top_errors[:10]:
            parts.append(f"- [{e.level}] {e.tag}: {e.count}× — {e.sample_msg[:100]}")

    if summary.tombstones:
        parts.append("\n### Crash Tombstones")
        for t in summary.tombstones[:5]:
            parts.append(
                f"- Process: {t.process} | Signal: {t.signal_name} ({t.signal}) "
                f"| Fault addr: {t.fault_addr}"
            )
            if t.backtrace:
                for frame in t.backtrace[:5]:
                    parts.append(f"  #{frame.frame_num:02d} {frame.library} {frame.function}")

    if summary.anr_events:
        parts.append("\n### ANR Events")
        for a in summary.anr_events[:3]:
            parts.append(f"- Process: {a.process} | Reason: {a.reason}")
            if a.main_thread_stack:
                parts.append("  Main thread (top 5 frames):")
                for frame in a.main_thread_stack[:5]:
                    parts.append(f"    {frame}")

    if summary.oom_events:
        parts.append("\n### OOM Kills")
        for o in summary.oom_events[:5]:
            parts.append(f"- {o.process} (pid {o.pid}), score_adj={o.score_adj}")

    if summary.thermal_events:
        parts.append("\n### Thermal Events")
        for t in summary.thermal_events[:5]:
            parts.append(f"- {t.zone}: {t.temp_c}°C — {t.action}")

    if summary.crash_loops:
        parts.append("\n### Crash Loops")
        for c in summary.crash_loops:
            parts.append(f"- {c.process}: {c.crash_count} crashes")

    if summary.selinux_denials:
        parts.append("\n### SELinux Denials (sample)")
        for s in summary.selinux_denials[:5]:
            parts.append(f"- {s.scontext} → {s.tcontext} [{s.tclass}]: {s.action}")

    # Key sections (trimmed for token budget)
    _TOKEN_BUDGET = 6000  # ~24K chars
    total_chars = sum(len(p) for p in parts)

    important_sections = [
        "SYSTEM LOG",
        "CRASH LOG",
        "ANR",
        "TOMBSTONE",
        "ACTIVITY MANAGER",
        "MEMORY INFO",
        "KERNEL LOG",
    ]
    for sec_name in important_sections:
        matching = [
            (k, v) for k, v in parsed_sections.items()
            if sec_name.lower() in k.lower()
        ]
        for k, v in matching[:1]:
            snippet = v[:2000]
            new_chars = len(snippet) + len(k) + 50
            if total_chars + new_chars < _TOKEN_BUDGET * 4:
                parts.append(f"\n### {k} (excerpt)\n```\n{snippet}\n```")
                total_chars += new_chars

    # Knowledge context (past cases)
    if knowledge_context:
        parts.append("\n## Relevant Past Cases")
        for case in knowledge_context[:3]:
            parts.append(
                f"\n**Case:** {case.get('title', 'Unknown')}\n"
                f"{case.get('content_snippet', '')[:300]}"
            )

    parts.append(
        "\n\nAnalyze the above diagnostic data. Identify the root cause, cite specific evidence, "
        "and provide actionable recommendations."
    )

    messages.append({"role": "user", "content": "\n".join(parts)})
    return messages


CHAT_SYSTEM_PROMPT = """\
You are an expert Android diagnostic assistant helping technicians diagnose issues with \
Android-based Interactive Flat Panel displays. You have access to the current diagnostic \
session data and can answer follow-up questions, explain log entries, and suggest \
investigation paths. Always cite specific log evidence when making claims. \
Be concise and actionable.
"""


def build_chat_prompt(
    summary_text: str,
    chat_history: list[dict],
    new_message: str,
    knowledge_context: list[dict] | None = None,
) -> list[dict]:
    messages: list[dict] = [{"role": "system", "content": CHAT_SYSTEM_PROMPT}]
    if summary_text:
        messages.append({
            "role": "user",
            "content": f"Current diagnostic session summary:\n\n{summary_text[:3000]}",
        })
        messages.append({"role": "assistant", "content": "I have reviewed the diagnostic data. How can I help?"})

    if knowledge_context:
        context_text = "\n".join(
            f"Past case: {c.get('title')}: {c.get('content_snippet', '')[:200]}"
            for c in knowledge_context[:3]
        )
        messages.append({"role": "user", "content": f"Related past cases:\n{context_text}"})
        messages.append({"role": "assistant", "content": "Noted the related cases."})

    # Add chat history (last 20 messages)
    for msg in chat_history[-20:]:
        messages.append({"role": msg["role"], "content": msg["content"]})

    messages.append({"role": "user", "content": new_message})
    return messages
