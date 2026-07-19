"""Structured, payload-free readiness for the disposable drill client."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING, Any, Callable, Mapping

from .drill import DisposableDrillSignalConfig
from .drill_docker_runtime import canonical_docker_argv
from .drill_readiness_stage import empty_stage

if TYPE_CHECKING:
    from .drill import DisposableDrillClientConfig
    from .drill_bootstrap import DisposableDrillBootstrapConfig


FORMAL_CLIENT_READY_TERMINAL_DEADLINE_SECONDS = 10.0
FORMAL_CLIENT_READY_POLL_SECONDS = 0.25
FORMAL_CLIENT_READY_MAX_PID_ATTEMPTS = (
    int(
        FORMAL_CLIENT_READY_TERMINAL_DEADLINE_SECONDS
        / FORMAL_CLIENT_READY_POLL_SECONDS
    )
    + 1
)
_PSQL = "/usr/lib/postgresql/16/bin/psql"


def _receipt(
    stages: Mapping[str, Any], detail_code: str | None
) -> dict[str, Any]:
    return {
        "passed": detail_code is None,
        "gate": "client_ready",
        "detail_code": detail_code,
        "terminal_deadline_seconds": FORMAL_CLIENT_READY_TERMINAL_DEADLINE_SECONDS,
        "poll_seconds": FORMAL_CLIENT_READY_POLL_SECONDS,
        "stages": stages,
    }


def evaluate_client_readiness(
    *,
    container_outcome: Mapping[str, Any] | None,
    bootstrap: DisposableDrillBootstrapConfig,
    client: DisposableDrillClientConfig,
    run: Callable[..., Any],
    stage_result: Callable[[Any], dict[str, Any]],
    bind_signal_target: Callable[[DisposableDrillSignalConfig, float], bool],
    monotonic: Callable[[], float],
    sleep: Callable[[float], None],
) -> tuple[Mapping[str, Any], DisposableDrillSignalConfig | None]:
    """Wait within one bounded deadline for the source-owned client PID."""

    stages = {
        "container_readback": empty_stage(),
        "source_owned_pid": empty_stage(),
    }
    container_passed = bool(
        container_outcome is not None and container_outcome.get("passed") is True
    )
    stages["container_readback"] = {
        "attempted": True,
        "attempt_count": 1,
        "success_count": int(container_passed),
        "passed": container_passed,
        "last_result": (
            container_outcome["last_result"]
            if container_outcome is not None
            else {
                "status": "validation_failed",
                "detail_code": "formal_client_container_readback_failed",
            }
        ),
    }
    if not container_passed:
        return _receipt(stages, "formal_client_container_readback_failed"), None

    query = (
        "SELECT pid FROM pg_stat_activity WHERE application_name = "
        "'postgres-signal-observer-drill-client' AND state <> 'idle' "
        "ORDER BY backend_start DESC LIMIT 1;"
    )
    argv = canonical_docker_argv(
        "exec",
        bootstrap.postgres_container_name,
        _PSQL,
        "-X",
        "-U",
        client.database_user,
        "-d",
        client.database_name,
        "--tuples-only",
        "--no-align",
        "--command",
        query,
    )
    pid_stage = stages["source_owned_pid"]
    deadline = monotonic() + FORMAL_CLIENT_READY_TERMINAL_DEADLINE_SECONDS
    final_attempt = False
    while True:
        remaining = deadline - monotonic()
        if remaining <= 0:
            pid_stage["last_result"] = {
                "status": "result_invalid",
                "error_code": "formal_client_pid_not_observed_before_deadline",
            }
            return _receipt(
                stages, "formal_client_pid_not_observed_before_deadline"
            ), None
        pid_stage["attempted"] = True
        pid_stage["attempt_count"] += 1
        try:
            completed = run(argv, timeout=remaining)
        except subprocess.TimeoutExpired:
            pid_stage["last_result"] = {
                "status": "timeout",
                "error_code": "formal_client_pid_query_terminal_deadline_exceeded",
            }
            return _receipt(
                stages, "formal_client_pid_query_terminal_deadline_exceeded"
            ), None
        except (OSError, RuntimeError):
            pid_stage["last_result"] = {
                "status": "exec_error",
                "error_code": "formal_client_pid_query_unavailable",
            }
            return _receipt(stages, "formal_client_pid_query_unavailable"), None

        result = stage_result(completed)
        pid_stage["last_result"] = result
        status = result.get("status")
        if status == "terminal_nonzero":
            return _receipt(stages, "formal_client_pid_query_terminal_nonzero"), None
        if status != "terminal_zero":
            error_code = result.get("error_code")
            detail_code = (
                error_code
                if error_code
                in {
                    "formal_client_readiness_result_invalid",
                    "formal_client_readiness_capture_invalid",
                }
                else "formal_client_pid_query_result_invalid"
            )
            return _receipt(stages, detail_code), None

        raw = getattr(completed, "stdout", None)
        if not isinstance(raw, bytes):
            pid_stage["last_result"] = {
                "status": "result_invalid",
                "error_code": "formal_client_pid_query_result_invalid",
            }
            return _receipt(stages, "formal_client_pid_query_result_invalid"), None
        value = raw.strip()
        if value:
            try:
                pid = int(value.decode("ascii"))
            except (UnicodeError, ValueError):
                pid_stage["last_result"] = {
                    "status": "result_invalid",
                    "error_code": "formal_client_pid_value_invalid",
                }
                return _receipt(stages, "formal_client_pid_value_invalid"), None
            break

        remaining = deadline - monotonic()
        if remaining <= 0 or final_attempt:
            pid_stage["last_result"] = {
                "status": "result_invalid",
                "error_code": "formal_client_pid_not_observed_before_deadline",
            }
            return _receipt(
                stages, "formal_client_pid_not_observed_before_deadline"
            ), None
        if remaining <= FORMAL_CLIENT_READY_POLL_SECONDS:
            final_attempt = True
            continue
        sleep(FORMAL_CLIENT_READY_POLL_SECONDS)
    try:
        signal = DisposableDrillSignalConfig(
            drill_suffix=bootstrap.drill_suffix,
            postgres_image_ref=bootstrap.postgres_image_ref,
            target_postgres_pid=pid,
        )
        signal.validate()
    except ValueError:
        pid_stage["last_result"] = {
            "status": "result_invalid",
            "error_code": "formal_client_signal_config_invalid",
        }
        return _receipt(stages, "formal_client_signal_config_invalid"), None
    remaining = deadline - monotonic()
    if remaining <= 0 or not bind_signal_target(signal, remaining):
        pid_stage["last_result"] = {
            "status": "result_invalid",
            "error_code": "formal_client_signal_target_binding_failed",
        }
        return _receipt(
            stages, "formal_client_signal_target_binding_failed"
        ), None

    pid_stage["success_count"] = 1
    pid_stage["passed"] = True
    return _receipt(stages, None), signal


__all__ = [
    "FORMAL_CLIENT_READY_MAX_PID_ATTEMPTS",
    "FORMAL_CLIENT_READY_POLL_SECONDS",
    "FORMAL_CLIENT_READY_TERMINAL_DEADLINE_SECONDS",
    "evaluate_client_readiness",
]
