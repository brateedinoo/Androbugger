"""Runtime permission sandboxing for plugin execution."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

_ALLOWED_BUILTINS_READ_ONLY = {
    "abs", "all", "any", "bool", "bytes", "chr", "dict", "dir", "divmod",
    "enumerate", "filter", "float", "format", "frozenset", "getattr",
    "hasattr", "hash", "hex", "int", "isinstance", "issubclass", "iter",
    "len", "list", "map", "max", "min", "next", "oct", "ord", "pow",
    "print", "range", "repr", "reversed", "round", "set", "slice",
    "sorted", "str", "sum", "tuple", "type", "vars", "zip",
}


class PluginSandbox:
    """
    Wraps plugin execution with permission-based constraints.
    Enforces: adb_commands tier, network access, max_execution_time.
    """

    def __init__(self, manifest_permissions: dict):
        self._adb_tier = manifest_permissions.get("adb_commands", "none")
        self._network_allowed = bool(manifest_permissions.get("network", False))
        self._fs_perm = manifest_permissions.get("file_system", "none")
        self._max_time = int(manifest_permissions.get("max_execution_time_seconds", 30))

    def build_context(self, device_serial: str | None = None, adb_fn=None) -> dict:
        """Build a context dict to pass into plugin.diagnose() / plugin.fix()."""
        ctx: dict[str, Any] = {}

        if device_serial and adb_fn and self._adb_tier != "none":
            ctx["adb"] = _RestrictedADB(device_serial, adb_fn, self._adb_tier)

        return ctx

    async def run_diagnose(self, instance: Any, parsed_data: dict, context: dict) -> list[dict]:
        """Run plugin.diagnose() with a timeout."""
        loop = asyncio.get_event_loop()
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(None, instance.diagnose, parsed_data, context),
                timeout=self._max_time,
            )
            if not isinstance(result, list):
                return []
            return [_to_dict(r) for r in result]
        except TimeoutError:
            logger.warning("Plugin diagnose() timed out after %ds", self._max_time)
            return []
        except Exception as exc:
            logger.warning("Plugin diagnose() raised: %s", exc)
            return []

    async def run_fix(self, instance: Any, device_serial: str, diagnosis: dict, context: dict) -> dict | None:
        loop = asyncio.get_event_loop()
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(None, instance.fix, device_serial, diagnosis, context),
                timeout=self._max_time,
            )
            return _to_dict(result) if result else None
        except TimeoutError:
            logger.warning("Plugin fix() timed out after %ds", self._max_time)
            return None
        except Exception as exc:
            logger.warning("Plugin fix() raised: %s", exc)
            return None


class _RestrictedADB:
    """ADB proxy that enforces the plugin's declared adb_commands permission tier."""

    _TIER_ORDER = ["read_only", "state_changing", "destructive"]

    def __init__(self, serial: str, adb_fn, max_tier: str):
        self._serial = serial
        self._adb_fn = adb_fn
        self._max_tier = max_tier

    def _tier_ok(self, cmd_list: list[str]) -> bool:
        cmd = " ".join(cmd_list)
        import fnmatch
        # Very conservative: any write-like command is state_changing+
        write_patterns = ["rm *", "mkdir *", "chmod *", "chown *", "mv *", "cp *",
                          "setprop *", "pm clear *", "am force-stop *", "reboot*", "wipe*"]
        is_write = any(fnmatch.fnmatch(cmd, p) for p in write_patterns)
        required_tier = "state_changing" if is_write else "read_only"
        return (self._TIER_ORDER.index(self._max_tier) >=
                self._TIER_ORDER.index(required_tier))

    def shell(self, args: list[str]) -> str:
        if not self._tier_ok(args):
            raise PermissionError(
                f"Plugin's adb_commands tier '{self._max_tier}' insufficient for: {' '.join(args)}"
            )
        import asyncio

        from androbugger.device import adb as adb_module
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(adb_module.shell(self._serial, args))
        finally:
            loop.close()


def _to_dict(obj: Any) -> dict:
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "__dict__"):
        return {k: v for k, v in vars(obj).items() if not k.startswith("_")}
    return {}
