from datetime import timezone

from backend.app.runner.worker import _parse_utc_iso, _utc_now


def test_parse_utc_iso_naive_input_becomes_utc_aware():
    dt = _parse_utc_iso("2026-02-27T16:34:43")
    assert dt is not None
    assert dt.tzinfo is not None
    assert dt.utcoffset() == timezone.utc.utcoffset(dt)


def test_parse_utc_iso_explicit_utc_keeps_timezone():
    dt = _parse_utc_iso("2026-02-27T16:34:43+00:00")
    assert dt is not None
    assert dt.tzinfo is not None
    assert dt.utcoffset() == timezone.utc.utcoffset(dt)


def test_parse_utc_iso_invalid_returns_none():
    assert _parse_utc_iso(None) is None
    assert _parse_utc_iso("") is None
    assert _parse_utc_iso("invalid") is None


def test_utc_now_is_timezone_aware():
    now = _utc_now()
    assert now.tzinfo is not None
    assert now.utcoffset() == timezone.utc.utcoffset(now)
