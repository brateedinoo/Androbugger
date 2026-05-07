# MCP Integration Guide — Androbugger

Androbugger exposes 9 tools via the [Model Context Protocol (MCP)](https://modelcontextprotocol.io) so that Claude Desktop and Claude Code can interact directly with connected Android devices.

## Quick Start

### 1. Set your API key

```bash
export ANDROBUGGER_MCP_API_KEY=your-secret-key
# Or add to .env:
# ANDROBUGGER_MCP_API_KEY=your-secret-key
```

### 2. Start the MCP server

**stdio (Claude Desktop / Claude Code):**
```bash
uv run androbugger mcp-server --transport stdio
```

**SSE (network clients):**
```bash
uv run androbugger mcp-server --transport sse --port 8765
```

---

## Claude Desktop Configuration

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "androbugger": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/Androbugger/backend", "androbugger", "mcp-server", "--transport", "stdio"],
      "env": {
        "ANDROBUGGER_MCP_API_KEY": "your-secret-key"
      }
    }
  }
}
```

---

## Claude Code Configuration

Add to `.mcp.json` in your project root (or `~/.claude/mcp.json` for global access):

```json
{
  "androbugger": {
    "command": "uv",
    "args": ["run", "--directory", "/path/to/Androbugger/backend", "androbugger", "mcp-server", "--transport", "stdio"],
    "env": {
      "ANDROBUGGER_MCP_API_KEY": "your-secret-key"
    }
  }
}
```

---

## SSE Transport (Remote / Docker)

When running in Docker or accessing from a remote machine:

```json
{
  "androbugger": {
    "url": "http://localhost:8765/sse",
    "headers": {}
  }
}
```

Pass your API key in each tool call via the `api_key` argument.

---

## Available Tools

| Tool | Description | Required Args |
|------|-------------|---------------|
| `list_devices` | List connected Android devices | — |
| `diagnose` | Start a diagnostic session | `serial` |
| `get_report` | Get a session's diagnostic report | `session_id` |
| `logcat` | Capture recent logcat output | `serial` |
| `shell` | Run read-only ADB shell command | `serial`, `command` |
| `search_knowledge` | Search past diagnoses & vendor docs | `query` |
| `device_info` | Get device properties via getprop | `serial` |
| `hardware_check` | Run hardware subsystem check | `serial` |
| `compare` | Compare two firmware versions | `firmware_a`, `firmware_b` |

### Notes

- `shell` only permits **read-only** commands (e.g. `getprop`, `dumpsys`, `cat`). Destructive or state-changing commands are blocked.
- `hardware_check` runs 6 collectors concurrently (~1–2s); it does not require a running diagnostic session.
- All tool calls are written to the Androbugger audit log.

---

## Example Usage in Claude

```
Can you list the connected devices and start a crash investigation on device emulator-5554?
```

Claude will call `list_devices` → `diagnose(serial="emulator-5554", template_id="crash")` → poll `get_report` until the session completes.
