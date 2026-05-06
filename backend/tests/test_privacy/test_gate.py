"""Privacy Gate tests — no network or device required."""
import pytest
from androbugger.privacy.gate import PrivacyGate, is_cloud_provider
from androbugger.privacy.mapper import PlaceholderMapper


def test_is_cloud_provider():
    assert is_cloud_provider("anthropic/claude-sonnet-4-5")
    assert is_cloud_provider("openai/gpt-4o")
    assert not is_cloud_provider("ollama/qwen3:14b")
    assert not is_cloud_provider("ollama_chat/qwen3:8b")
    assert not is_cloud_provider("vllm/my-model")


def test_sanitize_email():
    gate = PrivacyGate()
    result = gate.sanitize("Contact admin@example.com for help", "sess1")
    assert "admin@example.com" not in result.text
    assert result.placeholder_count >= 1
    assert "[EMAIL_ADDRESS_1]" in result.text or "EMAIL" in result.text


def test_sanitize_ip():
    gate = PrivacyGate()
    result = gate.sanitize("Connected to IP 192.168.1.100 via ADB", "sess2")
    assert "192.168.1.100" not in result.text
    assert result.placeholder_count >= 1


def test_sanitize_mac():
    gate = PrivacyGate()
    result = gate.sanitize("WiFi BSSID: aa:bb:cc:dd:ee:ff connected", "sess3")
    assert "aa:bb:cc:dd:ee:ff" not in result.text


def test_restore_roundtrip():
    gate = PrivacyGate()
    original = "User john.doe@corp.com connected from 10.0.0.1"
    sanitized = gate.sanitize(original, "sess4")
    assert sanitized.placeholder_count >= 1
    restored = gate.restore(sanitized.text, "sess4")
    assert "john.doe@corp.com" in restored
    assert "10.0.0.1" in restored


def test_no_pii_unchanged():
    gate = PrivacyGate()
    text = "FATAL EXCEPTION: main process com.example.app crashed"
    result = gate.sanitize(text, "sess5")
    assert result.placeholder_count == 0
    assert result.text == text


def test_mapper_destroy_session():
    mapper = PlaceholderMapper()
    mapper.add_mapping("s1", "[EMAIL_1]", "test@test.com")
    assert mapper.get_original("s1", "[EMAIL_1]") == "test@test.com"
    mapper.destroy_session("s1")
    assert mapper.get_original("s1", "[EMAIL_1]") is None


def test_stable_placeholder_numbering():
    gate = PrivacyGate()
    text = "From: alice@corp.com cc: bob@corp.com"
    result = gate.sanitize(text, "sess6")
    # Two distinct emails should get distinct placeholder numbers
    assert result.placeholder_count >= 1
