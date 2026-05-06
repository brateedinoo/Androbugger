"""AI chat WebSocket endpoint and explain-this REST endpoint."""
import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from androbugger.auth.middleware import get_current_user
from androbugger.db.database import get_db
from androbugger.llm import prompts, router as llm_router
from androbugger.llm.verifier import verify_citations
from androbugger.parser.models import ParsedBugreport

router = APIRouter(tags=["chat"])


class ExplainRequest(BaseModel):
    device_serial: str
    selected_lines: list[dict]  # [{line_number, text}]


@router.post("/api/chat/explain")
async def explain_lines(
    body: ExplainRequest,
    user: Annotated[dict, Depends(get_current_user)],
):
    lines_text = "\n".join(
        f"[Line {l.get('line_number', '?')}] {l.get('text', '')}"
        for l in body.selected_lines[:50]
    )
    messages = [
        {"role": "system", "content": "You are an Android system log expert. Explain the following logcat entries clearly. State whether they indicate a problem and what the likely cause is."},
        {"role": "user", "content": f"Explain these logcat entries:\n\n{lines_text}"},
    ]
    try:
        resp = await llm_router.complete(messages, user_id=user["id"])
        return {"explanation": resp.content, "warnings": []}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.websocket("/ws/chat/{session_id}")
async def ws_chat(websocket: WebSocket, session_id: str):
    await websocket.accept()

    # Load session context
    async with get_db() as db:
        row = await (await db.execute(
            "SELECT * FROM diagnostic_sessions WHERE id=?", (session_id,)
        )).fetchone()
        if not row:
            await websocket.close(code=4004, reason="Session not found")
            return
        session = dict(row)

        # Load chat history
        history_rows = await (await db.execute(
            "SELECT role, content FROM chat_messages WHERE session_id=? ORDER BY timestamp ASC LIMIT 40",
            (session_id,),
        )).fetchall()
        chat_history = [dict(r) for r in history_rows]

    summary_text = session.get("deterministic_summary") or ""
    if session.get("llm_report"):
        summary_text += "\n\n" + session["llm_report"][:2000]

    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            if data.get("type") != "message":
                continue
            user_msg = data.get("content", "").strip()
            if not user_msg:
                continue

            # Save user message
            msg_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc).isoformat()
            async with get_db() as db:
                await db.execute(
                    "INSERT INTO chat_messages (id, session_id, role, content, timestamp) VALUES (?,?,?,?,?)",
                    (msg_id, session_id, "user", user_msg, now),
                )
                await db.commit()
            chat_history.append({"role": "user", "content": user_msg})

            # Build prompt and stream response
            messages = prompts.build_chat_prompt(summary_text, chat_history[:-1], user_msg)
            full_response = ""
            try:
                async for chunk in llm_router.stream(messages):
                    full_response += chunk
                    await websocket.send_text(json.dumps({"type": "chunk", "content": chunk}))
                await websocket.send_text(json.dumps({"type": "done"}))
            except Exception as exc:
                await websocket.send_text(json.dumps({"type": "error", "content": str(exc)}))
                continue

            # Save assistant response
            asst_id = str(uuid.uuid4())
            now2 = datetime.now(timezone.utc).isoformat()
            async with get_db() as db:
                await db.execute(
                    "INSERT INTO chat_messages (id, session_id, role, content, timestamp) VALUES (?,?,?,?,?)",
                    (asst_id, session_id, "assistant", full_response, now2),
                )
                await db.commit()
            chat_history.append({"role": "assistant", "content": full_response})

            # Trim history to last 20
            if len(chat_history) > 20:
                chat_history = chat_history[-20:]

    except WebSocketDisconnect:
        pass
