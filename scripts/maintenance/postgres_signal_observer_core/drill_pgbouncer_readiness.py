"""Bounded shared-deadline PgBouncer startup readiness owner."""

from __future__ import annotations

import math
import subprocess
from typing import Any, Callable, Mapping


FORMAL_PGBOUNCER_STARTUP_DEADLINE_SECONDS = 10.0
FORMAL_PGBOUNCER_STARTUP_POLL_SECONDS = 0.25
FORMAL_PGBOUNCER_STARTUP_MAX_ATTEMPTS = math.ceil(
    FORMAL_PGBOUNCER_STARTUP_DEADLINE_SECONDS
    / FORMAL_PGBOUNCER_STARTUP_POLL_SECONDS
)


def _receipt(
    stages: Mapping[str, Any], detail_code: str | None
) -> dict[str, Any]:
    return {
        "passed": detail_code is None,
        "gate": "pgbouncer_readiness",
        "detail_code": detail_code,
        "startup_deadline_seconds": FORMAL_PGBOUNCER_STARTUP_DEADLINE_SECONDS,
        "poll_seconds": FORMAL_PGBOUNCER_STARTUP_POLL_SECONDS,
        "stages": stages,
    }


def _attempt(
    *,
    stage: dict[str, Any],
    argv: tuple[str, ...],
    timeout: float,
    run: Callable[..., Any],
    environment: Mapping[str, str],
    stage_result: Callable[[Any], dict[str, Any]],
    stage_name: str,
) -> str:
    stage["attempted"] = True
    stage["attempt_count"] += 1
    try:
        completed = run(argv, environment=environment, timeout=timeout)
    except subprocess.TimeoutExpired:
        stage["last_result"] = {
            "status": "timeout",
            "error_code": (
                f"formal_pgbouncer_{stage_name}_terminal_deadline_exceeded"
            ),
        }
        return "terminal"
    except (OSError, RuntimeError):
        stage["last_result"] = {
            "status": "exec_error",
            "error_code": f"formal_pgbouncer_{stage_name}_unavailable",
        }
        return "terminal"
    result = stage_result(completed)
    stage["last_result"] = result
    if result.get("status") == "terminal_zero":
        stage["success_count"] += 1
        stage["passed"] = True
        return "passed"
    return "retry"


def evaluate_pgbouncer_startup(
    *,
    stages: dict[str, dict[str, Any]],
    pg_isready_argv: tuple[str, ...],
    show_version_argv: tuple[str, ...],
    run: Callable[..., Any],
    environment: Mapping[str, str],
    stage_result: Callable[[Any], dict[str, Any]],
    monotonic: Callable[[], float],
    sleep: Callable[[float], None],
) -> Mapping[str, Any]:
    """Run the existing two commands under one absolute startup deadline."""

    deadline = monotonic() + FORMAL_PGBOUNCER_STARTUP_DEADLINE_SECONDS
    detail_code = "formal_pgbouncer_pg_isready_failed"
    while True:
        remaining = deadline - monotonic()
        if remaining <= 0:
            break
        final_attempt = remaining <= FORMAL_PGBOUNCER_STARTUP_POLL_SECONDS
        pg_outcome = _attempt(
            stage=stages["pg_isready"],
            argv=pg_isready_argv,
            timeout=remaining,
            run=run,
            environment=environment,
            stage_result=stage_result,
            stage_name="pg_isready",
        )
        if pg_outcome == "terminal":
            return _receipt(stages, "formal_pgbouncer_pg_isready_failed")
        if pg_outcome == "passed":
            detail_code = "formal_pgbouncer_show_version_failed"
            remaining = deadline - monotonic()
            if remaining <= 0:
                break
            show_outcome = _attempt(
                stage=stages["show_version"],
                argv=show_version_argv,
                timeout=remaining,
                run=run,
                environment=environment,
                stage_result=stage_result,
                stage_name="show_version",
            )
            if show_outcome == "terminal":
                return _receipt(stages, detail_code)
            if show_outcome == "passed":
                return _receipt(stages, None)
        else:
            detail_code = "formal_pgbouncer_pg_isready_failed"

        if final_attempt:
            break
        remaining = deadline - monotonic()
        if remaining <= 0:
            break
        if remaining <= FORMAL_PGBOUNCER_STARTUP_POLL_SECONDS:
            continue
        sleep(FORMAL_PGBOUNCER_STARTUP_POLL_SECONDS)
    return _receipt(stages, detail_code)


__all__ = [
    "FORMAL_PGBOUNCER_STARTUP_DEADLINE_SECONDS",
    "FORMAL_PGBOUNCER_STARTUP_MAX_ATTEMPTS",
    "FORMAL_PGBOUNCER_STARTUP_POLL_SECONDS",
    "evaluate_pgbouncer_startup",
]
