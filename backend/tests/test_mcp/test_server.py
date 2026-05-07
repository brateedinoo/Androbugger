"""Tests for MCP server tool registry and auth."""
import pytest

from androbugger.mcp.server import _TOOLS, _TOOL_HANDLERS, _check_api_key


# ── Tool registry ──────────────────────────────────────────────────────────────

def test_all_tools_have_handlers():
    """Every declared tool must have a corresponding handler."""
    tool_names = {t["name"] for t in _TOOLS}
    handler_names = set(_TOOL_HANDLERS.keys())
    assert tool_names == handler_names, f"Mismatched: {tool_names ^ handler_names}"


def test_tool_schemas_have_required_fields():
    for tool in _TOOLS:
        assert "name" in tool, f"Tool missing 'name'"
        assert "description" in tool, f"Tool {tool.get('name')} missing 'description'"
        assert "inputSchema" in tool, f"Tool {tool.get('name')} missing 'inputSchema'"
        schema = tool["inputSchema"]
        assert schema.get("type") == "object", f"Tool {tool['name']} schema type should be 'object'"


def test_expected_tool_count():
    assert len(_TOOLS) == 9, f"Expected 9 tools, got {len(_TOOLS)}"


def test_expected_tool_names():
    names = {t["name"] for t in _TOOLS}
    expected = {
        "list_devices", "diagnose", "get_report", "logcat", "shell",
        "search_knowledge", "device_info", "hardware_check", "compare",
    }
    assert names == expected


# ── Auth ───────────────────────────────────────────────────────────────────────

def test_check_api_key_no_env(monkeypatch):
    """When env var is empty, any key (including None) is accepted."""
    monkeypatch.setenv("ANDROBUGGER_MCP_API_KEY", "")
    _check_api_key(None)   # should not raise
    _check_api_key("anything")  # should not raise


def test_check_api_key_correct(monkeypatch):
    monkeypatch.setenv("ANDROBUGGER_MCP_API_KEY", "secret123")
    _check_api_key("secret123")  # should not raise


def test_check_api_key_wrong(monkeypatch):
    monkeypatch.setenv("ANDROBUGGER_MCP_API_KEY", "secret123")
    with pytest.raises(PermissionError):
        _check_api_key("wrong")


def test_check_api_key_none_when_required(monkeypatch):
    monkeypatch.setenv("ANDROBUGGER_MCP_API_KEY", "required")
    with pytest.raises(PermissionError):
        _check_api_key(None)
