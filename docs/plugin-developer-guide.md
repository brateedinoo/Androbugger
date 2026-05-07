# Plugin Developer Guide — Androbugger

Androbugger plugins are Python packages that extend diagnostic analysis. Each plugin lives in its own directory inside `backend/plugins/`.

## Directory Structure

```
my-plugin/
├── manifest.json          # Plugin metadata and capability declarations
├── plugin.py              # Plugin class implementation
└── test_fixtures/
    ├── input_bugreport.json   # Sample parsed_data for testing
    └── expected_output.json   # Expected diagnostic result fields
```

## manifest.json

```json
{
  "id": "my-plugin",
  "name": "My Plugin",
  "version": "1.0.0",
  "author": "Your Name",
  "description": "What this plugin detects or fixes",
  "license": "MIT",
  "min_androbugger_version": "0.1.0",
  "target_devices": {
    "models": ["*"],
    "firmware_versions": ["*"]
  },
  "entry_point": "plugin.py",
  "capabilities": {
    "diagnostic_patterns": [
      {
        "id": "my_pattern",
        "name": "Human-readable name",
        "description": "What this pattern detects",
        "severity": "critical | warning | info"
      }
    ],
    "fix_routines": [],
    "custom_parsers": []
  },
  "permissions": {
    "adb_commands": "read_only | state_changing | destructive",
    "network": false,
    "file_system": "read | write | none",
    "max_execution_time_seconds": 30
  },
  "dependencies": [],
  "test_data": "test_fixtures/",
  "metadata": {}
}
```

### `metadata` Field

Use `metadata` for plugin-configurable parameters (patterns, thresholds, etc.) that can be changed without code edits. Access them in `plugin.py` via `context.get("manifest_metadata", {})`.

## plugin.py — Plugin Class Interface

```python
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PluginDiagnosticResult:
    pattern_id: str
    detected: bool
    confidence: str          # "high" | "medium" | "low"
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
    def diagnose(self, parsed_data: dict, context: dict) -> list[PluginDiagnosticResult]:
        """Analyse parsed bugreport data and return results."""
        ...

    def fix(self, device_serial: str, diagnosis: PluginDiagnosticResult, context: dict) -> Optional[FixResult]:
        """Optionally apply a fix. Return None if no fix is available."""
        return None
```

### `parsed_data` Keys

| Key | Type | Contents |
|-----|------|----------|
| `props` | `dict[str, str]` | Device build properties from `getprop` |
| `tombstones` | `list[dict]` | Parsed native crash tombstones |
| `anr` | `list[dict]` | ANR trace events |
| `meminfo` | `dict` | Memory info including `per_process` |
| `thermal` | `dict` | Thermal zone readings |
| `logcat` | `list[dict]` | Recent logcat entries |

### `context` Keys

| Key | Type | Contents |
|-----|------|----------|
| `adb` | `RestrictedADB` | ADB interface (tier-limited by manifest permissions) |
| `manifest_metadata` | `dict` | The `metadata` block from your `manifest.json` |
| `device_serial` | `str` | The target device serial |
| `session_id` | `str` | Current diagnostic session ID |

## Sandbox Restrictions

- **ADB tier**: Commands are limited by `permissions.adb_commands`. Attempting a higher-tier command raises `PermissionError`.
- **Execution timeout**: `max_execution_time_seconds` (default 30s). The `diagnose()` method is cancelled if it exceeds this.
- **No network access**: Even if `network: true`, outbound connections are not enforced at the Python level — use responsibly and document why.

## Test Fixtures

Androbugger validates plugins against fixtures before loading them. The test will:

1. Load `test_fixtures/input_bugreport.json` as `parsed_data`
2. Call `Plugin().diagnose(parsed_data, {})`
3. Check that the first result's `pattern_id`, `detected`, and `confidence` match `expected_output.json`

**`expected_output.json` format:**
```json
{
  "pattern_id": "my_pattern",
  "detected": true,
  "confidence": "high"
}
```

## Publishing to the Marketplace

1. Create a public GitHub repository named `androbugger-<plugin-name>`
2. Add the topic `androbugger-plugin` to your repository (Settings → Topics)
3. Include `manifest.json`, `plugin.py`, and `test_fixtures/` at the repo root
4. Your plugin will appear in the Androbugger Marketplace tab within 5 minutes (cache TTL)

## Example: Installing via Marketplace

From the Plugin Manager UI → Marketplace tab → paste your GitHub URL → Install.

Or via API:
```bash
curl -X POST http://localhost:8000/api/plugins/install \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"github_url": "https://github.com/you/androbugger-my-plugin"}'
```
