"""Payload-free receipt schema for the formal PostgreSQL readiness gate."""

from __future__ import annotations

import re
from typing import Any, Mapping

from .drill_escalation import (
    FORMAL_POSTGRES_STARTUP_DEADLINE_SECONDS,
    FORMAL_POSTGRES_STARTUP_POLL_SECONDS,
)


_DETAIL_CODES = frozenset(
    {
        "formal_postgres_container_readback_failed",
        "formal_postgres_pg_isready_deadline_exceeded",
        "formal_postgres_pg_isready_unavailable",
        "formal_postgres_psql_select_one_deadline_exceeded",
        "formal_postgres_psql_select_one_not_attempted_deadline_exceeded",
        "formal_postgres_psql_select_one_unavailable",
    }
)
_RESULT_INVALID_CODES = frozenset(
    {
        "formal_postgres_readiness_result_invalid",
        "formal_postgres_readiness_capture_invalid",
    }
)
_STAGES = ("container_readback", "pg_isready", "psql_select_one")
_STAGE_ERRORS = {
    "pg_isready": {
        "timeout": "formal_postgres_pg_isready_deadline_exceeded",
        "exec_error": "formal_postgres_pg_isready_unavailable",
    },
    "psql_select_one": {
        "timeout": "formal_postgres_psql_select_one_deadline_exceeded",
        "exec_error": "formal_postgres_psql_select_one_unavailable",
    },
}
_CAPTURE_KEYS = (
    "terminal exit_code stdout_present stdout_bytes stdout_sha256 stderr_present "
    "stderr_bytes stderr_sha256 captures_truncated hash_input output_disclosed"
).split()


def _project_capture(source: object) -> dict[str, Any] | None:
    if not isinstance(source, Mapping):
        return None
    capture = {key: source.get(key) for key in _CAPTURE_KEYS}
    stdout_bytes = capture["stdout_bytes"]
    stderr_bytes = capture["stderr_bytes"]
    if (
        capture["terminal"] is not True
        or type(capture["exit_code"]) is not int
        or type(capture["stdout_present"]) is not bool
        or type(stdout_bytes) is not int
        or stdout_bytes < 0
        or capture["stdout_present"] != (stdout_bytes > 0)
        or type(capture["stdout_sha256"]) is not str
        or not re.fullmatch(r"[0-9a-f]{64}", capture["stdout_sha256"])
        or type(capture["stderr_present"]) is not bool
        or type(stderr_bytes) is not int
        or stderr_bytes < 0
        or capture["stderr_present"] != (stderr_bytes > 0)
        or type(capture["stderr_sha256"]) is not str
        or not re.fullmatch(r"[0-9a-f]{64}", capture["stderr_sha256"])
        or capture["captures_truncated"] is not False
        or capture["hash_input"] != "full_raw_subprocess_capture_bytes"
        or capture["output_disclosed"] is not False
    ):
        return None
    return capture


def _project_result(stage_name: str, source: object) -> dict[str, Any] | None:
    if not isinstance(source, Mapping):
        return None
    status = source.get("status")
    if type(status) is not str:
        return None
    if status in {"terminal_zero", "terminal_nonzero"}:
        exit_code = source.get("exit_code")
        capture = _project_capture(source.get("terminal_capture"))
        if (
            type(exit_code) is not int
            or (status == "terminal_zero") != (exit_code == 0)
            or capture is None
            or capture["exit_code"] != exit_code
        ):
            return None
        return {"status": status, "exit_code": exit_code, "terminal_capture": capture}
    if status == "validated" and stage_name == "container_readback":
        return {"status": status, "detail_code": None}
    if status == "validation_failed" and stage_name == "container_readback":
        detail = source.get("detail_code")
        if detail == "formal_postgres_container_readback_failed":
            return {"status": status, "detail_code": detail}
        return None
    if status in {"timeout", "exec_error"}:
        expected = _STAGE_ERRORS.get(stage_name, {}).get(status)
        if expected is not None and source.get("error_code") == expected:
            return {"status": status, "error_code": expected}
        return None
    if status == "result_invalid" and stage_name in _STAGE_ERRORS:
        error_code = source.get("error_code")
        if type(error_code) is str and error_code in _RESULT_INVALID_CODES:
            return {"status": status, "error_code": error_code}
    return None


def _project_stage(stage_name: str, source: object) -> dict[str, Any] | None:
    if not isinstance(source, Mapping):
        return None
    attempted = source.get("attempted")
    attempts = source.get("attempt_count")
    successes = source.get("success_count")
    passed = source.get("passed")
    result = _project_result(stage_name, source.get("last_result"))
    if (
        type(attempted) is not bool
        or type(attempts) is not int
        or type(successes) is not int
        or type(passed) is not bool
        or attempts < 0
        or not 0 <= successes <= attempts
        or attempted != (attempts > 0)
        or passed != (successes > 0)
        or (
            result is not None
            and result.get("status") == "terminal_zero"
            and successes == 0
        )
        or (
            stage_name != "container_readback"
            and result is not None
            and result.get("status") != "terminal_zero"
            and successes >= attempts
        )
        or (attempted and result is None)
        or (not attempted and source.get("last_result") is not None)
    ):
        return None
    return {
        "attempted": attempted,
        "attempt_count": attempts,
        "success_count": successes,
        "passed": passed,
        "last_result": result,
    }


