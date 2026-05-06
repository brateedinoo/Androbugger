from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


@dataclass
class DeviceInfo:
    serial: str
    model: str | None = None
    firmware_version: str | None = None
    connection_type: Literal["usb", "tcp"] = "usb"
    ip_address: str | None = None
    android_version: str | None = None
    build_fingerprint: str | None = None
    connected_at: datetime = field(default_factory=datetime.utcnow)
    last_seen: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "serial": self.serial,
            "model": self.model,
            "firmware_version": self.firmware_version,
            "connection_type": self.connection_type,
            "ip_address": self.ip_address,
            "android_version": self.android_version,
            "build_fingerprint": self.build_fingerprint,
            "connected_at": self.connected_at.isoformat(),
            "last_seen": self.last_seen.isoformat(),
        }
