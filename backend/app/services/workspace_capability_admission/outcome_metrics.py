"""Bounded in-process counters for shadow admission outcomes."""

from __future__ import annotations

from collections import Counter
from threading import Lock

from .contracts import AdmissionAvailability


_lock = Lock()
_shadow_outcomes: Counter[str] = Counter()


def record_shadow_outcome(outcome: AdmissionAvailability) -> None:
    with _lock:
        _shadow_outcomes[outcome] += 1


def shadow_outcome_snapshot() -> dict[str, int]:
    with _lock:
        return dict(_shadow_outcomes)
