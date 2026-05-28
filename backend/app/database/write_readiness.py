"""Core PostgreSQL write-readiness checks for mutating workflows."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.database.config import get_postgres_url_core
from backend.app.database.recovery_backoff import is_database_recovery_error


def _retry_after_seconds() -> int:
    try:
        return max(1, int(os.getenv("DB_RECOVERY_BACKOFF_SECONDS", "30")))
    except ValueError:
        return 30


@dataclass(frozen=True)
class DatabaseWriteReadiness:
    """Result of a core PostgreSQL write-readiness probe."""

    ready: bool
    reason: str
    retry_after_seconds: int = field(default_factory=_retry_after_seconds)
    details: Dict[str, Any] = field(default_factory=dict)


class DatabaseWriteNotReadyError(RuntimeError):
    """Raised when a mutating workflow must wait for writable PostgreSQL."""

    def __init__(self, readiness: DatabaseWriteReadiness):
        self.readiness = readiness
        super().__init__(readiness.reason)


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "t", "true", "yes", "on"}


def check_core_write_readiness(
    *,
    operation: str = "core_write",
    engine_factory: Optional[Callable[[str], Engine]] = None,
) -> DatabaseWriteReadiness:
    """Probe whether core PostgreSQL currently accepts writes."""

    engine: Optional[Engine] = None
    try:
        url = get_postgres_url_core()
        factory = engine_factory or create_engine
        engine = factory(url)
        with engine.connect() as conn:
            in_recovery = _coerce_bool(
                conn.execute(text("SELECT pg_is_in_recovery()")).scalar()
            )
            read_only = _coerce_bool(
                conn.execute(text("SHOW transaction_read_only")).scalar()
            )
            conn.execute(text("SELECT 1"))
        if in_recovery:
            return DatabaseWriteReadiness(
                ready=False,
                reason="postgres_recovery_in_progress",
                details={"operation": operation, "pg_is_in_recovery": True},
            )
        if read_only:
            return DatabaseWriteReadiness(
                ready=False,
                reason="postgres_transaction_read_only",
                details={"operation": operation, "transaction_read_only": True},
            )
        return DatabaseWriteReadiness(
            ready=True,
            reason="ready",
            retry_after_seconds=0,
            details={"operation": operation},
        )
    except Exception as exc:
        reason = (
            "postgres_recovery_in_progress"
            if is_database_recovery_error(exc)
            else "postgres_write_probe_failed"
        )
        return DatabaseWriteReadiness(
            ready=False,
            reason=reason,
            details={"operation": operation, "error": str(exc)},
        )
    finally:
        if engine is not None:
            engine.dispose()


def ensure_core_write_ready(
    *,
    operation: str = "core_write",
) -> DatabaseWriteReadiness:
    """Return readiness or raise when core PostgreSQL cannot accept writes."""

    readiness = check_core_write_readiness(operation=operation)
    if not readiness.ready:
        raise DatabaseWriteNotReadyError(readiness)
    return readiness


def wait_for_core_write_readiness(
    *,
    operation: str,
    timeout_seconds: int,
    poll_interval_seconds: float,
) -> DatabaseWriteReadiness:
    """Wait until core PostgreSQL accepts writes or raise after timeout."""

    deadline = time.monotonic() + max(0, timeout_seconds)
    last_readiness: Optional[DatabaseWriteReadiness] = None
    while True:
        readiness = check_core_write_readiness(operation=operation)
        if readiness.ready:
            return readiness
        last_readiness = readiness
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise DatabaseWriteNotReadyError(readiness)
        time.sleep(min(max(0.1, poll_interval_seconds), remaining))

    raise DatabaseWriteNotReadyError(
        last_readiness
        or DatabaseWriteReadiness(
            ready=False,
            reason="postgres_write_probe_timeout",
        )
    )
