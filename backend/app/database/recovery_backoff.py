"""Shared PostgreSQL recovery backoff helpers."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)

class DatabaseFailureCode(str, Enum):
    """Stable database failure codes shared by API, worker, and maintenance callers."""

    POSTGRES_SERVER_CLOSED_UNEXPECTEDLY = "postgres_server_closed_unexpectedly"
    POSTGRES_STARTUP_RECOVERY = "postgres_startup_recovery"
    POSTGRES_READ_ONLY = "postgres_read_only"
    PGBOUNCER_UNAVAILABLE = "pgbouncer_unavailable"
    SQL_APPLICATION_ERROR = "sql_application_error"


@dataclass(frozen=True)
class DatabaseFailureClassification:
    """Classification result without exposing raw exception text to callers."""

    code: DatabaseFailureCode
    recovery_related: bool
    opens_incident: bool


_UNEXPECTED_CLOSE_MARKERS = (
    "server closed the connection unexpectedly",
    "ssl syscall error: eof detected",
    "connection reset by peer",
)

_STARTUP_RECOVERY_MARKERS = (
    "database system is in recovery mode",
    "database system is not yet accepting connections",
    "consistent recovery state has not been yet reached",
    "the database system is starting up",
)

_READ_ONLY_MARKERS = (
    "cannot execute",
    "in a read-only transaction",
    "transaction_read_only",
)

_PGBOUNCER_MARKERS = (
    "pgbouncer",
    "query_wait_timeout",
    "no more connections allowed",
    "server login has been failing",
)


def _exception_chain_text(exc: BaseException) -> str:
    parts: list[str] = []
    seen: set[int] = set()
    current: Optional[BaseException] = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        parts.append(str(current))
        current = current.__cause__ or current.__context__
    return "\n".join(parts)


def classify_database_error(exc: BaseException) -> DatabaseFailureClassification:
    """Classify nested SQLAlchemy/driver failures using one stable code set."""

    message = _exception_chain_text(exc).lower()
    if any(marker in message for marker in _UNEXPECTED_CLOSE_MARKERS):
        return DatabaseFailureClassification(
            code=DatabaseFailureCode.POSTGRES_SERVER_CLOSED_UNEXPECTEDLY,
            recovery_related=True,
            opens_incident=True,
        )
    if any(marker in message for marker in _STARTUP_RECOVERY_MARKERS):
        return DatabaseFailureClassification(
            code=DatabaseFailureCode.POSTGRES_STARTUP_RECOVERY,
            recovery_related=True,
            opens_incident=False,
        )
    if all(marker in message for marker in _READ_ONLY_MARKERS[:2]) or (
        _READ_ONLY_MARKERS[2] in message
    ):
        return DatabaseFailureClassification(
            code=DatabaseFailureCode.POSTGRES_READ_ONLY,
            recovery_related=True,
            opens_incident=False,
        )
    if any(marker in message for marker in _PGBOUNCER_MARKERS):
        return DatabaseFailureClassification(
            code=DatabaseFailureCode.PGBOUNCER_UNAVAILABLE,
            recovery_related=True,
            opens_incident=False,
        )
    return DatabaseFailureClassification(
        code=DatabaseFailureCode.SQL_APPLICATION_ERROR,
        recovery_related=False,
        opens_incident=False,
    )


def is_database_recovery_error(exc: BaseException) -> bool:
    return classify_database_error(exc).recovery_related


@dataclass
class DatabaseRecoveryBackoff:
    delay_seconds: int
    log_interval_seconds: int = 30

    def __post_init__(self) -> None:
        self.delay_seconds = max(1, int(self.delay_seconds or 1))
        self.log_interval_seconds = max(1, int(self.log_interval_seconds or 1))
        self._until_monotonic = 0.0
        self._next_log_monotonic = 0.0

    def note_failure(self, exc: BaseException) -> bool:
        classification = classify_database_error(exc)
        if not classification.recovery_related:
            return False
        if classification.opens_incident:
            try:
                from backend.app.services.runtime_database_incident_gate import (
                    record_database_failure,
                )

                record_database_failure(classification.code.value)
            except Exception:
                logger.exception(
                    "Unable to persist runtime database incident; mutation gate will fail closed"
                )
        now = time.monotonic()
        self._until_monotonic = max(
            self._until_monotonic,
            now + float(self.delay_seconds),
        )
        return True

    def is_active(self) -> bool:
        return self.remaining_seconds() > 0

    def remaining_seconds(self) -> float:
        return max(0.0, self._until_monotonic - time.monotonic())

    def should_log(self) -> bool:
        now = time.monotonic()
        if now < self._next_log_monotonic:
            return False
        self._next_log_monotonic = now + float(self.log_interval_seconds)
        return True

    def wait_if_active(self, *, label: str) -> None:
        remaining = self.remaining_seconds()
        if remaining <= 0:
            return
        if self.should_log():
            logger.warning(
                "%s paused while PostgreSQL is recovering; remaining_backoff=%.1fs",
                label,
                remaining,
            )
        time.sleep(min(remaining, float(self.delay_seconds)))
