"""Natural language ADB command translation and execution."""
import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from androbugger.auth.middleware import get_current_user, require_role
from androbugger.auth.roles import role_gte
from androbugger.db.audit import log as audit_log
from androbugger.db.database import get_db
from androbugger.device import adb as adb_module
from androbugger.llm import router as llm_router

router = APIRouter(prefix="/api/commands", tags=["commands"])

_NL_SYSTEM = (
    "Translate the following user intent into one or more ADB shell commands. "
    "Respond ONLY with valid JSON in the format: "
    '{"commands": [{"cmd": "logcat -v threadtime -t 100", "destructive": false,'
    ' "explanation": "Gets last 100 log lines"}]}. '
    "Do not include 'adb shell' prefix — just the shell command. "
    "Mark destructive=true only for commands that irreversibly modify device state "
    "(reboot, factory reset, wipe, rm, format)."
)


async def _get_permission_tier(command: str) -> tuple[str, bool, str]:
    """Return (tier, requires_confirmation, min_role) for a command."""
    import fnmatch
    async with get_db() as db:
        rows = await (await db.execute("SELECT * FROM command_permissions ORDER BY length(pattern) DESC")).fetchall()
    for row in rows:
        if fnmatch.fnmatch(command, row["pattern"]):
            return row["tier"], bool(row["requires_confirmation"]), row["min_role"]
    return "state_changing", True, "technician"


class NaturalRequest(BaseModel):
    device_serial: str
    query: str


class ExecuteRequest(BaseModel):
    device_serial: str
    commands: list[dict]
    confirmed: bool = False


class RawRequest(BaseModel):
    device_serial: str
    command: str


@router.post("/natural")
async def natural_command(body: NaturalRequest, user: Annotated[dict, Depends(get_current_user)]):
    messages = [
        {"role": "system", "content": _NL_SYSTEM},
        {"role": "user", "content": body.query},
    ]
    try:
        resp = await llm_router.complete(messages, user_id=user["id"], device_serial=body.device_serial)
        parsed = json.loads(resp.content.strip().strip("```json").strip("```"))
        commands = parsed.get("commands", [])
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"LLM translation failed: {exc}") from exc

    needs_confirmation = False
    blocked: list[str] = []
    enriched: list[dict] = []

    for cmd_obj in commands:
        cmd = cmd_obj.get("cmd", "")
        tier, req_confirm, min_role = await _get_permission_tier(cmd)
        if not role_gte(user["role"], min_role):
            blocked.append(cmd)
            continue
        if req_confirm or tier in ("state_changing", "destructive"):
            needs_confirmation = True
        enriched.append({**cmd_obj, "tier": tier, "requires_confirmation": req_confirm})

    return {"commands": enriched, "needs_confirmation": needs_confirmation, "blocked_commands": blocked}


@router.post("/execute")
async def execute_commands(body: ExecuteRequest, user: Annotated[dict, Depends(get_current_user)]):
    needs_conf = any(c.get("requires_confirmation") for c in body.commands)
    if needs_conf and not body.confirmed:
        raise HTTPException(status_code=403, detail="Confirmation required")

    results = []
    for cmd_obj in body.commands:
        cmd = cmd_obj.get("cmd", "")
        try:
            output = await adb_module.shell(body.device_serial, cmd.split())
            await audit_log(
                "adb_command", "info",
                user_id=user["id"],
                device_serial=body.device_serial,
                detail={"command": cmd, "output_length": len(output), "confirmed": body.confirmed},
            )
            results.append({"command": cmd, "output": output[:5000], "error": None})
        except Exception as exc:
            results.append({"command": cmd, "output": None, "error": str(exc)})

    # LLM interprets the combined output
    combined = "\n\n".join(
        f"$ {r['command']}\n{r['output'] or r['error']}" for r in results
    )
    interp = ""
    try:
        msgs = [
            {
                "role": "system",
                "content": (
                    "You are an Android device expert. Interpret the following ADB command output "
                    "in plain language. Be concise."
                ),
            },
            {"role": "user", "content": combined[:4000]},
        ]
        iresp = await llm_router.complete(msgs, user_id=user["id"])
        interp = iresp.content
    except Exception:
        pass

    return {"results": results, "interpretation": interp}


@router.post("/raw")
async def raw_command(
    body: RawRequest,
    user: Annotated[dict, Depends(require_role("developer"))],
):
    tier, _, _ = await _get_permission_tier(body.command)
    await audit_log(
        "adb_command_raw",
        "warning" if tier == "destructive" else "info",
        user_id=user["id"],
        device_serial=body.device_serial,
        detail={"command": body.command, "tier": tier},
    )
    output = await adb_module.shell(body.device_serial, body.command.split())
    return {"output": output}
