"""Strict payload-free projection for sender-target correlation."""

from __future__ import annotations

from typing import Any, Mapping


FORMAL_CORRELATION_DEADLINE_SECONDS = 10.0
FORMAL_CORRELATION_POLL_SECONDS = 0.25
_DETAIL_CODES = frozenset(
    {
        "formal_correlation_event_not_observed",
        "formal_correlation_event_invalid",
        "formal_correlation_target_not_observed",
        "formal_correlation_pgbouncer_unavailable",
    }
)
_COUNT_KEYS = (
    "event_file_count",
    "parsed_event_count",
    "target_match_count",
    "correlated_match_count",
)
_SOURCE_KEYS = frozenset(
    {
        "passed",
        "gate",
        "detail_code",
        "terminal_deadline_seconds",
        "poll_seconds",
        *_COUNT_KEYS,
    }
)


def project_correlation_gate_receipt(name: str, source: object) -> dict[str, Any]:
    invalid = {
        "name": name,
        "kind": "gate",
        "passed": False,
        "detail_code": "formal_correlation_receipt_invalid",
    }
    if not isinstance(source, Mapping) or set(source) != _SOURCE_KEYS:
        return invalid
    passed = source.get("passed")
    detail = source.get("detail_code")
    if (
        source.get("gate") != name
        or type(passed) is not bool
        or not (detail is None or (type(detail) is str and detail in _DETAIL_CODES))
        or type(source.get("terminal_deadline_seconds")) is not float
        or source.get("terminal_deadline_seconds")
        != FORMAL_CORRELATION_DEADLINE_SECONDS
        or type(source.get("poll_seconds")) is not float
        or source.get("poll_seconds") != FORMAL_CORRELATION_POLL_SECONDS
        or any(type(source.get(key)) is not int for key in _COUNT_KEYS)
    ):
        return invalid
    events, parsed, targets, correlated = (source[key] for key in _COUNT_KEYS)
    if not (0 <= correlated <= targets <= parsed <= events):
        return invalid
    expected_detail = (
        None
        if correlated > 0
        else "formal_correlation_event_not_observed"
        if events == 0
        else "formal_correlation_event_invalid"
        if parsed == 0
        else "formal_correlation_target_not_observed"
        if targets == 0
        else "formal_correlation_pgbouncer_unavailable"
    )
    if passed is not (correlated > 0) or detail != expected_detail:
        return invalid
    return {
        "name": name,
        "kind": "gate",
        "passed": passed,
        "detail_code": detail,
        "terminal_deadline_seconds": FORMAL_CORRELATION_DEADLINE_SECONDS,
        "poll_seconds": FORMAL_CORRELATION_POLL_SECONDS,
        **{key: source[key] for key in _COUNT_KEYS},
    }
