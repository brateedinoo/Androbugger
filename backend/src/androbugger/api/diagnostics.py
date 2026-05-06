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


class BatchStartRequest(BaseModel):
    device_serials: list[str]


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


@router.post("/batch")
async def batch_start(
    body: BatchStartRequest,
    background_tasks: BackgroundTasks,
    user: Annotated[dict, Depends(get_current_user)],
):
    """Start diagnosis on multiple devices simultaneously."""
    results = []
    now = datetime.now(timezone.utc).isoformat()
    for serial in body.device_serials[:10]:  # cap at 10 concurrent
        try:
            device = manager.get_device(serial)
        except KeyError:
            results.append({"serial": serial, "error": "not connected"})
            continue
        session_id = str(uuid.uuid4())
        async with get_db() as db:
            await db.execute(
                """INSERT INTO diagnostic_sessions
                   (id, device_serial, device_model, firmware_version, user_id, status, started_at)
                   VALUES (?, ?, ?, ?, ?, 'running', ?)""",
                (session_id, serial, device.model, device.firmware_version, user["id"], now),
            )
            await db.commit()
        background_tasks.add_task(_run_diagnosis, session_id, serial, user["id"])
        results.append({"serial": serial, "session_id": session_id})
    await audit_log("batch_diagnose_start", "info", user_id=user["id"],
                    detail={"count": len(results)})
    return {"sessions": results}


@router.get("/compare")
async def compare_firmware(
    firmware_a: str,
    firmware_b: str,
    user: Annotated[dict, Depends(get_current_user)],
    limit: int = 20,
):
    """Compare diagnostic statistics between two firmware versions."""
    async with get_db() as db:
        async def _stats(fw: str) -> dict:
            rows = await (await db.execute(
                """SELECT id, status, root_cause, deterministic_summary, llm_report
                   FROM diagnostic_sessions
                   WHERE firmware_version LIKE ? AND status IN ('completed','resolved')
                   ORDER BY started_at DESC LIMIT ?""",
                (f"{fw}%", limit),
            )).fetchall()
            sessions = [dict(r) for r in rows]
            total = len(sessions)
            failed = sum(1 for s in sessions if s["status"] == "failed")
            resolved = sum(1 for s in sessions if s["status"] == "resolved")
            root_causes: dict[str, int] = {}
            for s in sessions:
                rc = (s.get("root_cause") or "Unknown")[:60]
                root_causes[rc] = root_causes.get(rc, 0) + 1
            top_causes = sorted(root_causes.items(), key=lambda x: x[1], reverse=True)[:5]
            return {
                "firmware": fw,
                "session_count": total,
                "resolved_count": resolved,
                "top_root_causes": [{"cause": c, "count": n} for c, n in top_causes],
                "sessions": sessions[:5],  # sample
            }

        stats_a = await _stats(firmware_a)
        stats_b = await _stats(firmware_b)

    return {"firmware_a": stats_a, "firmware_b": stats_b}


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


@router.get("/{session_id}/export")
async def export_session(
    session_id: str,
    user: Annotated[dict, Depends(get_current_user)],
    format: str = "markdown",
):
    """Export a diagnostic session as markdown or PDF."""
    async with get_db() as db:
        row = await (await db.execute("SELECT * FROM diagnostic_sessions WHERE id=?", (session_id,))).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Session not found")
    session = dict(row)

    md_content = _build_markdown_report(session)

    if format == "pdf":
        return await _export_pdf(md_content, session_id)

    from fastapi.responses import Response
    filename = f"androbugger-{session_id[:8]}.md"
    return Response(
        content=md_content.encode(),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _build_markdown_report(session: dict) -> str:
    lines = [
        f"# Androbugger Diagnostic Report",
        f"",
        f"**Session ID:** `{session.get('id', '')}`  ",
        f"**Device:** {session.get('device_model') or 'Unknown'} (`{session.get('device_serial', '')}`)",
        f"**Firmware:** {session.get('firmware_version') or 'Unknown'}  ",
        f"**Status:** {session.get('status', '')}  ",
        f"**Started:** {session.get('started_at', '')}  ",
        f"**Completed:** {session.get('completed_at') or '—'}  ",
        f"",
    ]
    if session.get("root_cause"):
        lines += [f"## Root Cause", f"", session["root_cause"], f""]
    if session.get("applied_fix"):
        lines += [f"## Applied Fix", f"", session["applied_fix"], f""]
    if session.get("resolution_notes"):
        lines += [f"## Notes", f"", session["resolution_notes"], f""]
    if session.get("llm_report"):
        lines += [f"## AI Analysis", f"", session["llm_report"], f""]
    if session.get("deterministic_summary"):
        lines += [f"## Deterministic Summary", f"", f"```json", session["deterministic_summary"], f"```", f""]
    lines += [f"---", f"*Generated by Androbugger*"]
    return "\n".join(lines)


async def _export_pdf(md_content: str, session_id: str):
    from fastapi.responses import Response
    try:
        import markdown as md_lib
        import weasyprint
        html_body = md_lib.markdown(md_content, extensions=["tables", "fenced_code"])
        html = f"""<!DOCTYPE html><html><head>
<style>
  body {{ font-family: sans-serif; max-width: 900px; margin: 2rem auto; color: #1a1a1a; line-height: 1.6; }}
  pre {{ background: #f4f4f4; padding: 1em; border-radius: 4px; overflow-x: auto; }}
  code {{ font-family: monospace; font-size: 0.9em; }}
  h1 {{ border-bottom: 2px solid #333; padding-bottom: .5em; }}
  h2 {{ color: #333; border-bottom: 1px solid #ccc; }}
</style></head><body>{html_body}</body></html>"""
        pdf_bytes = weasyprint.HTML(string=html).write_pdf()
        filename = f"androbugger-{session_id[:8]}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except ImportError:
        from fastapi import HTTPException
        raise HTTPException(status_code=501, detail="PDF export requires weasyprint and markdown packages")


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
