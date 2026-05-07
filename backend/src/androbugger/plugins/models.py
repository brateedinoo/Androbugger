"""Plugin data models."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum


class PluginStatus(str, Enum):
    enabled = "enabled"
    disabled = "disabled"
    failed = "failed"
    validating = "validating"


@dataclass
class PluginManifest:
    id: str
    name: str
    version: str
    author: str
    description: str
    entry_point: str
    license: str = "Unknown"
    min_androbugger_version: str = "0.1.0"
    capabilities: dict = field(default_factory=dict)
    permissions: dict = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)
    target_devices: dict = field(default_factory=dict)


@dataclass
class LoadedPlugin:
    manifest: PluginManifest
    plugin_dir: str
    status: PluginStatus = PluginStatus.disabled
    instance: object | None = None
    validation_errors: list[str] = field(default_factory=list)
    load_error: str = ""

    @property
    def id(self) -> str:
        return self.manifest.id

    def to_dict(self) -> dict:
        return {
            "id": self.manifest.id,
            "name": self.manifest.name,
            "version": self.manifest.version,
            "author": self.manifest.author,
            "description": self.manifest.description,
            "status": self.status.value,
            "capabilities": self.manifest.capabilities,
            "permissions": self.manifest.permissions,
            "validation_errors": self.validation_errors,
            "load_error": self.load_error,
        }
