"""Event-driven, payload-free PostgreSQL unexpected-close evidence."""

from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from typing import Any, Callable

from sqlalchemy import event
from sqlalchemy.engine import Engine

from backend.app.database.recovery_backoff import (
    DatabaseFailureCode,
    classify_database_error,
)


RecordFailure = Callable[..., Any]
_DATABASE_ROLES = frozenset(
    {"core", "vector", "core-readonly", "vector-readonly", "session"}
)
logger = logging.getLogger(__name__)


def _statement_digest(statement: Any) -> tuple[str, str]:
    if statement is None:
        return "", "0"
    if isinstance(statement, bytes):
        payload = statement
    else:
        payload = str(statement).encode("utf-8", errors="replace")
    return hashlib.sha256(payload).hexdigest(), str(len(payload))


def _database_role(application_name: str) -> str:
    role = str(application_name).rsplit(":", 1)[-1]
    return role if role in _DATABASE_ROLES else "unspecified"


def _burst_fingerprint(evidence: dict[str, str]) -> str:
    identity = (
        evidence["application_name"],
        evidence["client_process_pid"],
        evidence["database_role"],
        evidence["exception_class"],
        evidence["failure_code"],
    )
    return hashlib.sha256("\x1f".join(identity).encode("utf-8")).hexdigest()


class QueryFailureEvidenceRecorder:
    """Record one redacted event per bounded unexpected-close burst."""

    def __init__(
        self,
        *,
        application_name: str,
        record_failure: RecordFailure,
        monotonic: Callable[[], float] = time.monotonic,
        burst_seconds: float = 30.0,
    ) -> None:
        self.application_name = str(application_name).strip() or "unidentified"
        self.record_failure = record_failure
        self.monotonic = monotonic
        self.burst_seconds = max(1.0, float(burst_seconds))
        self._lock = threading.Lock()
        self._last_fingerprint = ""
        self._last_recorded_at = 0.0

    def observe(
        self,
        exc: BaseException,
        *,
        statement: Any = None,
    ) -> bool:
        classification = classify_database_error(exc)
        if (
            classification.code
            is not DatabaseFailureCode.POSTGRES_SERVER_CLOSED_UNEXPECTEDLY
        ):
            return False
        statement_sha256, statement_bytes = _statement_digest(statement)
        evidence = {
            "application_name": self.application_name,
            "client_process_pid": str(os.getpid()),
            "database_role": _database_role(self.application_name),
            "exception_class": type(exc).__qualname__,
            "failure_code": classification.code.value,
            "statement_sha256": statement_sha256,
            "statement_bytes": statement_bytes,
        }
        fingerprint = _burst_fingerprint(evidence)
        now = self.monotonic()
        with self._lock:
            if (
                fingerprint == self._last_fingerprint
                and now - self._last_recorded_at < self.burst_seconds
            ):
                return False
            self.record_failure(
                classification.code.value,
                evidence=evidence,
            )
            self._last_fingerprint = fingerprint
            self._last_recorded_at = now
        return True


def attach_query_failure_evidence(
    engine: Engine,
    *,
    application_name: str,
) -> QueryFailureEvidenceRecorder:
    """Attach one SQLAlchemy handle_error listener without a timer or thread."""

    from backend.app.services.runtime_database_incident_gate import (
        record_database_failure,
    )

    recorder = QueryFailureEvidenceRecorder(
        application_name=application_name,
        record_failure=record_database_failure,
    )

    def _handle_error(context: Any) -> None:
        original = getattr(context, "original_exception", None)
        sqlalchemy_error = getattr(context, "sqlalchemy_exception", None)
        error = original or sqlalchemy_error
        if isinstance(error, BaseException):
            try:
                recorder.observe(
                    error,
                    statement=getattr(context, "statement", None),
                )
            except Exception:
                logger.error("Unable to persist redacted database failure evidence")

    event.listen(engine, "handle_error", _handle_error)
    return recorder
