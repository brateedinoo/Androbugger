"""Plugin directory watcher and registry."""
from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from threading import Lock

from androbugger.plugins.models import LoadedPlugin, PluginManifest, PluginStatus
from androbugger.plugins.validator import (
    check_dependencies,
    run_sandboxed_test,
    validate_plugin,
)

logger = logging.getLogger(__name__)

_registry: dict[str, LoadedPlugin] = {}
_lock = Lock()


def load_all_plugins(plugins_dir: Path) -> None:
    """Discover and validate all plugin directories."""
    if not plugins_dir.exists():
        logger.info("Plugins directory not found: %s", plugins_dir)
        return

    for entry in sorted(plugins_dir.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        _load_plugin_dir(entry)

    logger.info("Plugin registry: %d plugin(s) loaded", len(_registry))


def _load_plugin_dir(plugin_dir: Path) -> None:
    plugin_id = plugin_dir.name
    lp = LoadedPlugin(
        manifest=PluginManifest(
            id=plugin_id, name=plugin_id, version="?", author="?",
            description="", entry_point="plugin.py"
        ),
        plugin_dir=str(plugin_dir),
        status=PluginStatus.validating,
    )

    # Stage 1: schema validation
    manifest, schema_errors = validate_plugin(plugin_dir)
    if schema_errors or manifest is None:
        lp.validation_errors = schema_errors
        lp.status = PluginStatus.failed
        lp.load_error = "; ".join(schema_errors)
        with _lock:
            _registry[plugin_id] = lp
        logger.warning("Plugin '%s' failed schema validation: %s", plugin_id, schema_errors)
        return

    lp.manifest = manifest

    # Stage 2: sandboxed test against fixtures
    test_errors = run_sandboxed_test(plugin_dir, manifest)
    if test_errors:
        lp.validation_errors = test_errors
        lp.status = PluginStatus.failed
        lp.load_error = "; ".join(test_errors)
        with _lock:
            _registry[manifest.id] = lp
        logger.warning("Plugin '%s' failed fixture test: %s", manifest.id, test_errors)
        return

    # Stage 3: dependency check
    dep_errors = check_dependencies(manifest)
    if dep_errors:
        lp.validation_errors = dep_errors
        lp.status = PluginStatus.failed
        lp.load_error = "; ".join(dep_errors)
        with _lock:
            _registry[manifest.id] = lp
        logger.warning("Plugin '%s' failed dependency check: %s", manifest.id, dep_errors)
        return

    # Load the plugin instance
    entry_path = plugin_dir / manifest.entry_point
    try:
        spec = importlib.util.spec_from_file_location(f"_plugin_{manifest.id}", str(entry_path))
        if spec is None or spec.loader is None:
            raise ImportError("Could not create module spec")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        instance = module.Plugin()
    except Exception as exc:
        lp.status = PluginStatus.failed
        lp.load_error = str(exc)
        with _lock:
            _registry[manifest.id] = lp
        logger.error("Plugin '%s' instantiation failed: %s", manifest.id, exc)
        return

    lp.instance = instance
    lp.status = PluginStatus.enabled
    with _lock:
        _registry[manifest.id] = lp
    logger.info("Plugin '%s' v%s loaded successfully", manifest.id, manifest.version)


def get_registry() -> dict[str, LoadedPlugin]:
    with _lock:
        return dict(_registry)


def get_plugin(plugin_id: str) -> LoadedPlugin | None:
    with _lock:
        return _registry.get(plugin_id)


def enable_plugin(plugin_id: str) -> bool:
    with _lock:
        lp = _registry.get(plugin_id)
        if lp and lp.instance is not None:
            lp.status = PluginStatus.enabled
            return True
    return False


def disable_plugin(plugin_id: str) -> bool:
    with _lock:
        lp = _registry.get(plugin_id)
        if lp:
            lp.status = PluginStatus.disabled
            return True
    return False


def reload_plugin(plugin_id: str) -> bool:
    """Re-run full validation and reload a plugin from disk."""
    with _lock:
        lp = _registry.get(plugin_id)
    if not lp:
        return False
    _load_plugin_dir(Path(lp.plugin_dir))
    return True


def run_plugins_for_session(parsed_data: dict, device_serial: str | None = None) -> list[dict]:
    """Run all enabled plugins against parsed diagnostic data. Returns list of results."""
    from androbugger.plugins.sandbox import PluginSandbox
    results: list[dict] = []
    with _lock:
        enabled = [(pid, lp) for pid, lp in _registry.items() if lp.status == PluginStatus.enabled]

    import asyncio
    loop = asyncio.new_event_loop()
    try:
        for pid, lp in enabled:
            sandbox = PluginSandbox(lp.manifest.permissions)
            ctx = sandbox.build_context(device_serial)
            try:
                diag_results = loop.run_until_complete(
                    sandbox.run_diagnose(lp.instance, parsed_data, ctx)
                )
                results.append({"plugin_id": pid, "plugin_name": lp.manifest.name, "results": diag_results})
            except Exception as exc:
                logger.warning("Plugin '%s' run error: %s", pid, exc)
    finally:
        loop.close()

    return results
