"""PostgreSQL HA and read-replica readiness probes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Sequence

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.database.config import (
    get_pgbouncer_admin_url,
    get_postgres_url_core,
    get_postgres_url_core_readonly,
)
from app.database.engine_factory import create_transient_transaction_engine
from app.database.resource_pool_readiness import (
    build_resource_pool_readiness_summary,
)


SCHEMA_VERSION = 1
PRIMARY_STATUS_SQL = """
SELECT
    pg_is_in_recovery() AS postgres_in_recovery,
    current_setting('transaction_read_only') AS transaction_read_only,
    current_setting('archive_mode') AS wal_archive_mode,
    current_setting('wal_level') AS wal_level,
    (
        SELECT COUNT(*)::bigint
        FROM pg_stat_activity
        WHERE datname IN ('mindscape_core', 'mindscape_vectors')
          AND state = 'idle in transaction'
          AND btrim(COALESCE(application_name, '')) <> ''
          AND application_name NOT IN ('psql', 'pg_isready')
    ) AS app_idle_in_transaction_count
"""
REPLICA_STATUS_SQL = """
SELECT
    pg_is_in_recovery() AS postgres_in_recovery,
    current_setting('transaction_read_only') AS transaction_read_only,
    pg_last_wal_receive_lsn()::text AS receive_lsn,
    pg_last_wal_replay_lsn()::text AS replay_lsn,
    CASE
        WHEN pg_last_wal_receive_lsn() IS NULL
          OR pg_last_wal_replay_lsn() IS NULL
        THEN NULL
        ELSE pg_wal_lsn_diff(
            pg_last_wal_receive_lsn(),
            pg_last_wal_replay_lsn()
        )::bigint
    END AS replay_lag_bytes
