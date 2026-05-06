from androbugger.parser.tombstone import parse_tombstone


def test_parse_tombstone(sample_tombstone):
    t = parse_tombstone(sample_tombstone)
    assert t.pid == 1234
    assert t.signal == "11"
    assert t.signal_name == "SIGSEGV"
    assert len(t.backtrace) == 3
    assert "libfoo.so" in t.backtrace[0].library
    assert len(t.memory_map) >= 1


def test_tombstone_graceful_on_empty():
    t = parse_tombstone("")
    assert t.pid == 0
    assert t.signal == ""
    assert t.backtrace == []
