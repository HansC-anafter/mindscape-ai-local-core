"""Strict payload-free schema for the formal client readiness gate."""

from __future__ import annotations

from typing import Any, Mapping

from .drill_client_readiness import FORMAL_CLIENT_READY_TERMINAL_DEADLINE_SECONDS
from .drill_gate_receipt import _project_capture, _project_stage


_STAGES = ("container_readback", "source_owned_pid")
_DETAIL_CODES = frozenset(
    {
        "formal_client_container_readback_failed",
        "formal_client_pid_query_terminal_nonzero",
        "formal_client_pid_query_terminal_deadline_exceeded",
        "formal_client_pid_query_unavailable",
        "formal_client_pid_query_result_invalid",
        "formal_client_readiness_result_invalid",
        "formal_client_readiness_capture_invalid",
        "formal_client_pid_value_invalid",
        "formal_client_signal_config_invalid",
    }
)
_RESULT_INVALID_CODES = frozenset(
    {
        "formal_client_pid_query_result_invalid",
        "formal_client_readiness_result_invalid",
        "formal_client_readiness_capture_invalid",
        "formal_client_pid_value_invalid",
        "formal_client_signal_config_invalid",
    }
)
_CAPTURE_KEYS = frozenset(
    "terminal exit_code stdout_present stdout_bytes stdout_sha256 stderr_present "
    "stderr_bytes stderr_sha256 captures_truncated hash_input output_disclosed".split()
)


def _project_pid_result(source: object) -> dict[str, Any] | None:
    if not isinstance(source, Mapping) or type(source.get("status")) is not str:
        return None
    status = source["status"]
    if status in {"terminal_zero", "terminal_nonzero"}:
        capture_source = source.get("terminal_capture")
        capture = _project_capture(capture_source)
        exit_code = source.get("exit_code")
        projected = {
            "status": status,
            "exit_code": exit_code,
            "terminal_capture": capture,
        }
        if (
            set(source) != set(projected)
            or type(exit_code) is not int
            or (status == "terminal_zero") != (exit_code == 0)
            or capture is None
            or capture["exit_code"] != exit_code
            or not isinstance(capture_source, Mapping)
            or set(capture_source) != _CAPTURE_KEYS
        ):
            return None
        return projected
    expected_error = {
        "timeout": "formal_client_pid_query_terminal_deadline_exceeded",
        "exec_error": "formal_client_pid_query_unavailable",
    }.get(status)
    if expected_error is not None:
        if set(source) == {"status", "error_code"} and source.get(
            "error_code"
        ) == expected_error:
            return {"status": status, "error_code": expected_error}
        return None
    if status == "result_invalid":
        error_code = source.get("error_code")
        if (
            set(source) == {"status", "error_code"}
            and type(error_code) is str
            and error_code in _RESULT_INVALID_CODES
        ):
            return {"status": status, "error_code": error_code}
    return None


def _project_pid_stage(source: object) -> dict[str, Any] | None:
    if not isinstance(source, Mapping) or set(source) != {
        "attempted",
        "attempt_count",
        "success_count",
        "passed",
        "last_result",
    }:
        return None
    attempted = source.get("attempted")
    attempts = source.get("attempt_count")
    successes = source.get("success_count")
    passed = source.get("passed")
    raw_result = source.get("last_result")
    result = _project_pid_result(raw_result) if raw_result is not None else None
    if (
        type(attempted) is not bool
        or type(attempts) is not int
        or type(successes) is not int
        or type(passed) is not bool
        or attempts not in {0, 1}
        or successes not in {0, 1}
        or successes > attempts
        or attempted != (attempts == 1)
        or passed != (successes == 1)
        or (attempted and result is None)
        or (not attempted and raw_result is not None)
        or (passed and result is not None and result["status"] != "terminal_zero")
        or (
            not passed
            and result is not None
            and result["status"] == "terminal_zero"
        )
    ):
        return None
    return {
        "attempted": attempted,
        "attempt_count": attempts,
        "success_count": successes,
        "passed": passed,
        "last_result": result,
    }


def _detail_matches(detail: object, pid_stage: Mapping[str, Any]) -> bool:
    result = pid_stage["last_result"]
    if not isinstance(result, Mapping):
        return False
    status = result.get("status")
    if detail == "formal_client_pid_query_terminal_nonzero":
        return status == "terminal_nonzero"
    if detail == "formal_client_pid_query_terminal_deadline_exceeded":
        return result == {
            "status": "timeout",
            "error_code": "formal_client_pid_query_terminal_deadline_exceeded",
        }
    if detail == "formal_client_pid_query_unavailable":
        return result == {
            "status": "exec_error",
            "error_code": "formal_client_pid_query_unavailable",
        }
    return status == "result_invalid" and result.get("error_code") == detail


def project_client_gate_receipt(name: str, source: object) -> dict[str, Any]:
    """Reject stage drift while retaining exact terminal metadata only."""

    invalid = {
        "name": name,
        "kind": "gate",
        "passed": False,
        "detail_code": "formal_client_readiness_receipt_invalid",
    }
    if not isinstance(source, Mapping) or set(source) != {
        "passed",
        "gate",
        "detail_code",
        "terminal_deadline_seconds",
        "stages",
    }:
        return invalid
    passed = source.get("passed")
    detail = source.get("detail_code")
    raw_stages = source.get("stages")
    if (
        type(passed) is not bool
        or type(source.get("gate")) is not str
        or source.get("gate") != name
        or (
            detail is not None
            and (type(detail) is not str or detail not in _DETAIL_CODES)
        )
        or type(source.get("terminal_deadline_seconds")) is not float
        or source.get("terminal_deadline_seconds")
        != FORMAL_CLIENT_READY_TERMINAL_DEADLINE_SECONDS
        or not isinstance(raw_stages, Mapping)
        or set(raw_stages) != set(_STAGES)
    ):
        return invalid
    raw_container = raw_stages.get("container_readback")
    container = _project_stage(
        "container_readback", raw_container, role="client"
    )
    pid_stage = _project_pid_stage(raw_stages.get("source_owned_pid"))
    if (
        container is None
        or pid_stage is None
        or container["attempt_count"] != 1
        or not isinstance(container["last_result"], Mapping)
        or not isinstance(raw_container, Mapping)
        or set(raw_container)
        != {"attempted", "attempt_count", "success_count", "passed", "last_result"}
        or raw_container.get("last_result") != container["last_result"]
    ):
        return invalid
    container_status = container["last_result"]["status"]
    consistent = bool(
        container["attempt_count"] == 1
        and container_status
        == ("validated" if container["passed"] else "validation_failed")
        and passed == pid_stage["passed"]
        and (
            (
                not container["passed"]
                and not passed
                and detail == "formal_client_container_readback_failed"
                and not pid_stage["attempted"]
            )
            or (
                container["passed"]
                and pid_stage["attempted"]
                and (
                    (
                        passed
                        and detail is None
                        and pid_stage["last_result"]["status"] == "terminal_zero"
                    )
                    or (
                        not passed
                        and detail is not None
                        and _detail_matches(detail, pid_stage)
                    )
                )
            )
        )
    )
    if not consistent:
        return invalid
    return {
        "name": name,
        "kind": "gate",
        "passed": passed,
        "detail_code": detail,
        "terminal_deadline_seconds": FORMAL_CLIENT_READY_TERMINAL_DEADLINE_SECONDS,
        "stages": {
            "container_readback": container,
            "source_owned_pid": pid_stage,
        },
    }


__all__ = ["project_client_gate_receipt"]