def _detail_matches_stages(
    detail: object,
    container: Mapping[str, Any],
    pg_ready: Mapping[str, Any],
    select_one: Mapping[str, Any],
) -> bool:
    pg_result = pg_ready["last_result"]
    psql_result = select_one["last_result"]
    pg_status = pg_result.get("status") if isinstance(pg_result, Mapping) else None
    psql_status = (
        psql_result.get("status") if isinstance(psql_result, Mapping) else None
    )
    if detail == "formal_postgres_container_readback_failed":
        return (
            container["last_result"]["status"] == "validation_failed"
            and not pg_ready["attempted"]
            and not select_one["attempted"]
        )
    if detail == "formal_postgres_pg_isready_unavailable":
        return pg_result == {
            "status": "exec_error",
            "error_code": "formal_postgres_pg_isready_unavailable",
        }
    if detail == "formal_postgres_pg_isready_deadline_exceeded":
        return pg_ready["attempted"] and pg_status in {
            "terminal_nonzero",
            "timeout",
            "result_invalid",
        }
    if detail == "formal_postgres_psql_select_one_unavailable":
        return psql_result == {
            "status": "exec_error",
            "error_code": "formal_postgres_psql_select_one_unavailable",
        }
    if detail == "formal_postgres_psql_select_one_deadline_exceeded":
        return select_one["attempted"] and psql_status in {
            "terminal_nonzero",
            "timeout",
            "result_invalid",
        }
    if detail == "formal_postgres_psql_select_one_not_attempted_deadline_exceeded":
        return (
            pg_ready["passed"]
            and pg_status == "terminal_zero"
            and not select_one["passed"]
            and pg_ready["success_count"] == select_one["attempt_count"] + 1
            and (
                not select_one["attempted"]
                or psql_status in {"terminal_nonzero", "result_invalid"}
            )
        )
    return detail is None


def project_formal_gate_receipt(name: str, source: object) -> dict[str, Any]:
    """Persist only the exact source-owned readiness projection."""

    invalid = {
        "name": name,
        "kind": "gate",
        "passed": False,
        "detail_code": "formal_postgres_readiness_receipt_invalid",
    }
    if name != "postgres_readiness":
        return {
            "name": name,
            "kind": "gate",
            "passed": isinstance(source, Mapping) and source.get("passed") is True,
        }
    if not isinstance(source, Mapping):
        return invalid
    passed = source.get("passed")
    detail = source.get("detail_code")
    raw_stages = source.get("stages")
    if (
        type(passed) is not bool
        or (
            detail is not None
            and (type(detail) is not str or detail not in _DETAIL_CODES)
        )
        or source.get("startup_deadline_seconds")
        != FORMAL_POSTGRES_STARTUP_DEADLINE_SECONDS
        or source.get("poll_seconds") != FORMAL_POSTGRES_STARTUP_POLL_SECONDS
        or not isinstance(raw_stages, Mapping)
    ):
        return invalid
    stages: dict[str, Any] = {}
    for stage_name in _STAGES:
        stage = _project_stage(stage_name, raw_stages.get(stage_name))
        if stage is None:
            return invalid
        stages[stage_name] = stage
    container, pg_ready, select_one = (stages[name] for name in _STAGES)
    consistent = bool(
        container["attempt_count"] == 1
        and container["last_result"]["status"]
        == ("validated" if container["passed"] else "validation_failed")
        and (
            (container["passed"] and pg_ready["attempted"])
            or (
                not container["passed"]
                and not pg_ready["attempted"]
                and not select_one["attempted"]
                and detail == "formal_postgres_container_readback_failed"
            )
        )
        and select_one["attempt_count"] <= pg_ready["success_count"]
        and passed == select_one["passed"]
        and _detail_matches_stages(detail, container, pg_ready, select_one)
        and (
            not passed
            or (
                detail is None
                and all(stage["passed"] for stage in stages.values())
                and pg_ready["last_result"]["status"] == "terminal_zero"
                and select_one["last_result"]["status"] == "terminal_zero"
            )
        )
        and (passed or detail is not None)
    )
    if not consistent:
        return invalid
    return {
        "name": name,
        "kind": "gate",
        "passed": passed,
        "detail_code": detail,
        "startup_deadline_seconds": FORMAL_POSTGRES_STARTUP_DEADLINE_SECONDS,
        "poll_seconds": FORMAL_POSTGRES_STARTUP_POLL_SECONDS,
        "stages": stages,
    }
