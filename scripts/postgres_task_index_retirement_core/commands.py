"""Database commands for one exact task-index retirement or backout."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from sqlalchemy import text

from backend.app.database.task_index_manifest import retirement_target


PREFLIGHT_SQL = text(
    """
    SELECT
      pg_is_in_recovery() AS in_recovery,
      current_setting('transaction_read_only') AS read_only,
      (SELECT count(*) FROM pg_index WHERE NOT indisvalid OR NOT indisready)
        AS invalid_indexes,
      (SELECT failed_count FROM pg_stat_archiver) AS archive_failures,
      (
        SELECT count(*)
        FROM pg_stat_activity
        WHERE wait_event_type = 'Lock'
          AND clock_timestamp() - query_start > interval '5 seconds'
      ) AS lock_waiters_over_5s
    """
)


def _definition(conn, index_name: str) -> str | None:
    row = conn.execute(
        text(
            """
            SELECT indexdef
            FROM pg_indexes
            WHERE schemaname = 'public' AND indexname = :index_name
            """
        ),
        {"index_name": index_name},
    ).scalar()
    return str(row) if row else None


def collect_database_preflight(factory, *, index_name: str) -> dict[str, Any]:
    target = retirement_target(index_name)
    if target is None:
        raise ValueError("index_not_registered_retirement_target")
    with factory.get_connection() as conn:
        state = dict(conn.execute(PREFLIGHT_SQL).mappings().one())
        definition = _definition(conn, index_name)
    return {
        "relation": target.relation,
        "index_name": index_name,
        "definition": definition,
        "definition_sha256": (
            hashlib.sha256(definition.encode()).hexdigest() if definition else None
        ),
        "in_recovery": bool(state.get("in_recovery")),
        "read_only": str(state.get("read_only") or ""),
        "invalid_indexes": int(state.get("invalid_indexes") or 0),
        "archive_failures": int(state.get("archive_failures") or 0),
        "lock_waiters_over_5s": int(state.get("lock_waiters_over_5s") or 0),
    }


def _assert_database_ready(payload: dict[str, Any]) -> None:
    if payload["in_recovery"] or payload["read_only"] != "off":
        raise ValueError("database_not_write_ready")
    if payload["invalid_indexes"]:
        raise ValueError("invalid_index_detected")
    if payload["archive_failures"]:
        raise ValueError("archive_failure_detected")
    if payload["lock_waiters_over_5s"]:
        raise ValueError("lock_waiter_over_5s_detected")


def drop_index(factory, *, index_name: str, expected_sha256: str) -> None:
    before = collect_database_preflight(factory, index_name=index_name)
    _assert_database_ready(before)
    if before["definition_sha256"] != expected_sha256:
        raise ValueError("live_index_definition_sha256_mismatch")
    connection = factory.get_connection().execution_options(
        isolation_level="AUTOCOMMIT"
    )
    try:
        connection.execute(text(f'DROP INDEX CONCURRENTLY "{index_name}"'))
    finally:
        connection.close()


def restore_index(
    factory,
    *,
    index_name: str,
    definition: str,
    expected_sha256: str,
) -> None:
    if hashlib.sha256(definition.encode()).hexdigest() != expected_sha256:
        raise ValueError("backout_definition_sha256_mismatch")
    before = collect_database_preflight(factory, index_name=index_name)
    _assert_database_ready(before)
    if before["definition"] is not None:
        raise ValueError("index_restore_requires_missing_index")
    statement = re.sub(
        r"^CREATE (UNIQUE )?INDEX ",
        lambda match: f"CREATE {match.group(1) or ''}INDEX CONCURRENTLY ",
        definition,
        count=1,
    )
    if "INDEX CONCURRENTLY" not in statement:
        raise ValueError("backout_definition_not_create_index")
    connection = factory.get_connection().execution_options(
        isolation_level="AUTOCOMMIT"
    )
    try:
        connection.execute(text(statement))
    finally:
        connection.close()
