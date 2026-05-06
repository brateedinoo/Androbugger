"""Diagnostic session endpoints."""
import asyncio
import json
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from androbugger.auth.middleware import get_current_user
from androbugger.db.audit import log as audit_log
from androbugger.db.database import get_db
from androbugger.device import adb as adb_module
from androbugger.device import manager
from androbugger.knowledge.indexer import index_resolved_diagnosis, search_knowledge
from androbugger.llm import prompts, router as llm_router
from androbugger.llm.verifier import verify_citations
from androbugger.parser import bugreport as br_parser
from androbugger.parser import (
    anr as anr_parser,
    dmesg as dmesg_parser,
    dumpsys as dumpsys_parser,
    logcat as logcat_parser,
    tombstone as tombstone_parser,
)
from androbugger.parser.models import ParsedBugreport
from androbugger.parser.summary import generate_summary

router = APIRouter(prefix="/api/diagnostics", tags=["diagnostics"])


class StartRequest(BaseModel):
    device_serial: str


class ResolveRequest(BaseModel):
    root_cause: str
    applied_fix: str
    notes: str = ""


async def _run_diagnosis(session_id: str, device_serial: str, user_id: str) -> None:
    """Background task: pull bugreport → parse → LLM → store results."""
    async with get_db() as db:
        try:
            # 1. Pull bugreport
            await audit_log("bugreport_pull_start", "info", user_id=user_id, device_serial=device_serial)
            zip_path = await adb_module.pull_bugreport(device_serial)
            await audit_log("bugreport_pull_done", "info", user_id=user_id, device_serial=device_serial,
                            detail={"path": str(zip_path)})

            # 2. Parse
            extracted = br_parser.unzip(zip_path)
            main_file = br_parser.identify_main_file(extracted)
            sections: dict[str, str] = {}
            parsed = ParsedBugreport()

            if main_file:
                sections = br_parser.split_sections(main_file)

                # Logcat
                for name, text in sections.items():
                    if "system log" in name.lower() or "logcat" in name.lower():
                        parsed.logcat = logcat_parser.parse_buffer(text)
                        break

                # ANR
                for anr_file in br_parser.identify_anr_files(extracted):
                    try:
                        parsed.anr_traces.append(anr_parser.parse_anr_file(anr_file.read_text(errors="replace")))
                    except Exception:
                        pass

                # Tombstones
                for ts_file in br_parser.identify_tombstone_files(extracted):
                    try:
                        parsed.tombstones.append(tombstone_parser.parse_tombstone(ts_file.read_text(errors="replace")))
                    except Exception:
                        pass

                # Dumpsys
                for name, text in sections.items():
                    nl = name.lower()
                    if "meminfo" in nl:
                        parsed.meminfo = dumpsys_parser.parse_meminfo(text)
                    elif "batterystats" in nl or "battery" in nl:
                        parsed.battery_stats = dumpsys_parser.parse_batterystats(text)
                    elif "activity manager" in nl:
                        parsed.activity_info = dumpsys_parser.parse_activity(text)
                    elif "gfxinfo" in nl or "graphic" in nl:
                        parsed.gfx_info = dumpsys_parser.parse_gfxinfo(text)

                # Dmesg
                for name, text in sections.items():
                    if "kernel" in name.lower() or "dmesg" in name.lower():
                        dmesg_entries = dmesg_parser.parse_dmesg(text)
                        parsed.dmesg = dmesg_entries
                        parsed.thermal_events = dmesg_parser.extract_thermal_events(dmesg_entries)
                        parsed.oom_kills = dmesg_parser.extract_oom_kills(dmesg_entries)
                        parsed.selinux_denials = dmesg_parser.extract_selinux_denials(dmesg_entries)
                        break

                parsed.sections = {k: v[:10000] for k, v in sections.items()}  # cap for storage

            # 3. Deterministic summary
            summary = generate_summary(parsed)
            summary_json = json.dumps({
                "severity": summary.severity,
                "top_errors": [{"tag": e.tag, "count": e.count, "level": e.level, "sample_msg": e.sample_msg} for e in summary.top_errors],
                "tombstone_count": len(summary.tombstones),
                "anr_count": len(summary.anr_events),
                "oom_count": len(summary.oom_events),
                "thermal_count": len(summary.thermal_events),
                "crash_loop_count": len(summary.crash_loops),
                "low_memory_events": summary.low_memory_events_count,
            })

            # 4. Knowledge retrieval — find relevant past cases before LLM call
            device = manager.get_device(device_serial) if device_serial in {d.serial for d in manager.list_connected()} else None
            device_info = device.to_dict() if device else {}
            knowledge_context: list[dict] = []
            try:
                summary_query = " ".join(filter(None, [
                    summary.severity,
                    " ".join(e.tag for e in summary.top_errors[:5]),
                    " ".join(t.signal_name for t in summary.tombstones[:2]),
                ]))
                knowledge_context = search_knowledge(
                    query=summary_query,
                    device_model=device_info.get("model"),
                    namespace="past_diagnoses",
                    top_k=5,
                )
            except Exception:
                pass  # knowledge retrieval is best-effort

            # 5. LLM analysis
            llm_report = None
            llm_provider = None
            llm_tokens = None
            try:
                messages = prompts.build_diagnostic_prompt(
                    summary, parsed.sections, knowledge_context=knowledge_context or None, device_info=device_info
                )
                llm_resp = await llm_router.complete(messages, user_id=user_id, device_serial=device_serial)
                verified = verify_citations(llm_resp.content, parsed)
                llm_report = verified.text
                if verified.warnings:
                    llm_report += "\n\n---\n*Citation warnings: " + "; ".join(verified.warnings[:5]) + "*"
                llm_provider = llm_resp.model
                llm_tokens = llm_resp.prompt_tokens + llm_resp.completion_tokens
                await audit_log("llm_call", "info", user_id=user_id, device_serial=device_serial,
                                detail={"model": llm_resp.model, "tokens": llm_tokens, "latency_ms": round(llm_resp.latency_ms)})
            except Exception as exc:
                llm_report = None
                await audit_log("llm_call_failed", "warning", user_id=user_id, device_serial=device_serial,
                                detail={"error": str(exc)})

            # 6. Store session
            now = datetime.now(timezone.utc).isoformat()
            await db.execute(
                """UPDATE diagnostic_sessions SET
                   status='completed', completed_at=?, bugreport_path=?,
                   deterministic_summary=?, llm_report=?, llm_provider=?, llm_token_count=?
                   WHERE id=?""",
                (now, str(zip_path), summary_json, llm_report, llm_provider, llm_tokens, session_id),
            )
            await db.commit()

        except Exception as exc:
            await db.execute(
                "UPDATE diagnostic_sessions SET status='failed' WHERE id=?", (session_id,)
            )
            await db.commit()
            await audit_log("diagnosis_failed", "warning", user_id=user_id, device_serial=device_serial,
                            detail={"error": str(exc)})


