"""Read-only database probes for PostgreSQL runtime preflight."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from sqlalchemy import text


REQUIRED_EXTENSIONS = ("pg_repack", "pg_stat_statements")


def _format_bytes(value: Any) -> str:
    try:
        size = float(value or 0)
    except (TypeError, ValueError):
        size = 0.0
    units = ("B", "KB", "MB", "GB", "TB")
    for unit in units:
        if size < 1024.0 or unit == units[-1]:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{int(value or 0)} B"


def mapping_one(
    conn,
    sql: str,
    params: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    row = conn.execute(text(sql), dict(params or {})).mappings().first()
    return dict(row or {})


def mapping_all(
    conn,
    sql: str,
    params: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in conn.execute(text(sql), dict(params or {})).mappings()
    ]


def show_setting(conn, name: str) -> str:
    row = conn.execute(text(f"SHOW {name}")).first()
    if not row:
        return ""
    return str(row[0] or "")


def relation_sizes(conn, relations: Iterable[str]) -> list[dict[str, Any]]:
    rows = mapping_all(
        conn,
        """
        SELECT
            relname,
            pg_total_relation_size(relid)::bigint AS total_bytes,
            pg_relation_size(relid)::bigint AS heap_bytes,
            pg_indexes_size(relid)::bigint AS index_bytes,
            (
                pg_total_relation_size(relid)
                - pg_relation_size(relid)
                - pg_indexes_size(relid)
            )::bigint AS toast_bytes
        FROM pg_catalog.pg_statio_user_tables
        WHERE relname = ANY(:relations)
        ORDER BY pg_total_relation_size(relid) DESC
        """,
        {"relations": list(relations)},
    )
    for row in rows:
        for key in ("total_bytes", "heap_bytes", "index_bytes", "toast_bytes"):
            row[f"{key}_pretty"] = _format_bytes(row.get(key))
    return rows


def hot_row_budget(
    conn,
    *,
    recent_hours: int,
    execution_context_budget: int,
    result_budget: int,
    params_budget: int,
    blocked_payload_budget: int,
) -> dict[str, Any]:
    return mapping_one(
        conn,
        """
        SELECT
            COUNT(*)::bigint AS recent_rows,
            COUNT(*) FILTER (
                WHERE octet_length(coalesce(execution_context::text, ''))
                      > :execution_context_budget
            )::bigint AS execution_context_over_budget,
            COUNT(*) FILTER (
                WHERE octet_length(coalesce(result::text, '')) > :result_budget
            )::bigint AS result_over_budget,
            COUNT(*) FILTER (
                WHERE octet_length(coalesce(params::text, '')) > :params_budget
            )::bigint AS params_over_budget,
            COUNT(*) FILTER (
                WHERE octet_length(coalesce(blocked_payload::text, ''))
                      > :blocked_payload_budget
            )::bigint AS blocked_payload_over_budget,
            COALESCE(MAX(octet_length(coalesce(execution_context::text, ''))), 0)::bigint
                AS max_execution_context_bytes,
            COALESCE(MAX(octet_length(coalesce(result::text, ''))), 0)::bigint
                AS max_result_bytes,
            COALESCE(MAX(octet_length(coalesce(params::text, ''))), 0)::bigint
                AS max_params_bytes,
            COALESCE(MAX(octet_length(coalesce(blocked_payload::text, ''))), 0)::bigint
                AS max_blocked_payload_bytes
        FROM tasks
        WHERE created_at >= now() - (:recent_hours * interval '1 hour')
        """,
        {
            "recent_hours": recent_hours,
            "execution_context_budget": execution_context_budget,
            "result_budget": result_budget,
            "params_budget": params_budget,
            "blocked_payload_budget": blocked_payload_budget,
        },
    )


def activity(conn) -> dict[str, Any]:
    states = mapping_all(
        conn,
        """
        SELECT state, COUNT(*)::bigint AS count
        FROM pg_stat_activity
        GROUP BY state
        ORDER BY state NULLS FIRST
        """,
    )
    state_counts = {
        str(row.get("state") or "backend"): int(row.get("count") or 0)
        for row in states
    }
    idle_in_transaction = int(state_counts.get("idle in transaction", 0))
    samples = mapping_all(
        conn,
        """
        SELECT
            datname,
            application_name,
            state,
            wait_event_type,
            COUNT(*)::bigint AS count
        FROM pg_stat_activity
        GROUP BY datname, application_name, state, wait_event_type
        ORDER BY count DESC, state NULLS FIRST, application_name
        LIMIT 20
        """,
    )
    return {
        "state_counts": state_counts,
        "idle_in_transaction": idle_in_transaction,
        "total_connections": sum(state_counts.values()),
        "samples": samples,
    }


def runner_workload(conn) -> dict[str, Any]:
    try:
        return mapping_one(
            conn,
            """
            SELECT
                COUNT(*) FILTER (WHERE status = 'running')::bigint AS running_tasks,
                COUNT(*) FILTER (
                    WHERE status = 'running'
                      AND (
                        runner_id IS NOT NULL
                        OR execution_context->>'runner_id' IS NOT NULL
                      )
                )::bigint AS runner_owned_running_tasks,
                COUNT(*) FILTER (
                    WHERE status = 'pending'
                      AND (next_eligible_at IS NULL OR next_eligible_at <= now())
                )::bigint AS ready_pending_tasks,
                COUNT(DISTINCT COALESCE(runner_id, execution_context->>'runner_id'))
                    FILTER (
                        WHERE status = 'running'
                          AND COALESCE(runner_id, execution_context->>'runner_id')
                              IS NOT NULL
                    )::bigint AS active_runner_owners
            FROM tasks
            WHERE status IN ('running', 'pending')
            """,
        )
    except Exception as exc:
        return {"error": str(exc)}


def installed_extensions(conn) -> set[str]:
    rows = mapping_all(
        conn,
        """
        SELECT extname
        FROM pg_extension
        WHERE extname = ANY(:extensions)
        ORDER BY extname
        """,
        {"extensions": list(REQUIRED_EXTENSIONS)},
    )
    return {str(row["extname"]) for row in rows if row.get("extname")}


def pg_stat_statements_top(
    conn,
    *,
    enabled: bool,
    limit: int,
) -> list[dict[str, Any]]:
    if not enabled:
        return []
    try:
        return mapping_all(
            conn,
            """
            SELECT
                queryid,
                calls,
                total_exec_time,
                mean_exec_time,
                rows,
                left(query, 500) AS query
            FROM pg_stat_statements
            ORDER BY total_exec_time DESC
            LIMIT :limit
            """,
            {"limit": limit},
        )
    except Exception as exc:
        return [{"error": str(exc)}]
