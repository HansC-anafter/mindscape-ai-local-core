"""Bounded authoritative task-status observation for runtime pressure gates."""

from __future__ import annotations

from typing import Any, Callable


RunCommand = Callable[[list[str], float], dict[str, Any]]

TASK_STATUS_STATEMENT_TIMEOUT_MS = 2_000
TASK_STATUS_LOCK_TIMEOUT_MS = 1_000


def _task_status_sql(
    *,
    running_observation_limit: int,
    pending_observation_limit: int,
) -> str:
    running_limit = max(0, int(running_observation_limit)) + 1
    pending_limit = max(0, int(pending_observation_limit)) + 1
    return (
        "select 'running' as status, count(*) from ("
        "select 1 from tasks where status = 'running' "
        f"limit {running_limit}"
        ") as bounded_running union all "
        "select 'pending' as status, count(*) from ("
        "select 1 from tasks where status = 'pending' "
        "and task_type in ('playbook_execution', 'tool_execution') "
        "and frontier_state = 'ready' "
        "and (blocked_reason is null or blocked_reason = '') "
        f"limit {pending_limit}"
        ") as bounded_pending;"
    )


def collect_task_status_counts(
    run_command: RunCommand,
    timeout_seconds: float,
    *,
    running_observation_limit: int,
    pending_observation_limit: int,
) -> dict[str, Any]:
    """Collect bounded task truth without turning observed counts into a gate."""

    sql = _task_status_sql(
        running_observation_limit=running_observation_limit,
        pending_observation_limit=pending_observation_limit,
    )
    pgoptions = (
        f"-c statement_timeout={TASK_STATUS_STATEMENT_TIMEOUT_MS} "
        f"-c lock_timeout={TASK_STATUS_LOCK_TIMEOUT_MS} "
        "-c default_transaction_read_only=on"
    )
    result = run_command(
        [
            "docker",
            "exec",
            "--env",
            f"PGOPTIONS={pgoptions}",
            "mindscape-ai-local-core-postgres",
            "psql",
            "-X",
            "-U",
            "mindscape",
            "-d",
            "mindscape_core",
            "-At",
            "-F",
            ",",
            "-c",
            sql,
        ],
        timeout_seconds,
    )
    counts = {"pending": 0, "running": 0}
    parse_error = False
    seen_statuses: set[str] = set()
    if result.get("ok"):
        try:
            for line in str(result.get("stdout") or "").splitlines():
                status, separator, raw_count = line.partition(",")
                if not separator or status not in counts or status in seen_statuses:
                    parse_error = True
                    break
                counts[status] = int(raw_count)
                seen_statuses.add(status)
        except (TypeError, ValueError):
            parse_error = True
        parse_error = parse_error or seen_statuses != set(counts)

    ok = bool(result.get("ok")) and not parse_error
    if parse_error:
        error = "task_status_output_invalid"
    elif result.get("timeout"):
        error = "command_timeout"
    elif not ok:
        error = str(result.get("stderr") or "").strip() or "task_status_unavailable"
    else:
        error = ""
    return {
        "ok": ok,
        "counts": counts,
        "gate_semantics": "observational_only",
        "pending_semantics": "ready_unblocked_execution_frontier",
        "query_source": "tasks_authoritative_bounded",
        "server_statement_timeout_ms": TASK_STATUS_STATEMENT_TIMEOUT_MS,
        "server_lock_timeout_ms": TASK_STATUS_LOCK_TIMEOUT_MS,
        "elapsed_seconds": result.get("elapsed_seconds"),
        "error": error,
    }
