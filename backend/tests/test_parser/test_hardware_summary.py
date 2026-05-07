"""Tests for the hardware summary parser."""
import pytest

from androbugger.parser.hardware_summary import (
    HardwareSummary, SubsystemStatus, parse_hardware_results
)


def _result(raw: dict) -> HardwareSummary:
    return parse_hardware_results(raw)


# ── sensors ───────────────────────────────────────────────────────────────────

def test_sensors_empty_fail():
    r = _result({"sensors": ""})
    sub = next(s for s in r.subsystems if s.name == "sensors")
    assert sub.status == "fail"


def test_sensors_no_sensor_text_fail():
    r = _result({"sensors": "no sensor registered"})
    sub = next(s for s in r.subsystems if s.name == "sensors")
    assert sub.status == "fail"


def test_sensors_pass():
    r = _result({"sensors": "Sensor List:\n  0 | Accelerometer | WAKE_UP | 3 | vendor"})
    sub = next(s for s in r.subsystems if s.name == "sensors")
    assert sub.status == "pass"


# ── storage ───────────────────────────────────────────────────────────────────

def test_storage_critical_usage():
    df = "/dev/sda5  10G  9.6G  400M  97% /data"
    r = _result({"storage": df})
    sub = next(s for s in r.subsystems if s.name == "storage")
    assert sub.status == "fail"
    assert any("97%" in a for a in sub.anomalies)


def test_storage_high_usage_warning():
    df = "/dev/sda5  10G  8.7G  1.3G  87% /data"
    r = _result({"storage": df})
    sub = next(s for s in r.subsystems if s.name == "storage")
    assert sub.status == "warning"


def test_storage_normal():
    df = "/dev/sda5  10G  5G  5G  50% /data"
    r = _result({"storage": df})
    sub = next(s for s in r.subsystems if s.name == "storage")
    assert sub.status == "pass"


# ── network ───────────────────────────────────────────────────────────────────

def test_network_packet_loss_fail():
    r = _result({"network": "3 packets transmitted, 0 received, 100% packet loss"})
    sub = next(s for s in r.subsystems if s.name == "network")
    assert sub.status == "fail"
    assert any("100% packet loss" in a for a in sub.anomalies)


def test_network_high_latency_warning():
    r = _result({"network": "rtt min/avg/max/mdev = 10.0/600.0/1200.0/5.0 ms"})
    sub = next(s for s in r.subsystems if s.name == "network")
    assert sub.status == "warning"


def test_network_good():
    r = _result({"network": "rtt min/avg/max/mdev = 5.0/15.0/30.0/2.0 ms"})
    sub = next(s for s in r.subsystems if s.name == "network")
    assert sub.status == "pass"


# ── touch ─────────────────────────────────────────────────────────────────────

def test_touch_no_abs_mt_fail():
    r = _result({"touch": "getevent output with no multitouch events"})
    sub = next(s for s in r.subsystems if s.name == "touch")
    assert sub.status == "fail"


def test_touch_with_abs_mt_pass():
    r = _result({"touch": "ABS_MT_POSITION_X\n  BTN_TOUCH\n  add device 1: /dev/input/event0"})
    sub = next(s for s in r.subsystems if s.name == "touch")
    assert sub.status == "pass"


# ── USB ───────────────────────────────────────────────────────────────────────

def test_usb_configured_pass():
    r = _result({"usb": "mCurrentFunctions=mtp\nmUsbState=CONFIGURED"})
    sub = next(s for s in r.subsystems if s.name == "usb")
    assert sub.status == "pass"


def test_usb_disconnected_fail():
    r = _result({"usb": "mUsbState=disconnected"})
    sub = next(s for s in r.subsystems if s.name == "usb")
    assert sub.status == "fail"


# ── overall status ─────────────────────────────────────────────────────────────

def test_overall_fail_if_any_subsystem_fails():
    raw = {
        "sensors": "",  # fail
        "display": "Physical size: 1920x1080",
        "touch": "ABS_MT_POSITION_X",
        "storage": "/dev/sda5  10G  5G  5G  50% /data",
        "network": "rtt min/avg/max/mdev = 5/10/20/1 ms",
        "usb": "CONFIGURED",
    }
    r = _result(raw)
    assert r.overall_status == "fail"


def test_overall_warning_if_warning_but_no_fail():
    raw = {
        "sensors": "ABS_MT_POSITION_X sensor data",
        "display": "Physical size: 1920x1080",
        "touch": "ABS_MT_POSITION_X",
        "storage": "/dev/sda5  10G  8.7G  1.3G  87% /data",  # warning
        "network": "rtt min/avg/max/mdev = 5/10/20/1 ms",
        "usb": "CONFIGURED",
    }
    r = _result(raw)
    assert r.overall_status == "warning"


def test_overall_pass_all_good():
    raw = {
        "sensors": "0 | Accelerometer",
        "display": "Physical size: 1920x1080",
        "touch": "ABS_MT_POSITION_X BTN_TOUCH",
        "storage": "/dev/sda5  10G  5G  5G  50% /data",
        "network": "rtt min/avg/max/mdev = 5/10/20/1 ms",
        "usb": "CONFIGURED",
    }
    r = _result(raw)
    assert r.overall_status == "pass"
