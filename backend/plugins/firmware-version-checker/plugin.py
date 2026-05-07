"""Firmware version checker — warns on end-of-life or unsupported firmware."""
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
    """Checks device firmware version against known EOL and minimum stable lists."""

    def diagnose(self, parsed_data: dict, context: dict) -> list[PluginDiagnosticResult]:
        props = parsed_data.get("props", {})
        firmware = (
            props.get("ro.build.version.incremental")
            or props.get("ro.build.display.id")
            or props.get("ro.build.id")
            or ""
        )

        manifest_meta = context.get("manifest_metadata", {})
        eol_versions: list[str] = manifest_meta.get("known_eol_versions", [])
        min_stable: str = manifest_meta.get("minimum_stable_version", "")

        if not firmware:
            return [PluginDiagnosticResult(
                pattern_id="eol_firmware",
                detected=False,
                confidence="low",
                summary="Could not determine firmware version from device props",
                detail="ro.build.version.incremental and ro.build.id not found in parsed data",
            )]

        evidence = [{"section": "props", "line_number": 0, "text": f"Firmware version: {firmware}"}]

        if firmware in eol_versions:
            return [PluginDiagnosticResult(
                pattern_id="eol_firmware",
                detected=True,
                confidence="high",
                summary=f"Device is running EOL firmware: {firmware}",
                detail=(
                    f"Firmware version '{firmware}' is in the known end-of-life list. "
                    "This version no longer receives security patches or bug fixes. "
                    f"Minimum recommended stable version: {min_stable or 'check with vendor'}."
                ),
                evidence=evidence,
            )]

        if min_stable and firmware < min_stable:
            return [PluginDiagnosticResult(
                pattern_id="eol_firmware",
                detected=True,
                confidence="medium",
                summary=f"Firmware {firmware} is below minimum stable version {min_stable}",
                detail=(
                    f"The device is running firmware '{firmware}' which is older than "
                    f"the minimum stable version '{min_stable}'. Known stability issues may apply."
                ),
                evidence=evidence,
            )]

        return [PluginDiagnosticResult(
            pattern_id="eol_firmware",
            detected=False,
            confidence="high",
            summary=f"Firmware {firmware} is current",
            detail=f"No EOL or stability concerns for version '{firmware}'.",
        )]

    def fix(self, device_serial: str, diagnosis: PluginDiagnosticResult, context: dict) -> Optional[FixResult]:
        return None  # No automated fix available for firmware upgrades
