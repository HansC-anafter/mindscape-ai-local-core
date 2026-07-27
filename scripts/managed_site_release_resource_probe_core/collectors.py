"""Bounded read-only PostgreSQL, PgBouncer, and worker collectors."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from typing import Any
from urllib.parse import urlparse

import psycopg2
import redis

_POSTGRES_METRICS_SQL = """
SELECT
  (SELECT count(*) FROM pg_stat_activity)::bigint AS connections,
  (
    SELECT count(*) FROM pg_stat_activity
    WHERE state = 'active' AND pid <> pg_backend_pid()
  )::bigint AS active,
  (
    SELECT count(*) FROM pg_stat_activity
    WHERE state = 'idle in transaction'
  )::bigint AS idle_transaction,
  (
    SELECT count(*) FROM pg_locks WHERE NOT granted
  )::bigint AS waiting_locks,
  (
    SELECT count(*) FROM pg_stat_activity
    WHERE xact_start IS NOT NULL
      AND pid <> pg_backend_pid()
      AND clock_timestamp() - xact_start > interval '60 seconds'
  )::bigint AS long_transactions
"""
_QUEUE_KEY = re.compile(
    r"^mindscape:queue:(pending|processing|delayed|temp):"
    r"[a-zA-Z0-9._-]{1,128}$"
)
_MAX_QUEUE_KEYS = 4096
_PGBOUNCER_SAMPLES = 3
_PGBOUNCER_SAMPLE_INTERVAL_SECONDS = 0.25
_RUNNER_FRESH_SECONDS = 45


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _postgres_url(name: str) -> str:
    value = os.environ.get(name, "")
    parsed = urlparse(value)
    if (
        parsed.scheme not in {"postgres", "postgresql"}
        or not parsed.hostname
        or not parsed.path.strip("/")
    ):
        raise RuntimeError(f"managed_resource_probe_{name.lower()}_invalid")
    return value


def _connect_postgres(dsn: str):
    connection = psycopg2.connect(
        dsn,
        connect_timeout=3,
        options=(
            "-c statement_timeout=3000 "
            "-c default_transaction_read_only=on "
            "-c idle_in_transaction_session_timeout=3000"
        ),
    )
    connection.autocommit = True
    return connection


def _connect_pgbouncer(dsn: str):
    connection = psycopg2.connect(
        dsn,
        connect_timeout=3,
    )
    connection.autocommit = True
    return connection


class RuntimeResourceCollectors:
    """Collect exact raw values without changing runtime configuration."""

    def database(self) -> dict[str, int]:
        with _connect_postgres(
            _postgres_url("DATABASE_URL_CORE_SESSION")
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute(_POSTGRES_METRICS_SQL)
                row = cursor.fetchone()
        if not isinstance(row, tuple) or len(row) != 5:
            raise RuntimeError(
                "managed_resource_probe_database_metrics_invalid"
            )
        values = tuple(int(value) for value in row)
        if any(value < 0 for value in values):
            raise RuntimeError(
                "managed_resource_probe_database_metrics_invalid"
            )
        return dict(
            zip(
                (
                    "connections",
                    "active",
                    "idle_transaction",
                    "waiting_locks",
                    "long_transactions",
                ),
                values,
            )
        )

    def pgbouncer(
        self,
        *,
        include_samples: bool,
    ) -> dict[str, Any]:
        dsn = _postgres_url("PGBOUNCER_ADMIN_URL")
        with _connect_pgbouncer(dsn) as connection:
            config_rows = self._pgbouncer_config(connection)
            result: dict[str, Any] = {
                "config_sha256": _canonical_sha256(config_rows)
            }
            if include_samples:
                result.update(self._pgbouncer_samples(connection))
        return result

    @staticmethod
    def _pgbouncer_config(connection) -> list[dict[str, Any]]:
        with connection.cursor() as cursor:
            cursor.execute("SHOW CONFIG")
            columns = [item.name for item in cursor.description]
            rows = cursor.fetchall()
        required = {"key", "value", "default", "changeable"}
        if not required.issubset(columns) or not rows:
            raise RuntimeError(
                "managed_resource_probe_pgbouncer_config_invalid"
            )
        indexes = {name: columns.index(name) for name in required}
        return [
            {
                name: str(row[indexes[name]])
                for name in sorted(required)
            }
            for row in rows
        ]

    @staticmethod
    def _pgbouncer_samples(connection) -> dict[str, int]:
        client_waiting_max = 0
        max_wait_seconds = 0
        for index in range(_PGBOUNCER_SAMPLES):
            with connection.cursor() as cursor:
                cursor.execute("SHOW POOLS")
                columns = [item.name for item in cursor.description]
                rows = cursor.fetchall()
            required = {
                "database",
                "cl_waiting",
                "maxwait",
                "maxwait_us",
            }
            if not required.issubset(columns) or not rows:
                raise RuntimeError(
                    "managed_resource_probe_pgbouncer_pools_invalid"
                )
            positions = {
                name: columns.index(name) for name in required
            }
            selected = [
                row
                for row in rows
                if str(row[positions["database"]])
                in {
                    "mindscape_core",
                    "mindscape_core_readonly",
                    "mindscape_vectors",
                    "mindscape_vectors_readonly",
                }
            ]
            if not selected:
                raise RuntimeError(
                    "managed_resource_probe_pgbouncer_pools_empty"
                )
            client_waiting_max = max(
                client_waiting_max,
                *(
                    int(row[positions["cl_waiting"]])
                    for row in selected
                ),
            )
            max_wait_seconds = max(
                max_wait_seconds,
                *(
                    int(row[positions["maxwait"]])
                    + int(int(row[positions["maxwait_us"]]) > 0)
                    for row in selected
                ),
            )
            if index + 1 < _PGBOUNCER_SAMPLES:
                time.sleep(_PGBOUNCER_SAMPLE_INTERVAL_SECONDS)
        return {
            "sample_count": _PGBOUNCER_SAMPLES,
            "client_waiting_max": client_waiting_max,
            "max_wait_seconds": max_wait_seconds,
        }

    def worker(self) -> dict[str, int]:
        process_count = self._runner_process_count()
        queue_depth = self._queue_depth()
        return {
            "process_count": process_count,
            "queue_depth": queue_depth,
        }

    @staticmethod
    def _runner_process_count() -> int:
        with _connect_postgres(
            _postgres_url("DATABASE_URL_CORE_SESSION")
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT count(DISTINCT runner_id)::bigint
                    FROM runner_heartbeats
                    WHERE heartbeat_at >
                      clock_timestamp() - interval '1 second' * %s
                    """,
                    (_RUNNER_FRESH_SECONDS,),
                )
                row = cursor.fetchone()
        if not isinstance(row, tuple) or len(row) != 1:
            raise RuntimeError(
                "managed_resource_probe_runner_metrics_invalid"
            )
        value = int(row[0])
        if value < 1:
            raise RuntimeError(
                "managed_resource_probe_no_fresh_runners"
            )
        return value

    @staticmethod
    def _queue_depth() -> int:
        client = redis.Redis(
            host=os.environ.get("REDIS_HOST", "redis"),
            port=int(os.environ.get("REDIS_PORT", "6379")),
            db=int(os.environ.get("REDIS_DB", "0")),
            password=os.environ.get("REDIS_PASSWORD") or None,
            socket_connect_timeout=3,
            socket_timeout=3,
            decode_responses=True,
        )
        if client.ping() is not True:
            raise RuntimeError(
                "managed_resource_probe_redis_unavailable"
            )
        cursor = 0
        keys: list[str] = []
        while True:
            cursor, batch = client.scan(
                cursor=cursor,
                match="mindscape:queue:*",
                count=100,
            )
            keys.extend(str(key) for key in batch)
            if len(keys) > _MAX_QUEUE_KEYS:
                raise RuntimeError(
                    "managed_resource_probe_queue_key_budget_exceeded"
                )
            if cursor == 0:
                break
        selected = sorted(
            key for key in set(keys) if _QUEUE_KEY.fullmatch(key)
        )
        pipeline = client.pipeline(transaction=False)
        types: list[str] = []
        for key in selected:
            queue_kind = key.split(":", 3)[2]
            types.append(queue_kind)
            if queue_kind in {"pending", "temp"}:
                pipeline.llen(key)
            else:
                pipeline.zcard(key)
        values = pipeline.execute()
        if len(values) != len(selected):
            raise RuntimeError(
                "managed_resource_probe_queue_metrics_invalid"
            )
        depths = [int(value) for value in values]
        if any(value < 0 for value in depths):
            raise RuntimeError(
                "managed_resource_probe_queue_metrics_invalid"
            )
        return sum(depths)
