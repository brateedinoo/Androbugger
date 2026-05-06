from androbugger.parser.logcat import parse_buffer
from androbugger.parser.tombstone import parse_tombstone
from androbugger.parser.models import ParsedBugreport
from androbugger.parser.summary import generate_summary


def test_summary_critical_with_tombstone(sample_logcat, sample_tombstone):
    parsed = ParsedBugreport(
        logcat=parse_buffer(sample_logcat),
        tombstones=[parse_tombstone(sample_tombstone)],
    )
    summary = generate_summary(parsed)
    assert summary.severity == "critical"
    assert len(summary.tombstones) == 1


def test_summary_info_on_clean():
    parsed = ParsedBugreport()
    summary = generate_summary(parsed)
    assert summary.severity == "info"
    assert summary.top_errors == []


def test_summary_top_errors(sample_logcat):
    parsed = ParsedBugreport(logcat=parse_buffer(sample_logcat))
    summary = generate_summary(parsed)
    assert isinstance(summary.top_errors, list)
