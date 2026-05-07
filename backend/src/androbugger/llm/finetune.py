"""Fine-tuning data export, validation, and model evaluation utilities."""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ExportResult:
    record_count: int
    skipped_count: int
    path: str


@dataclass
class ValidationResult:
    valid: bool
    record_count: int
    errors: list[str]


@dataclass
class EvalResult:
    model_id: str
    record_count: int
    rouge_l_precision: float
    rouge_l_recall: float
    rouge_l_fmeasure: float


def export_training_data(output_path: str | Path, min_quality: float = 0.0) -> ExportResult:
    """Export resolved diagnostic sessions as JSONL training data."""
    import asyncio
    return asyncio.run(_export_training_data_async(Path(output_path), min_quality))


async def _export_training_data_async(output_path: Path, min_quality: float) -> ExportResult:
    from androbugger.db.database import get_db

    output_path.parent.mkdir(parents=True, exist_ok=True)

    seen_hashes: set[str] = set()
    record_count = 0
    skipped_count = 0

    async with get_db() as db:
        rows = await (await db.execute(
            """SELECT id, deterministic_summary, llm_report, root_cause, applied_fix, user_id
               FROM diagnostic_sessions
               WHERE status = 'resolved'
                 AND root_cause IS NOT NULL AND root_cause != ''
                 AND applied_fix IS NOT NULL AND applied_fix != ''
                 AND llm_report IS NOT NULL"""
        )).fetchall()

        with output_path.open("w", encoding="utf-8") as f:
            for row in rows:
                r = dict(row)
                summary = r.get("deterministic_summary") or ""
                report = r.get("llm_report") or ""
                root_cause = r.get("root_cause") or ""
                applied_fix = r.get("applied_fix") or ""

                # Quality filters
                if len(summary) < 50 or len(report) < 100 or len(root_cause) < 10:
                    skipped_count += 1
                    continue

                # Near-duplicate filter
                dedup_hash = hashlib.sha256(summary[:200].encode()).hexdigest()
                if dedup_hash in seen_hashes:
                    skipped_count += 1
                    continue
                seen_hashes.add(dedup_hash)

                assistant_content = f"{report}\n\nRoot cause: {root_cause}\n\nApplied fix: {applied_fix}"
                record = {
                    "messages": [
                        {"role": "user", "content": summary},
                        {"role": "assistant", "content": assistant_content},
                    ]
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                record_count += 1

        # Record export in DB
        exported_at = datetime.now(timezone.utc).isoformat()
        try:
            # Use first resolved session's user_id as fallback exporter
            first_row = rows[0] if rows else None
            exporter_id = first_row["user_id"] if first_row else "system"
            await db.execute(
                """INSERT INTO finetune_exports (exported_at, exported_by, record_count, output_path, filters_json)
                   VALUES (?, ?, ?, ?, ?)""",
                (exported_at, exporter_id, record_count, str(output_path),
                 json.dumps({"min_quality": min_quality})),
            )
            await db.commit()
        except Exception:
            pass

    logger.info("Exported %d training records, skipped %d", record_count, skipped_count)
    return ExportResult(record_count=record_count, skipped_count=skipped_count, path=str(output_path))


def export_training_data_for_user(output_path: str | Path, user_id: str, min_quality: float = 0.0) -> ExportResult:
    """Export training data and attribute the export to a specific user."""
    import asyncio
    return asyncio.run(_export_for_user_async(Path(output_path), user_id, min_quality))


async def _export_for_user_async(output_path: Path, user_id: str, min_quality: float) -> ExportResult:
    from androbugger.db.database import get_db

    output_path.parent.mkdir(parents=True, exist_ok=True)
    seen_hashes: set[str] = set()
    record_count = 0
    skipped_count = 0

    async with get_db() as db:
        rows = await (await db.execute(
            """SELECT deterministic_summary, llm_report, root_cause, applied_fix
               FROM diagnostic_sessions
               WHERE status = 'resolved'
                 AND root_cause IS NOT NULL AND root_cause != ''
                 AND applied_fix IS NOT NULL AND applied_fix != ''
                 AND llm_report IS NOT NULL"""
        )).fetchall()

        with output_path.open("w", encoding="utf-8") as f:
            for row in rows:
                r = dict(row)
                summary = r.get("deterministic_summary") or ""
                report = r.get("llm_report") or ""
                root_cause = r.get("root_cause") or ""
                applied_fix = r.get("applied_fix") or ""

                if len(summary) < 50 or len(report) < 100 or len(root_cause) < 10:
                    skipped_count += 1
                    continue

                dedup_hash = hashlib.sha256(summary[:200].encode()).hexdigest()
                if dedup_hash in seen_hashes:
                    skipped_count += 1
                    continue
                seen_hashes.add(dedup_hash)

                assistant_content = f"{report}\n\nRoot cause: {root_cause}\n\nApplied fix: {applied_fix}"
                record = {
                    "messages": [
                        {"role": "user", "content": summary},
                        {"role": "assistant", "content": assistant_content},
                    ]
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                record_count += 1

        exported_at = datetime.now(timezone.utc).isoformat()
        try:
            await db.execute(
                """INSERT INTO finetune_exports (exported_at, exported_by, record_count, output_path, filters_json)
                   VALUES (?, ?, ?, ?, ?)""",
                (exported_at, user_id, record_count, str(output_path),
                 json.dumps({"min_quality": min_quality})),
            )
            await db.commit()
        except Exception:
            pass

    return ExportResult(record_count=record_count, skipped_count=skipped_count, path=str(output_path))


def validate_training_data(input_path: str | Path) -> ValidationResult:
    """Validate a JSONL training file for schema correctness and content sanity."""
    p = Path(input_path)
    if not p.exists():
        return ValidationResult(valid=False, record_count=0, errors=[f"File not found: {p}"])

    errors: list[str] = []
    record_count = 0

    with p.open("r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                errors.append(f"Line {lineno}: invalid JSON — {e}")
                continue

            if "messages" not in obj:
                errors.append(f"Line {lineno}: missing 'messages' key")
                continue

            msgs = obj["messages"]
            if not isinstance(msgs, list) or len(msgs) < 2:
                errors.append(f"Line {lineno}: 'messages' must be a list with at least 2 items")
                continue

            for i, msg in enumerate(msgs):
                if not isinstance(msg, dict):
                    errors.append(f"Line {lineno} msg[{i}]: not a dict")
                elif "role" not in msg or "content" not in msg:
                    errors.append(f"Line {lineno} msg[{i}]: missing 'role' or 'content'")
                elif msg["role"] not in ("user", "assistant", "system"):
                    errors.append(f"Line {lineno} msg[{i}]: unknown role '{msg['role']}'")
                elif not isinstance(msg["content"], str) or len(msg["content"].strip()) == 0:
                    errors.append(f"Line {lineno} msg[{i}]: empty content")

            record_count += 1

    valid = len(errors) == 0
    return ValidationResult(valid=valid, record_count=record_count, errors=errors[:50])


def evaluate_model(model_id: str, eval_set_path: str | Path) -> EvalResult:
    """Evaluate a model against a JSONL eval set using ROUGE-L."""
    try:
        from rouge_score import rouge_scorer
    except ImportError:
        raise RuntimeError("rouge-score is not installed. Run: pip install rouge-score")

    import asyncio
    return asyncio.run(_evaluate_model_async(model_id, Path(eval_set_path)))


async def _evaluate_model_async(model_id: str, eval_path: Path) -> EvalResult:
    import litellm
    from rouge_score import rouge_scorer

    scorer = rouge_scorer.RougeScorer(["rougeL"], use_stemmer=True)

    validation = validate_training_data(eval_path)
    if not validation.valid:
        raise ValueError(f"Invalid eval set: {validation.errors[:3]}")

    precisions: list[float] = []
    recalls: list[float] = []
    fmeasures: list[float] = []

    with eval_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            msgs = obj["messages"]
            user_msg = next((m["content"] for m in msgs if m["role"] == "user"), None)
            reference = next((m["content"] for m in msgs if m["role"] == "assistant"), None)
            if not user_msg or not reference:
                continue

            try:
                resp = await litellm.acompletion(
                    model=model_id,
                    messages=[{"role": "user", "content": user_msg}],
                    max_tokens=512,
                )
                prediction = resp.choices[0].message.content or ""
            except Exception:
                prediction = ""

            scores = scorer.score(reference, prediction)
            precisions.append(scores["rougeL"].precision)
            recalls.append(scores["rougeL"].recall)
            fmeasures.append(scores["rougeL"].fmeasure)

    n = len(fmeasures) or 1
    return EvalResult(
        model_id=model_id,
        record_count=n,
        rouge_l_precision=sum(precisions) / n,
        rouge_l_recall=sum(recalls) / n,
        rouge_l_fmeasure=sum(fmeasures) / n,
    )


async def get_finetune_stats() -> dict:
    """Return stats for the admin panel: exportable session count and last export info."""
    from androbugger.db.database import get_db
    async with get_db() as db:
        count_row = await (await db.execute(
            """SELECT COUNT(*) FROM diagnostic_sessions
               WHERE status = 'resolved'
                 AND root_cause IS NOT NULL AND root_cause != ''
                 AND applied_fix IS NOT NULL AND applied_fix != ''
                 AND llm_report IS NOT NULL"""
        )).fetchone()
        exportable = count_row[0] if count_row else 0

        last_row = await (await db.execute(
            "SELECT exported_at, record_count, output_path FROM finetune_exports ORDER BY id DESC LIMIT 1"
        )).fetchone()
        last_export = dict(last_row) if last_row else None

    return {"exportable_sessions": exportable, "last_export": last_export}
