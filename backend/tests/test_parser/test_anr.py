from androbugger.parser.anr import parse_anr_file


def test_parse_anr(sample_anr):
    trace = parse_anr_file(sample_anr)
    assert "com.example.app" in trace.process
    assert trace.pid == 1234


def test_anr_graceful_on_empty():
    trace = parse_anr_file("")
    assert trace.process == ""
    assert trace.pid == 0