"""
PGBOUNCER_POOLS_SQL = "SHOW POOLS"
PGBOUNCER_DATABASES_SQL = "SHOW DATABASES"

QueryOne = Callable[[str, str, str], Mapping[str, Any]]
QueryAll = Callable[[str, str, str], Sequence[Mapping[str, Any]]]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00",
        "Z",
    )


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "t", "true", "yes", "on"}


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _row_to_dict(row: Mapping[str, Any] | None) -> dict[str, Any]:
    return dict(row or {})


def _create_probe_engine(url: str, application_name: str) -> Engine:
    return create_transient_transaction_engine(url, application_name)


def _query_one(url: str, sql: str, application_name: str) -> dict[str, Any]:
    engine = _create_probe_engine(url, application_name)
    try:
        with engine.connect() as conn:
            row = conn.execute(text(sql)).mappings().first()
            return _row_to_dict(row)
    finally:
        engine.dispose()


def _query_all(url: str, sql: str, application_name: str) -> list[dict[str, Any]]:
    engine = _create_probe_engine(url, application_name)
    try:
        with engine.connect() as conn:
            return [dict(row) for row in conn.execute(text(sql)).mappings()]
    finally:
        engine.dispose()


def _query_all_autocommit(
    url: str,
    sql: str,
    application_name: str,
) -> list[dict[str, Any]]:
    import psycopg2

    conn = psycopg2.connect(url, application_name=application_name)
    conn.autocommit = True
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql)
            columns = [column[0] for column in cursor.description or ()]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        conn.close()


def _find_pool(
    pools: Sequence[Mapping[str, Any]],
    database_name: str,
) -> Mapping[str, Any] | None:
    for row in pools:
        row_database = str(row.get("database") or row.get("database_name") or "")
        if row_database == database_name:
            return row
    return None


def _pool_waiting(pools: Sequence[Mapping[str, Any]], database_name: str) -> int | None:
    pool = _find_pool(pools, database_name)
    if pool is None:
        return None
    return _coerce_int(pool.get("cl_waiting"), 0)


def _database_alias_present(
    databases: Sequence[Mapping[str, Any]],
    database_name: str,
) -> bool:
    for row in databases:
        alias = str(row.get("name") or row.get("database") or "")
        if alias == database_name:
            return True
    return False


def _waiting_or_zero_for_present_alias(
    pools: Sequence[Mapping[str, Any]],
    databases: Sequence[Mapping[str, Any]],
    database_name: str,
) -> int | None:
    waiting = _pool_waiting(pools, database_name)
    if waiting is None and _database_alias_present(databases, database_name):
        return 0
    return waiting


def _build_primary_status(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "available": True,
        "postgres_in_recovery": _coerce_bool(row.get("postgres_in_recovery")),
        "transaction_read_only": str(row.get("transaction_read_only") or ""),
        "wal_archive_mode": str(row.get("wal_archive_mode") or ""),
        "wal_level": str(row.get("wal_level") or ""),
        "app_idle_in_transaction_count": _coerce_int(
            row.get("app_idle_in_transaction_count"),
            0,
        ),
    }


def _build_replica_status(
    *,
    enabled: bool,
    configured: bool,
    row: Mapping[str, Any] | None = None,
    reason: str = "",
    error: str = "",
) -> dict[str, Any]:
    status = {
        "probe_enabled": enabled,
        "configured": configured,
        "available": False,
        "postgres_in_recovery": None,
        "transaction_read_only": "",
        "receive_lsn": None,
        "replay_lsn": None,
        "replay_lag_bytes": None,
        "reason": reason,
    }
    if error:
        status["error"] = error
    if not row:
        return status

    in_recovery = _coerce_bool(row.get("postgres_in_recovery"))
    read_only = str(row.get("transaction_read_only") or "")
    status.update(
        {
            "postgres_in_recovery": in_recovery,
            "transaction_read_only": read_only,
            "receive_lsn": row.get("receive_lsn"),
            "replay_lsn": row.get("replay_lsn"),
            "replay_lag_bytes": row.get("replay_lag_bytes"),
        }
    )
    status["available"] = in_recovery and read_only.lower() == "on"
    status["reason"] = "" if status["available"] else "not_readonly_replica"
    return status


def build_ha_readiness_report(
    *,
    use_readonly_probe: bool = False,
    include_pgbouncer: bool = True,
    application_name: str = "local-core-ha-readiness",
    query_one: QueryOne | None = None,
    query_all: QueryAll | None = None,
) -> dict[str, Any]:
    """Build a non-mutating PostgreSQL HA readiness report."""

    one = query_one or _query_one
    all_rows = query_all or _query_all
    primary = {
        "available": False,
        "postgres_in_recovery": None,
        "transaction_read_only": "",
        "wal_archive_mode": "",
        "wal_level": "",
        "app_idle_in_transaction_count": 0,
    }
    try:
        primary_url = get_postgres_url_core(required=True)
        primary = _build_primary_status(
            one(primary_url, PRIMARY_STATUS_SQL, application_name)
        )
    except Exception as exc:
        primary["error"] = str(exc)

    pgbouncer = {
        "enabled": include_pgbouncer,
        "available": False,
        "core_waiting": None,
        "vector_waiting": None,
        "readonly_core_waiting": None,
        "readonly_vector_waiting": None,
        "core_pool_present": False,
        "vector_pool_present": False,
        "readonly_core_pool_present": False,
        "readonly_vector_pool_present": False,
        "core_database_present": False,
        "vector_database_present": False,
        "readonly_core_database_present": False,
        "readonly_vector_database_present": False,
        "reason": "",
    }
    if include_pgbouncer:
        try:
            admin_url = get_pgbouncer_admin_url(required=False)
            if not admin_url:
                pgbouncer["reason"] = "pgbouncer_admin_url_missing"
            else:
                pool_query = all_rows if query_all is not None else _query_all_autocommit
                pools = pool_query(admin_url, PGBOUNCER_POOLS_SQL, application_name)
                databases = pool_query(
                    admin_url,
                    PGBOUNCER_DATABASES_SQL,
                    application_name,
                )
                pgbouncer.update(
                    {
                        "available": True,
                        "core_database_present": _database_alias_present(
                            databases,
                            "mindscape_core",
                        ),
                        "vector_database_present": _database_alias_present(
                            databases,
                            "mindscape_vectors",
                        ),
                        "readonly_core_database_present": _database_alias_present(
                            databases,
                            "mindscape_core_readonly",
                        ),
                        "readonly_vector_database_present": _database_alias_present(
                            databases,
                            "mindscape_vectors_readonly",
                        ),
                        "core_pool_present": _find_pool(
                            pools,
                            "mindscape_core",
                        )
                        is not None,
                        "vector_pool_present": _find_pool(
                            pools,
                            "mindscape_vectors",
                        )
                        is not None,
                        "readonly_core_pool_present": _find_pool(
                            pools,
                            "mindscape_core_readonly",
                        )
                        is not None,
                        "readonly_vector_pool_present": _find_pool(
                            pools,
                            "mindscape_vectors_readonly",
                        )
                        is not None,
                        "core_waiting": _waiting_or_zero_for_present_alias(
                            pools,
                            databases,
                            "mindscape_core",
                        ),
                        "vector_waiting": _waiting_or_zero_for_present_alias(
                            pools,
                            databases,
                            "mindscape_vectors",
                        ),
                        "readonly_core_waiting": _waiting_or_zero_for_present_alias(
                            pools,
                            databases,
                            "mindscape_core_readonly",
                        ),
                        "readonly_vector_waiting": _waiting_or_zero_for_present_alias(
                            pools,
                            databases,
                            "mindscape_vectors_readonly",
                        ),
                        "pools": [dict(row) for row in pools],
                        "databases": [dict(row) for row in databases],
                    }
                )
        except Exception as exc:
            pgbouncer["reason"] = "pgbouncer_probe_failed"
            pgbouncer["error"] = str(exc)
    else:
        pgbouncer["reason"] = "pgbouncer_probe_disabled"

    readonly_url = get_postgres_url_core_readonly(required=False)
    if not use_readonly_probe:
        replica = _build_replica_status(
            enabled=False,
            configured=bool(readonly_url),
            reason="readonly_probe_disabled",
        )
    elif not readonly_url:
        replica = _build_replica_status(
            enabled=True,
            configured=False,
            reason="readonly_url_missing",
        )
    else:
        try:
            replica = _build_replica_status(
                enabled=True,
                configured=True,
                row=one(
                    readonly_url,
                    REPLICA_STATUS_SQL,
                    f"{application_name}:readonly",
                ),
            )
        except Exception as exc:
            replica = _build_replica_status(
                enabled=True,
                configured=True,
                reason="readonly_probe_failed",
                error=str(exc),
            )

    resource_pool_readiness = build_resource_pool_readiness_summary(
        primary=primary,
        pgbouncer=pgbouncer,
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "checked_at": _utc_now(),
        "primary": primary,
        "pgbouncer": pgbouncer,
        "resource_pool_readiness": resource_pool_readiness,
        "replica": replica,
        "postgres_in_recovery": primary["postgres_in_recovery"],
        "transaction_read_only": primary["transaction_read_only"],
        "pgbouncer_core_waiting": pgbouncer["core_waiting"],
        "pgbouncer_vector_waiting": pgbouncer["vector_waiting"],
        "pgbouncer_readonly_core_waiting": pgbouncer["readonly_core_waiting"],
        "pgbouncer_readonly_vector_waiting": pgbouncer["readonly_vector_waiting"],
        "app_idle_in_transaction_count": primary["app_idle_in_transaction_count"],
        "replica_available": replica["available"],
        "replica_replay_lag_bytes": replica["replay_lag_bytes"],
        "wal_archive_mode": primary["wal_archive_mode"],
    }
