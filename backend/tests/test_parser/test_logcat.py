from androbugger.parser.logcat import parse_line, parse_buffer, filter_by_level, error_frequency


def test_parse_valid_line():
    line = "05-01 12:00:03.000  1234  1235 E AndroidRuntime: FATAL EXCEPTION"
    entry = parse_line(line)
    assert entry is not None
    assert entry.pid == 1234
    assert entry.level == "E"
    assert entry.tag == "AndroidRuntime"
    assert "FATAL" in entry.msg


def test_parse_invalid_line():
    assert parse_line("not a logcat line") is None
    assert parse_line("") is None


def test_parse_buffer(sample_logcat):
    entries = parse_buffer(sample_logcat)
    assert len(entries) >= 5


def test_filter_by_level(sample_logcat):
    entries = parse_buffer(sample_logcat)
    errors = filter_by_level(entries, "E")
    assert all(e.level in ("E", "F") for e in errors)


def test_error_frequency(sample_logcat):
    entries = parse_buffer(sample_logcat)
    freq = error_frequency(entries)
    assert isinstance(freq, list)
    if freq:
        assert "tag" in freq[0]
        assert "count" in freq[0]
