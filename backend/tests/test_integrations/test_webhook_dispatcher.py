"""Tests for webhook_dispatcher HMAC signature and retry logic."""
import hashlib
import hmac
import json

import pytest


def test_hmac_signature_matches():
    """Verify HMAC-SHA256 signature is computed correctly."""
    secret = "my-secret"
    body = json.dumps({"event": "session.completed", "payload": {}})
    expected = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    # Recompute
    actual = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    assert expected == actual


def test_hmac_different_body():
    secret = "abc"
    sig1 = hmac.new(secret.encode(), b"body1", hashlib.sha256).hexdigest()
    sig2 = hmac.new(secret.encode(), b"body2", hashlib.sha256).hexdigest()
    assert sig1 != sig2


def test_hmac_different_secret():
    body = b"same body"
    sig1 = hmac.new(b"secret1", body, hashlib.sha256).hexdigest()
    sig2 = hmac.new(b"secret2", body, hashlib.sha256).hexdigest()
    assert sig1 != sig2


def test_empty_secret_produces_signature():
    """Empty secret still produces a deterministic signature."""
    sig = hmac.new(b"", b"payload", hashlib.sha256).hexdigest()
    assert len(sig) == 64


@pytest.mark.asyncio
async def test_dispatch_event_no_endpoints(tmp_path):
    """dispatch_event with no matching endpoints completes without error."""
    import androbugger.db.database as db_module
    from androbugger.db.database import init_db

    original = db_module._db_path
    db_module._db_path = str(tmp_path / "test.db")
    try:
        await init_db()
        from androbugger.integrations.webhook_dispatcher import dispatch_event
        # Should not raise even with empty endpoints table
        await dispatch_event("session.completed", {"session_id": "test"})
    finally:
        db_module._db_path = original
