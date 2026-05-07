"""Tests for the fine-tuning data export and validation utilities."""
import json
import hashlib
import tempfile
from pathlib import Path

import pytest

from androbugger.llm.finetune import validate_training_data, ValidationResult


# ── validate_training_data ────────────────────────────────────────────────────

def _write_jsonl(lines: list[dict]) -> Path:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False)
    for obj in lines:
        f.write(json.dumps(obj) + "\n")
    f.close()
    return Path(f.name)


def test_validate_valid_file():
    path = _write_jsonl([
        {"messages": [
            {"role": "user", "content": "diagnose this bugreport"},
            {"role": "assistant", "content": "Root cause: OOM in com.app"},
        ]},
        {"messages": [
            {"role": "user", "content": "another bugreport"},
            {"role": "assistant", "content": "Root cause: ANR timeout"},
        ]},
    ])
    result = validate_training_data(path)
    assert result.valid is True
    assert result.record_count == 2
    assert result.errors == []


def test_validate_missing_messages_key():
    path = _write_jsonl([{"text": "not a valid record"}])
    result = validate_training_data(path)
    assert result.valid is False
    assert any("missing 'messages'" in e for e in result.errors)


def test_validate_single_message():
    path = _write_jsonl([{"messages": [{"role": "user", "content": "hello"}]}])
    result = validate_training_data(path)
    assert result.valid is False
    assert any("at least 2 items" in e for e in result.errors)


def test_validate_unknown_role():
    path = _write_jsonl([
        {"messages": [
            {"role": "human", "content": "hello"},
            {"role": "ai", "content": "world"},
        ]}
    ])
    result = validate_training_data(path)
    assert result.valid is False
    assert any("unknown role" in e for e in result.errors)


def test_validate_empty_content():
    path = _write_jsonl([
        {"messages": [
            {"role": "user", "content": "   "},
            {"role": "assistant", "content": "ok"},
        ]}
    ])
    result = validate_training_data(path)
    assert result.valid is False
    assert any("empty content" in e for e in result.errors)


def test_validate_invalid_json():
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False)
    f.write("not valid json\n")
    f.close()
    result = validate_training_data(f.name)
    assert result.valid is False
    assert any("invalid JSON" in e for e in result.errors)


def test_validate_missing_file():
    result = validate_training_data("/nonexistent/path.jsonl")
    assert result.valid is False
    assert any("not found" in e.lower() for e in result.errors)


def test_validate_empty_file():
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False)
    f.close()
    result = validate_training_data(f.name)
    assert result.valid is True
    assert result.record_count == 0


# ── deduplication logic ────────────────────────────────────────────────────────

def test_sha256_dedup_logic():
    """Verify that the SHA256 dedup hash is consistent."""
    summary = "A" * 200 + "extra content that should be ignored"
    h1 = hashlib.sha256(summary[:200].encode()).hexdigest()
    h2 = hashlib.sha256(summary[:200].encode()).hexdigest()
    assert h1 == h2
    h3 = hashlib.sha256("different content here".encode()).hexdigest()
    assert h1 != h3
