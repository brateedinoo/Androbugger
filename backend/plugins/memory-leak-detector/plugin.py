"""Memory leak detector — flags processes with high PSS usage."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PluginDiagnosticResult:
    pattern_id: str
    detected: bool
    confidence: str
    summary: str
    detail: str
    evidence: list[dict] = field(default_factory=list)
    suggested_fix_id: Optional[str] = None


@dataclass
class FixResult:
    fix_id: str
    success: bool
    detail: str
    commands_executed: list[str] = field(default_factory=list)
    requires_reboot: bool = False


class Plugin:
    """Detects memory leaks by inspecting per-process PSS values."""

    _DEFAULT_THRESHOLD_MB = 300

    def diagnose(self, parsed_data: dict, context: dict) -> list[PluginDiagnosticResult]:
        manifest_meta = context.get("manifest_metadata", {})
        threshold_mb = manifest_meta.get("pss_threshold_mb", self._DEFAULT_THRESHOLD_MB)

        meminfo = parsed_data.get("meminfo", {})
        per_process = meminfo.get("per_process", {})

        if not per_process:
            return [PluginDiagnosticResult(
                pattern_id="memory_leak",
                detected=False,
                confidence="low",
                summary="No per-process meminfo data available",
                detail="parsed_data.meminfo.per_process is empty — bugreport may not include meminfo",
            )]

        suspects: list[dict] = []
        for proc_name, stats in per_process.items():
            pss_mb = 0
            if isinstance(stats, dict):
                pss_kb = stats.get("total_pss", stats.get("pss", 0))
                pss_mb = pss_kb / 1024
            elif isinstance(stats, (int, float)):
                pss_mb = stats / 1024

            if pss_mb >= threshold_mb:
                suspects.append({"process": proc_name, "pss_mb": round(pss_mb, 1)})

        if not suspects:
            return [PluginDiagnosticResult(
                pattern_id="memory_leak",
                detected=False,
                confidence="high",
                summary=f"No processes exceed {threshold_mb} MB PSS threshold",
                detail=f"All {len(per_process)} processes are within normal memory usage.",
            )]

        suspects.sort(key=lambda x: x["pss_mb"], reverse=True)
        evidence = [
            {"section": "meminfo", "line_number": 0,
             "text": f"{s['process']}: {s['pss_mb']} MB PSS"}
            for s in suspects
        ]
        top = suspects[0]

        return [PluginDiagnosticResult(
            pattern_id="memory_leak",
            detected=True,
            confidence="high" if len(suspects) >= 2 else "medium",
            summary=f"{len(suspects)} process(es) exceed {threshold_mb} MB PSS — possible memory leak",
            detail=(
                f"Processes with PSS ≥ {threshold_mb} MB: "
                + ", ".join(f"{s['process']} ({s['pss_mb']} MB)" for s in suspects[:5])
                + f". Highest: {top['process']} at {top['pss_mb']} MB. "
                "Consider restarting the affected process or profiling with Memory Profiler."
            ),
            evidence=evidence,
        )]

    def fix(self, device_serial: str, diagnosis: PluginDiagnosticResult, context: dict) -> Optional[FixResult]:
        return None  # Manual intervention required for memory leaks
