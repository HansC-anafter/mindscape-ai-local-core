"""Singleflight pgvector readiness for backend health readers."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from threading import Condition
from typing import Any, Callable

from backend.app.database.vector_connection import get_vector_dbapi_connection

_READINESS_SQL = """
    SELECT
        EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector') AS installed,
        (SELECT extversion FROM pg_extension WHERE extname = 'vector' LIMIT 1) AS version
"""
_CONNECTION_TEST_SQL = """
    SELECT
        EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector') AS installed,
        (SELECT extversion FROM pg_extension WHERE extname = 'vector' LIMIT 1) AS version,
        (
            SELECT atttypmod - 4
            FROM pg_attribute
            WHERE attrelid = to_regclass('mindscape_personal')
              AND attname = 'embedding'
              AND atttypmod > 0
            LIMIT 1
        ) AS dimension
"""


@dataclass(frozen=True)
class VectorReadinessResult:
    connected: bool
    pgvector_installed: bool
    pgvector_version: str | None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class VectorReadinessProbe:
    """Cache one vector readiness result and coalesce concurrent worker threads."""

    def __init__(
        self,
        *,
        connection_factory: Callable[[], Any] = get_vector_dbapi_connection,
        ttl_seconds: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._connection_factory = connection_factory
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._condition = Condition()
        self._inflight = False
        self._cached_at = 0.0
        self._cached_result: VectorReadinessResult | None = None

    def check(self, *, force: bool = False) -> VectorReadinessResult:
        with self._condition:
            cached = self._fresh_cached_result()
            if cached is not None and not force:
                return cached
            if self._inflight:
                self._condition.wait_for(lambda: not self._inflight)
                if self._cached_result is None:
                    raise RuntimeError("vector_readiness_result_missing")
                return self._cached_result
            self._inflight = True

        result = self._execute_once()
        with self._condition:
            self._cached_result = result
            self._cached_at = self._clock()
            self._inflight = False
            self._condition.notify_all()
        return result

    def _fresh_cached_result(self) -> VectorReadinessResult | None:
        if self._cached_result is None:
            return None
        if self._clock() - self._cached_at >= self._ttl_seconds:
            return None
        return self._cached_result

    def _execute_once(self) -> VectorReadinessResult:
        connection = None
        cursor = None
        try:
            connection = self._connection_factory()
            cursor = connection.cursor()
            cursor.execute(_READINESS_SQL)
            row = cursor.fetchone()
            installed = bool(row and row[0])
            version = str(row[1]) if row and row[1] is not None else None
            return VectorReadinessResult(
                connected=installed,
                pgvector_installed=installed,
                pgvector_version=version,
            )
        except Exception as exc:
            return VectorReadinessResult(
                connected=False,
                pgvector_installed=False,
                pgvector_version=None,
                error=str(exc),
            )
        finally:
            if cursor is not None:
                try:
                    cursor.close()
                except Exception:
                    pass
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass


_VECTOR_READINESS_PROBE = VectorReadinessProbe()


def get_vector_readiness(*, force: bool = False) -> VectorReadinessResult:
    return _VECTOR_READINESS_PROBE.check(force=force)


def run_vector_connection_test(
    postgres_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run one fresh connection and one query for explicit diagnostics."""
    connection = None
    cursor = None
    try:
        connection = get_vector_dbapi_connection(postgres_config)
        cursor = connection.cursor()
        cursor.execute(_CONNECTION_TEST_SQL)
        row = cursor.fetchone()
        installed = bool(row and row[0])
        version = str(row[1]) if row and row[1] is not None else None
        dimension = int(row[2]) if row and row[2] is not None else None
        return {
            "success": True,
            "connected": True,
            "pgvector_installed": installed,
            "pgvector_version": version,
            "dimension_check": dimension is not None,
            "dimension": dimension,
            "dimension_error": None,
        }
    except Exception as exc:
        return {
            "success": False,
            "connected": False,
            "error": f"Connection failed: {exc}",
            "pgvector_installed": False,
        }
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass


def reset_vector_readiness_probe() -> None:
    global _VECTOR_READINESS_PROBE
    _VECTOR_READINESS_PROBE = VectorReadinessProbe()


__all__ = [
    "VectorReadinessProbe",
    "VectorReadinessResult",
    "get_vector_readiness",
    "reset_vector_readiness_probe",
    "run_vector_connection_test",
]
