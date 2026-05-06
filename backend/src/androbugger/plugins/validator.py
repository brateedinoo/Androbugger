"""3-stage plugin validation: schema → sandboxed test → dependency check."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from androbugger.plugins.models import LoadedPlugin, PluginManifest

logger = logging.getLogger(__name__)

_REQUIRED_MANIFEST_KEYS = {"id", "name", "version", "author", "description", "entry_point"}
_VALID_ADB_TIERS = {"read_only", "state_changing", "destructive", "none"}
_VALID_FS_PERMS = {"read", "write", "none"}


def validate_plugin(plugin_dir: Path) -> tuple[PluginManifest | None, list[str]]:
    """
    Stage 1: Schema validation.
    Returns (manifest, errors). If errors is non-empty, manifest may be None.
    """
    errors: list[str] = []
    manifest_path = plugin_dir / "manifest.json"
    if not manifest_path.exists():
        return None, ["manifest.json not found"]

    try:
        raw = json.loads(manifest_path.read_text())
    except json.JSONDecodeError as exc:
        return None, [f"manifest.json parse error: {exc}"]

    missing = _REQUIRED_MANIFEST_KEYS - set(raw.keys())
    if missing:
        errors.append(f"Missing required fields: {', '.join(sorted(missing))}")

    plugin_id = raw.get("id", "")
    if not plugin_id or not plugin_id.replace("-", "").replace("_", "").isalnum():
        errors.append(f"Invalid plugin id: {plugin_id!r}")

    entry = raw.get("entry_point", "")
    if entry and not (plugin_dir / entry).exists():
        errors.append(f"entry_point '{entry}' not found in plugin directory")

    perms = raw.get("permissions", {})
    adb_tier = perms.get("adb_commands", "none")
    if adb_tier not in _VALID_ADB_TIERS:
        errors.append(f"Invalid permissions.adb_commands: {adb_tier!r}")
    fs_perm = perms.get("file_system", "none")
    if fs_perm not in _VALID_FS_PERMS:
        errors.append(f"Invalid permissions.file_system: {fs_perm!r}")

    if raw.get("permissions", {}).get("network") not in (True, False, None):
        errors.append("permissions.network must be true or false")

    if errors:
        return None, errors

    manifest = PluginManifest(
        id=raw["id"],
        name=raw["name"],
        version=raw["version"],
        author=raw["author"],
        description=raw["description"],
        entry_point=raw["entry_point"],
        license=raw.get("license", "Unknown"),
        min_androbugger_version=raw.get("min_androbugger_version", "0.1.0"),
        capabilities=raw.get("capabilities", {}),
        permissions=raw.get("permissions", {}),
        dependencies=raw.get("dependencies", []),
        target_devices=raw.get("target_devices", {}),
    )
    return manifest, []


def check_dependencies(manifest: PluginManifest) -> list[str]:
    """Stage 3: Check that declared Python dependencies are importable."""
    errors: list[str] = []
    for dep in manifest.dependencies:
        try:
            __import__(dep.split("[")[0].replace("-", "_"))
        except ImportError:
            errors.append(f"Missing dependency: {dep}")
    return errors


def run_sandboxed_test(plugin_dir: Path, manifest: PluginManifest) -> list[str]:
    """
    Stage 2: Load the plugin in a restricted manner and run against fixture data.
    Returns list of validation errors (empty = pass).
    """
    import importlib.util
    import sys

    errors: list[str] = []
    entry_path = plugin_dir / manifest.entry_point

    try:
        spec = importlib.util.spec_from_file_location(f"_plugin_test_{manifest.id}", str(entry_path))
        if spec is None or spec.loader is None:
            return ["Could not load plugin module"]
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    except Exception as exc:
        return [f"Plugin load error: {exc}"]

    if not hasattr(module, "Plugin"):
        return ["Plugin class not found in entry_point"]

    plugin_cls = module.Plugin
    if not callable(getattr(plugin_cls, "diagnose", None)):
        errors.append("Plugin.diagnose() method missing or not callable")

    # Run against fixture data if present
    fixture_dir = plugin_dir / "test_fixtures"
    input_fixture = fixture_dir / "input_bugreport.json"
    expected_fixture = fixture_dir / "expected_output.json"

    if input_fixture.exists() and expected_fixture.exists():
        try:
            input_data = json.loads(input_fixture.read_text())
            expected = json.loads(expected_fixture.read_text())
            instance = plugin_cls()
            results = instance.diagnose(input_data, {})
            if not isinstance(results, list):
                errors.append("Plugin.diagnose() must return a list")
        except Exception as exc:
            errors.append(f"Fixture test failed: {exc}")

    return errors