@router.post("/start")
async def start_diagnosis(
    body: StartRequest,
    background_tasks: BackgroundTasks,
    user: Annotated[dict, Depends(get_current_user)],
):
    # Verify device is connected
    try:
        device = manager.get_device(body.device_serial)
    except KeyError:
        raise HTTPException(status_code=404, detail="Device not connected")

    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    async with get_db() as db:
        await db.execute(
            """INSERT INTO diagnostic_sessions
               (id, device_serial, device_model, firmware_version, user_id, status, started_at)
               VALUES (?, ?, ?, ?, ?, 'running', ?)""",
            (session_id, body.device_serial, device.model, device.firmware_version, user["id"], now),
        )
        await db.commit()

    await audit_log("diagnose_start", "info", user_id=user["id"], device_serial=body.device_serial,
                    detail={"session_id": session_id})
    background_tasks.add_task(_run_diagnosis, session_id, body.device_serial, user["id"])
    return {"session_id": session_id}


@router.get("/history")
async def history(
    user: Annotated[dict, Depends(get_current_user)],
    device_serial: str | None = None,
    firmware_version: str | None = None,
    status: str | None = None,
    page: int = 1,
    per_page: int = 20,
):
    conditions = []
    params: list = []
    if device_serial:
        conditions.append("device_serial=?")
        params.append(device_serial)
    if firmware_version:
        conditions.append("firmware_version LIKE ?")
        params.append(f"{firmware_version}%")
    if status:
        conditions.append("status=?")
        params.append(status)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    offset = (page - 1) * per_page

    async with get_db() as db:
        total_row = await (await db.execute(f"SELECT COUNT(*) FROM diagnostic_sessions {where}", params)).fetchone()
        total = total_row[0]
        rows = await (await db.execute(
            f"SELECT id, device_serial, device_model, firmware_version, status, started_at, completed_at, "
            f"llm_provider, llm_token_count, root_cause FROM diagnostic_sessions {where} "
            f"ORDER BY started_at DESC LIMIT ? OFFSET ?",
            params + [per_page, offset],
        )).fetchall()

    sessions = [dict(r) for r in rows]
    return {"sessions": sessions, "total": total, "page": page, "per_page": per_page}


@router.get("/{session_id}")
async def get_session(session_id: str, user: Annotated[dict, Depends(get_current_user)]):
    async with get_db() as db:
        row = await (await db.execute("SELECT * FROM diagnostic_sessions WHERE id=?", (session_id,))).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session": dict(row)}


@router.get("/{session_id}/report")
async def get_report(session_id: str, user: Annotated[dict, Depends(get_current_user)]):
    async with get_db() as db:
        row = await (await db.execute(
            "SELECT llm_report, deterministic_summary FROM diagnostic_sessions WHERE id=?", (session_id,)
        )).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"llm_report": row["llm_report"], "deterministic_summary": row["deterministic_summary"]}


@router.post("/{session_id}/resolve")
async def resolve_session(
    session_id: str,
    body: ResolveRequest,
    user: Annotated[dict, Depends(get_current_user)],
):
    async with get_db() as db:
        await db.execute(
            """UPDATE diagnostic_sessions SET status='resolved', root_cause=?, applied_fix=?, resolution_notes=?
               WHERE id=?""",
            (body.root_cause, body.applied_fix, body.notes, session_id),
        )
        await db.commit()
        row = await (await db.execute("SELECT * FROM diagnostic_sessions WHERE id=?", (session_id,))).fetchone()

    await audit_log("session_resolved", "info", user_id=user["id"],
                    detail={"session_id": session_id, "root_cause": body.root_cause[:100]})

    # Auto-index into knowledge base (best-effort, non-blocking)
    if row:
        try:
            index_resolved_diagnosis(dict(row))
        except Exception:
            pass

    return {"ok": True}


@router.get("/search")
async def search_sessions(q: str, user: Annotated[dict, Depends(get_current_user)]):
    async with get_db() as db:
        rows = await (await db.execute(
            """SELECT ds.id, ds.device_serial, ds.device_model, ds.firmware_version,
                      ds.status, ds.started_at, ds.root_cause
               FROM diagnostic_search fts
               JOIN diagnostic_sessions ds ON ds.id = fts.session_id
               WHERE diagnostic_search MATCH ?
               ORDER BY rank LIMIT 50""",
            (q,),
        )).fetchall()
    return {"sessions": [dict(r) for r in rows]}
