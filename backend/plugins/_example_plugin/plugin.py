"""
Example Androbugger plugin — detects repeated SIGSEGV crashes in libfoo.so.

Copy this directory as a starting point for new plugins.
All logic lives in the Plugin class below.
"""
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
    """Detects repeated SIGSEGV crashes in libfoo.so tombstones."""

    _TARGET_LIB = "libfoo.so"
    _TARGET_SIGNAL = "SIGSEGV"

    def diagnose(self, parsed_data: dict, context: dict) -> list[PluginDiagnosticResult]:
        tombstones = parsed_data.get("tombstones", [])
        matches = [
            t for t in tombstones
            if t.get("signal_name") == self._TARGET_SIGNAL
            and any(self._TARGET_LIB in (f.get("library", "")) for f in t.get("backtrace", []))
        ]

        if not matches:
            return [PluginDiagnosticResult(
                pattern_id="sigsegv_libfoo",
                detected=False,
                confidence="high",
                summary="No SIGSEGV crashes in libfoo.so detected",
                detail="",
            )]

        evidence = [
            {
                "section": "tombstone",
                "line_number": 0,
                "text": f"Process: {t.get('process')} | Signal: {t.get('signal_name')} | "
                        f"Frame: {next((f.get('library') for f in t.get('backtrace', []) if self._TARGET_LIB in f.get('library','')), '?')}",
            }
            for t in matches
        ]

        return [PluginDiagnosticResult(
            pattern_id="sigsegv_libfoo",
            detected=True,
            confidence="high" if len(matches) >= 2 else "medium",
            summary=f"SIGSEGV crash in {self._TARGET_LIB} detected ({len(matches)} tombstone(s))",
            detail=(
                f"Found {len(matches)} tombstone(s) with SIGSEGV in {self._TARGET_LIB}. "
                "This typically indicates a corrupted cache file or a firmware-specific bug. "
                "Clearing the libfoo cache directory often resolves the issue."
            ),
            evidence=evidence,
            suggested_fix_id="clear_libfoo_cache",
        )]

    def fix(self, device_serial: str, diagnosis: PluginDiagnosticResult, context: dict) -> Optional[FixResult]:
        if diagnosis.suggested_fix_id != "clear_libfoo_cache":
            return None
        adb = context.get("adb")
        if not adb:
            return FixResult(
                fix_id="clear_libfoo_cache",
                success=False,
                detail="No ADB access available",
            )
        try:
            output = adb.shell(["rm", "-rf", "/data/local/tmp/libfoo_cache"])
            return FixResult(
                fix_id="clear_libfoo_cache",
                success=True,
                detail=f"Cache cleared. Output: {output}",
                commands_executed=["rm -rf /data/local/tmp/libfoo_cache"],
                requires_reboot=False,
            )
        except Exception as exc:
            return FixResult(
                fix_id="clear_libfoo_cache",
                success=False,
                detail=str(exc),
            )
