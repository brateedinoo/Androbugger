import pytest
import asyncio
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_logcat() -> str:
    return (FIXTURES_DIR / "logcat_crash.txt").read_text()


@pytest.fixture
def sample_anr() -> str:
    return (FIXTURES_DIR / "anr_trace.txt").read_text()


@pytest.fixture
def sample_tombstone() -> str:
    return (FIXTURES_DIR / "tombstone_sample.txt").read_text()
