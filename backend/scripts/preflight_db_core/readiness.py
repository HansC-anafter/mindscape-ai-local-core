"""Bounded startup probe policy shared by database and schema checks."""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional, TypeVar

from backend.app.database.recovery_backoff import (
    DatabaseFailureCode,
    classify_database_error,
)


class DatabaseProbeState(str, Enum):
    READY = "ready"
    RECOVERING = "recovering"
    UNAVAILABLE = "unavailable"
    AUTH_FAILED = "auth_failed"
    SCHEMA_MISSING = "schema_missing"


@dataclass(frozen=True)
class DatabaseProbeResult:
    state: DatabaseProbeState
    attempts: int
    elapsed_seconds: float
    failure_code: Optional[str] = None
    missing_tables: tuple[str, ...] = ()


_AUTH_MARKERS = (
    "password authentication failed",
    "no pg_hba.conf entry",
    "authentication failed",
)


def classify_probe_exception(exc: BaseException) -> DatabaseProbeState:
    message = str(exc).lower()
    if any(marker in message for marker in _AUTH_MARKERS):
        return DatabaseProbeState.AUTH_FAILED
    classification = classify_database_error(exc)
    if classification.code in {
        DatabaseFailureCode.POSTGRES_STARTUP_RECOVERY,
        DatabaseFailureCode.POSTGRES_SERVER_CLOSED_UNEXPECTEDLY,
        DatabaseFailureCode.POSTGRES_READ_ONLY,
    }:
        return DatabaseProbeState.RECOVERING
    return DatabaseProbeState.UNAVAILABLE


T = TypeVar("T")


def run_bounded_database_probe(
    probe: Callable[[], T],
    *,
    timeout_seconds: float = 120.0,
    delay_schedule: tuple[float, ...] = (1, 2, 4, 8, 10),
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> tuple[DatabaseProbeResult, Optional[T]]:
    """Retry recovery/unavailable probes, but fail authentication immediately."""

    started = monotonic()
    attempts = 0
    last_state = DatabaseProbeState.UNAVAILABLE
    last_code: Optional[str] = None
    while True:
        attempts += 1
        try:
            value = probe()
            return (
                DatabaseProbeResult(
                    state=DatabaseProbeState.READY,
                    attempts=attempts,
                    elapsed_seconds=max(0.0, monotonic() - started),
                ),
                value,
            )
        except Exception as exc:
            last_state = classify_probe_exception(exc)
            last_code = classify_database_error(exc).code.value
            elapsed = max(0.0, monotonic() - started)
            if last_state is DatabaseProbeState.AUTH_FAILED:
                return (
                    DatabaseProbeResult(
                        state=last_state,
                        attempts=attempts,
                        elapsed_seconds=elapsed,
                        failure_code=last_code,
                    ),
                    None,
                )
            delay = delay_schedule[min(attempts - 1, len(delay_schedule) - 1)]
            if elapsed + delay > timeout_seconds:
                return (
                    DatabaseProbeResult(
                        state=last_state,
                        attempts=attempts,
                        elapsed_seconds=elapsed,
                        failure_code=last_code,
                    ),
                    None,
                )
            sleep(delay)
