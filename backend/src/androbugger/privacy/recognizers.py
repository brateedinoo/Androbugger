"""Custom Presidio recognizers for Android device log PII patterns."""
from presidio_analyzer import Pattern, PatternRecognizer


class MACAddressRecognizer(PatternRecognizer):
    PATTERNS = [Pattern("MAC", r"([0-9A-Fa-f]{2}[:\-]){5}[0-9A-Fa-f]{2}", 0.9)]
    CONTEXT = ["mac", "bssid", "address", "addr"]

    def __init__(self):
        super().__init__(supported_entity="MAC_ADDRESS", patterns=self.PATTERNS, context=self.CONTEXT)


class IMEIRecognizer(PatternRecognizer):
    # 15-digit number — validated with Luhn check in load_recognizers
    PATTERNS = [Pattern("IMEI", r"\b\d{15}\b", 0.5)]
    CONTEXT = ["imei", "meid", "device id", "serial"]

    def __init__(self):
        super().__init__(supported_entity="IMEI", patterns=self.PATTERNS, context=self.CONTEXT)


class SSIDRecognizer(PatternRecognizer):
    PATTERNS = [
        Pattern("SSID_EQ", r'ssid="([^"]{2,32})"', 0.9),
        Pattern("SSID_COLON", r"SSID:\s*(\S+)", 0.8),
        Pattern("SSID_QUOTED", r"ssid=([^\s,;]{2,32})", 0.7),
    ]
    CONTEXT = ["ssid", "wifi", "network", "wlan"]

    def __init__(self):
        super().__init__(supported_entity="WIFI_SSID", patterns=self.PATTERNS, context=self.CONTEXT)


class DeviceSerialRecognizer(PatternRecognizer):
    PATTERNS = [
        Pattern("SERIAL_PROP", r"ro\.serialno[=:]\s*([A-Z0-9]{8,20})", 0.9),
        Pattern("SERIAL_GENERIC", r"\bserial[:\s=]+([A-Z0-9]{10,20})\b", 0.7),
    ]
    CONTEXT = ["serial", "serialno", "device serial"]

    def __init__(self):
        super().__init__(supported_entity="DEVICE_SERIAL", patterns=self.PATTERNS, context=self.CONTEXT)


class ADUsernameRecognizer(PatternRecognizer):
    """Active Directory domain\username patterns."""
    PATTERNS = [
        Pattern("AD_BACKSLASH", r"[A-Z]{2,15}\\[a-z][a-z0-9._]{2,20}", 0.85),
        Pattern("AD_UPN", r"[a-z][a-z0-9.]{2,20}@[a-z]{2,15}\.[a-z]{2,5}", 0.7),
    ]
    CONTEXT = ["user", "username", "account", "login", "auth"]

    def __init__(self):
        super().__init__(supported_entity="AD_USERNAME", patterns=self.PATTERNS, context=self.CONTEXT)


class AssetTagRecognizer(PatternRecognizer):
    """Company asset tag — default pattern ADV-XXXXXX; configurable."""
    PATTERNS = [Pattern("ASSET_TAG", r"\bADV-\d{6}\b", 0.95)]
    CONTEXT = ["asset", "tag", "device"]

    def __init__(self, extra_patterns: list[str] | None = None):
        patterns = list(self.PATTERNS)
        for i, p in enumerate(extra_patterns or []):
            patterns.append(Pattern(f"CUSTOM_{i}", p, 0.85))
        super().__init__(supported_entity="ASSET_TAG", patterns=patterns, context=self.CONTEXT)


def all_recognizers(extra_asset_patterns: list[str] | None = None) -> list:
    return [
        MACAddressRecognizer(),
        IMEIRecognizer(),
        SSIDRecognizer(),
        DeviceSerialRecognizer(),
        ADUsernameRecognizer(),
        AssetTagRecognizer(extra_asset_patterns),
    ]
