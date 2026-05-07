"""Crash pattern matcher — matches tombstone backtraces against configurable regex patterns."""
from __future__ import annotations
import re
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
    """Matches tombstone library names against a configurable list of known-bad patterns."""

    def diagnose(self, parsed_data: dict, context: dict) -> list[PluginDiagnosticResult]:
        manifest_meta = context.get("manifest_metadata", {})
        patterns: list[dict] = manifest_meta.get("patterns", [])

        tombstones = parsed_data.get("tombstones", [])
        if not tombstones:
            return [PluginDiagnosticResult(
                pattern_id="known_crash_pattern",
                detected=False,
                confidence="high",
                summary="No tombstones to analyse",
                detail="parsed_data.tombstones is empty",
            )]

        # Collect all library names from all tombstones
        all_libs: list[str] = []
        for t in tombstones:
            for frame in t.get("backtrace", []):
                lib = frame.get("library", "")
                if lib:
                    all_libs.append(lib)

        if not all_libs:
            return [PluginDiagnosticResult(
                pattern_id="known_crash_pattern",
                detected=False,
                confidence="medium",
                summary="Tombstones found but no library info in backtrace frames",
                detail="",
            )]

        matches: list[dict] = []
        for pattern_def in patterns:
            regex = pattern_def.get("regex", "")
            if not regex:
                continue
            try:
                compiled = re.compile(regex, re.IGNORECASE)
            except re.error:
                continue
            matching_libs = [lib for lib in all_libs if compiled.search(lib)]
            if matching_libs:
                matches.append({
                    "pattern_name": pattern_def.get("name", regex),
                    "known_fix": pattern_def.get("known_fix", "No fix information available"),
                    "matching_libs": list(set(matching_libs)),
                })

        if not matches:
            return [PluginDiagnosticResult(
                pattern_id="known_crash_pattern",
                detected=False,
                confidence="high",
                summary=f"No known crash patterns found in {len(all_libs)} backtrace frame(s)",
                detail="",
            )]

        evidence = [
            {
                "section": "tombstone",
                "line_number": 0,
                "text": f"{m['pattern_name']}: {', '.join(m['matching_libs'][:3])}",
            }
            for m in matches
        ]

        fix_lines = "\n".join(
            f"• {m['pattern_name']}: {m['known_fix']}" for m in matches
        )

        return [PluginDiagnosticResult(
            pattern_id="known_crash_pattern",
            detected=True,
            confidence="high",
            summary=f"{len(matches)} known crash pattern(s) matched in tombstone backtraces",
            detail=f"Matched patterns and known fixes:\n{fix_lines}",
            evidence=evidence,
        )]

    def fix(self, device_serial: str, diagnosis: PluginDiagnosticResult, context: dict) -> Optional[FixResult]:
        return None
