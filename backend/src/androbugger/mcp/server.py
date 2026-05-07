"""Androbugger MCP server — 9 tools for Claude Desktop / Claude Code integration."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import UTC
from typing import Any

logger = logging.getLogger(__name__)

# ── MCP SDK import (guarded for version flexibility) ─────────────────────────

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import TextContent, Tool
    _MCP_AVAILABLE = True
except ImportError:
    _MCP_AVAILABLE = False
    Server = None  # type: ignore
    stdio_server = None  # type: ignore
    Tool = None  # type: ignore
    TextContent = None  # type: ignore


# ── Auth helper ───────────────────────────────────────────────────────────────

def _check_api_key(key: str | None) -> None:
    expected = os.environ.get("ANDROBUGGER_MCP_API_KEY", "")
    if expected and key != expected:
        raise PermissionError("Invalid or missing MCP API key")


# ── Tool registry ─────────────────────────────────────────────────────────────

_TOOLS: list[dict] = [
    {
        "name": "list_devices",
        "description": "List all currently connected Android devices managed by Androbugger.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "api_key": {"type": "string", "description": "Androbugger MCP API key"},
            },
        },
    },
    {
        "name": "diagnose",
        "description": "Start a diagnostic session for a connected device.",
        "inputSchema": {
            "type": "object",
            "required": ["serial"],
            "properties": {
                "serial": {"type": "string"},
                "template_id": {"type": "string", "description": "Optional template: performance/crash/network"},
                "api_key": {"type": "string"},
            },
        },
    },
    {
        "name": "get_report",
        "description": "Retrieve the diagnostic report for a session.",
        "inputSchema": {
            "type": "object",
            "required": ["session_id"],
            "properties": {
                "session_id": {"type": "string"},
                "api_key": {"type": "string"},
            },
        },
    },
    {
        "name": "logcat",
        "description": "Capture recent logcat output from a device.",
        "inputSchema": {
            "type": "object",
            "required": ["serial"],
            "properties": {
                "serial": {"type": "string"},
                "lines": {"type": "integer", "default": 200},
                "filter": {"type": "string", "description": "logcat filter expression"},
                "api_key": {"type": "string"},
            },
        },
    },
    {
        "name": "shell",
        "description": "Run an ADB shell command on a device (read-only tier only).",
        "inputSchema": {
            "type": "object",
            "required": ["serial", "command"],
            "properties": {
                "serial": {"type": "string"},
                "command": {"type": "string", "description": "Shell command to execute"},
                "api_key": {"type": "string"},
            },
        },
    },
    {
        "name": "search_knowledge",
        "description": "Search the Androbugger knowledge base for past diagnoses and vendor docs.",
        "inputSchema": {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string"},
                "device_model": {"type": "string"},
                "top_k": {"type": "integer", "default": 5},
                "api_key": {"type": "string"},
            },
        },
    },
    {
        "name": "device_info",
        "description": "Get device properties (model, firmware, build props) via adb getprop.",
        "inputSchema": {
            "type": "object",
            "required": ["serial"],
            "properties": {
                "serial": {"type": "string"},
                "api_key": {"type": "string"},
            },
        },
    },
    {
        "name": "hardware_check",
        "description": "Run a hardware diagnostic check on a device (sensors, display, touch, storage, network, USB).",
        "inputSchema": {
            "type": "object",
            "required": ["serial"],
            "properties": {
                "serial": {"type": "string"},
                "api_key": {"type": "string"},
            },
        },
    },
    {
        "name": "compare",
        "description": "Compare diagnostic data between two firmware versions.",
        "inputSchema": {
            "type": "object",
            "required": ["firmware_a", "firmware_b"],
            "properties": {
                "firmware_a": {"type": "string"},
                "firmware_b": {"type": "string"},
                "limit": {"type": "integer", "default": 20},
                "api_key": {"type": "string"},
            },
        },
    },
]


# ── Tool implementations ──────────────────────────────────────────────────────

async def _tool_list_devices(args: dict) -> str:
    from androbugger.device.manager import list_connected
    devices = list_connected()
    return json.dumps([d.to_dict() for d in devices], indent=2)


async def _tool_diagnose(args: dict) -> str:
    import uuid
    from datetime import datetime

    from androbugger.db.database import get_db

    serial = args["serial"]
    template_id = args.get("template_id", "default")
    session_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()

    async with get_db() as db:
        # Get or create system user
        system_row = await (await db.execute(
            "SELECT id FROM users WHERE username='system' LIMIT 1"
        )).fetchone()
        user_id = system_row[0] if system_row else "mcp"

        await db.execute(
            """INSERT INTO diagnostic_sessions
               (id, device_serial, user_id, status, started_at, firmware_version)
               VALUES (?, ?, ?, 'running', ?, ?)""",
            (session_id, serial, user_id, now, None),
        )
        await db.commit()

    # Start diagnosis as background task (fire-and-forget)
    try:
        from androbugger.api.diagnostics import _run_diagnosis
        asyncio.create_task(_run_diagnosis(session_id, serial, template_id))
    except Exception:
        pass

    return json.dumps({"session_id": session_id, "status": "running"})


async def _tool_get_report(args: dict) -> str:
    from androbugger.db.database import get_db
    session_id = args["session_id"]
    async with get_db() as db:
        row = await (await db.execute(
            "SELECT id, device_serial, status, started_at, completed_at,"
            " deterministic_summary, llm_report, root_cause, applied_fix"
            " FROM diagnostic_sessions WHERE id=?",
            (session_id,),
        )).fetchone()
    if not row:
        return json.dumps({"error": f"Session {session_id} not found"})
    return json.dumps(dict(row), indent=2)


async def _tool_logcat(args: dict) -> str:
    from androbugger.device.adb import shell
    serial = args["serial"]
    lines = int(args.get("lines", 200))
    filter_expr = args.get("filter", "*:V")
    cmd = ["logcat", "-d", "-t", str(lines), filter_expr]
    output = await shell(serial, cmd)
    return output or "(no logcat output)"


async def _tool_shell(args: dict) -> str:
    from androbugger.device.adb import _get_tier_for_command, shell
    serial = args["serial"]
    command = args["command"]
    cmd_parts = command.split()

    tier = _get_tier_for_command(cmd_parts)
    if tier not in ("read_only",):
        return f"[Blocked] Command tier '{tier}' is not permitted via MCP (read_only only)"

    output = await shell(serial, cmd_parts)
    return output or "(empty output)"


async def _tool_search_knowledge(args: dict) -> str:
    from androbugger.knowledge.indexer import search_knowledge
    results = search_knowledge(
        query=args["query"],
        device_model=args.get("device_model"),
        namespace="past_diagnoses",
        top_k=int(args.get("top_k", 5)),
    )
    return json.dumps(results, indent=2)


async def _tool_device_info(args: dict) -> str:
    from androbugger.device.adb import getprop
    props = await getprop(args["serial"])
    return json.dumps(props, indent=2)


async def _tool_hardware_check(args: dict) -> str:
    import dataclasses

    from androbugger.device.hardware import run_hardware_check
    from androbugger.parser.hardware_summary import parse_hardware_results

    raw = await run_hardware_check(args["serial"])
    summary = parse_hardware_results(raw)
    return json.dumps({
        "overall_status": summary.overall_status,
        "checked_at": summary.checked_at,
        "subsystems": [dataclasses.asdict(s) for s in summary.subsystems],
    }, indent=2)


async def _tool_compare(args: dict) -> str:
    from androbugger.db.database import get_db
    fw_a = args["firmware_a"]
    fw_b = args["firmware_b"]
    limit = int(args.get("limit", 20))

    async def _fw_stats(db, fw: str) -> dict:
        rows = await (await db.execute(
            """SELECT id, status, root_cause, firmware_version FROM diagnostic_sessions
               WHERE firmware_version=? ORDER BY started_at DESC LIMIT ?""",
            (fw, limit),
        )).fetchall()
        sessions = [dict(r) for r in rows]
        resolved = [s for s in sessions if s["status"] == "resolved"]
        from collections import Counter
        causes = Counter(s["root_cause"] for s in resolved if s.get("root_cause"))
        return {
            "firmware": fw,
            "session_count": len(sessions),
            "resolved_count": len(resolved),
            "top_root_causes": [{"cause": c, "count": n} for c, n in causes.most_common(5)],
            "sessions": sessions[:5],
        }

    async with get_db() as db:
        stats_a = await _fw_stats(db, fw_a)
        stats_b = await _fw_stats(db, fw_b)

    return json.dumps({"firmware_a": stats_a, "firmware_b": stats_b}, indent=2)


_TOOL_HANDLERS = {
    "list_devices": _tool_list_devices,
    "diagnose": _tool_diagnose,
    "get_report": _tool_get_report,
    "logcat": _tool_logcat,
    "shell": _tool_shell,
    "search_knowledge": _tool_search_knowledge,
    "device_info": _tool_device_info,
    "hardware_check": _tool_hardware_check,
    "compare": _tool_compare,
}


# ── Audit helper ──────────────────────────────────────────────────────────────

async def _audit_mcp(tool_name: str, args: dict) -> None:
    try:
        from androbugger.db.audit import log as audit_log
        await audit_log(
            action=f"mcp_{tool_name}",
            severity="info",
            device_serial=args.get("serial"),
            detail={"tool": tool_name},
        )
    except Exception:
        pass


# ── Server run ────────────────────────────────────────────────────────────────

async def run_server(transport: str = "stdio", port: int = 8765) -> None:
    if not _MCP_AVAILABLE:
        raise RuntimeError(
            "mcp package not installed. Run: pip install 'mcp>=1.0'"
        )

    server = Server("androbugger")

    @server.list_tools()
    async def handle_list_tools() -> list[Tool]:
        return [
            Tool(
                name=t["name"],
                description=t["description"],
                inputSchema=t["inputSchema"],
            )
            for t in _TOOLS
        ]

    @server.call_tool()
    async def handle_call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        try:
            _check_api_key(arguments.get("api_key"))
        except PermissionError as e:
            return [TextContent(type="text", text=f"[Auth error] {e}")]

        handler = _TOOL_HANDLERS.get(name)
        if not handler:
            return [TextContent(type="text", text=f"[Error] Unknown tool: {name}")]

        await _audit_mcp(name, arguments)

        try:
            result = await handler(arguments)
            return [TextContent(type="text", text=result)]
        except Exception as exc:
            logger.exception("MCP tool %s failed", name)
            return [TextContent(type="text", text=f"[Error] {exc}")]

    if transport == "stdio":
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())
    elif transport == "sse":
        try:
            import uvicorn
            from mcp.server.sse import SseServerTransport
            from starlette.applications import Starlette
            from starlette.routing import Route

            sse = SseServerTransport("/messages")

            async def handle_sse(request):
                async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
                    await server.run(streams[0], streams[1], server.create_initialization_options())

            async def handle_messages(request):
                await sse.handle_post_message(request.scope, request.receive, request._send)

            starlette_app = Starlette(routes=[
                Route("/sse", endpoint=handle_sse),
                Route("/messages", endpoint=handle_messages, methods=["POST"]),
            ])
            config = uvicorn.Config(starlette_app, host="0.0.0.0", port=port, log_level="info")
            server_instance = uvicorn.Server(config)
            await server_instance.serve()
        except ImportError:
            raise RuntimeError("SSE transport requires starlette and uvicorn: pip install starlette uvicorn")
    else:
        raise ValueError(f"Unknown transport: {transport}. Use 'stdio' or 'sse'.")
