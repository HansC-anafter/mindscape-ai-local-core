"""Payload-free receipt schema for the formal PostgreSQL readiness gate."""

from __future__ import annotations

import hashlib
import re
from typing import Any, Mapping

from .drill_escalation import (
    FORMAL_POSTGRES_STARTUP_DEADLINE_SECONDS,
    FORMAL_POSTGRES_STARTUP_POLL_SECONDS,
)
from .drill_readback import CONTAINER_READBACK_TERMINAL_DEADLINE_SECONDS
from .drill_readback_projection import (
    CONTAINER_READBACK_MAX_BYTES,
    CONTAINER_READBACK_SCHEMA_VERSION,
)


_DETAIL_CODES = frozenset(
    "formal_postgres_container_readback_failed "
    "formal_postgres_pg_isready_deadline_exceeded formal_postgres_pg_isready_unavailable "
    "formal_postgres_psql_select_one_deadline_exceeded "
    "formal_postgres_psql_select_one_not_attempted_deadline_exceeded "
    "formal_postgres_psql_select_one_unavailable".split()
)
_RESULT_INVALID_CODES = frozenset(
    "formal_postgres_readiness_result_invalid "
    "formal_postgres_readiness_capture_invalid".split()
)
_STAGES = ("container_readback", "pg_isready", "psql_select_one")
_CONTAINER_FAILURE_SCHEMA_VERSION = 1
_FORMAL_READBACK_FAILURE_SUFFIXES = (
    "terminal_deadline_exceeded unavailable result_invalid failed projection_invalid"
).split()
_CONTAINER_FAILURE_SUFFIXES = (
    "role_mismatch name_mismatch config_image_mismatch image_id_mismatch "
    "user_mismatch entrypoint_mismatch cmd_mismatch nano_cpus_mismatch "
    "memory_bytes_mismatch pids_limit_mismatch read_only_rootfs_mismatch "
    "security_opt_mismatch tmpfs_mismatch mounts_mismatch cap_add_mismatch "
    "cap_drop_mismatch privileged_mismatch pid_mode_mismatch "
    "network_mode_mismatch network_identity_mismatch id_invalid state_unready "
    "health_mismatch"
).split()
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
_EMPTY_CAPTURE_SHA256 = hashlib.sha256(b"").hexdigest()


def _container_failure_codes(role: str) -> frozenset[str]:
    return frozenset(
        [f"formal_{role}_readback_{suffix}" for suffix in _FORMAL_READBACK_FAILURE_SUFFIXES]
        + [f"{role}_container_readback_{suffix}" for suffix in _CONTAINER_FAILURE_SUFFIXES]
    )


def _project_container_metadata(source: Mapping[str, Any]) -> dict[str, Any] | None:
    metadata = {
        "projection_schema_version": CONTAINER_READBACK_SCHEMA_VERSION,
        "projection_max_bytes": CONTAINER_READBACK_MAX_BYTES,
        "terminal_deadline_seconds": CONTAINER_READBACK_TERMINAL_DEADLINE_SECONDS,
    }
    if any(
        type(source.get(key)) is not type(value) or source.get(key) != value
        for key, value in metadata.items()
    ):
        return None
    return metadata


def _project_container_readback_outcome(role: str, source: object) -> dict[str, Any] | None:
    """Project one exact, payload-free role-specific readback outcome."""

    if not isinstance(source, Mapping) or type(source.get("role")) is not str:
        return None
    if source.get("role") != role:
        return None
    metadata = _project_container_metadata(source)
    if metadata is None:
        return None
    validation_passed = source.get("validation_passed")
    first_failure = source.get("first_failure")
    failures = source.get("failures")
    failure_codes = _container_failure_codes(role)
    if (
        validation_passed is True
        and first_failure is None
        and type(failures) is list
        and not failures
    ):
        if "exit_code" in source or "terminal_nonzero_capture" in source:
            return None
        return {
            "passed": True,
            "last_result": {
                "status": "validated",
                "detail_code": None,
                **metadata,
            },
        }
    if (
        validation_passed is not False
        or type(first_failure) is not str
        or first_failure not in failure_codes
        or type(failures) is not list
        or not 1 <= len(failures) <= len(failure_codes)
        or failures[0] != first_failure
        or any(type(code) is not str for code in failures)
        or any(code not in failure_codes for code in failures)
        or len(set(failures)) != len(failures)
    ):
        return None
    failure_projection: dict[str, Any] = {}
    terminal_failure = f"formal_{role}_readback_failed"
    if first_failure == terminal_failure:
        if failures != [terminal_failure]:
            return None
        exit_code = source.get("exit_code")
        capture_source = source.get("terminal_nonzero_capture")
        capture = (
            _project_capture(capture_source)
            if isinstance(capture_source, Mapping)
            and set(capture_source) == set(_CAPTURE_KEYS)
            else None
        )
        if (
            type(exit_code) is not int
            or exit_code == 0
            or capture is None
            or capture["exit_code"] != exit_code
        ):
            return None
        failure_projection = {
            "exit_code": exit_code,
            "terminal_nonzero_capture": capture,
        }
    elif "exit_code" in source or "terminal_nonzero_capture" in source:
        return None
    return {
        "passed": False,
        "last_result": {
            "status": "validation_failed",
            "detail_code": f"formal_{role}_container_readback_failed",
            **metadata,
            "leaf_failure_schema_version": _CONTAINER_FAILURE_SCHEMA_VERSION,
            "leaf_failure_code": first_failure,
            "leaf_failure_count": len(failures),
            "leaf_failure_codes": list(failures),
            **failure_projection,
        },
    }


def project_postgres_container_readback_outcome(source: object) -> dict[str, Any] | None:
    return _project_container_readback_outcome("postgres", source)


def project_pgbouncer_container_readback_outcome(source: object) -> dict[str, Any] | None:
    return _project_container_readback_outcome("pgbouncer", source)


def _project_container_failure(source: Mapping[str, Any], *, role: str = "postgres") -> dict[str, Any] | None:
    readback_source = {
        "validation_passed": False,
        "role": role,
        "first_failure": source.get("leaf_failure_code"),
        "failures": source.get("leaf_failure_codes"),
        "projection_schema_version": source.get("projection_schema_version"),
        "projection_max_bytes": source.get("projection_max_bytes"),
        "terminal_deadline_seconds": source.get("terminal_deadline_seconds"),
    }
    if "exit_code" in source:
        readback_source["exit_code"] = source.get("exit_code")
    if "terminal_nonzero_capture" in source:
        readback_source["terminal_nonzero_capture"] = source.get("terminal_nonzero_capture")
    outcome = _project_container_readback_outcome(role, readback_source)
    projection = outcome.get("last_result") if outcome is not None else None
    if (
        projection is None
        or type(source.get("leaf_failure_schema_version")) is not int
        or source.get("leaf_failure_schema_version")
        != _CONTAINER_FAILURE_SCHEMA_VERSION
        or type(source.get("leaf_failure_count")) is not int
        or source.get("leaf_failure_count") != projection.get("leaf_failure_count")
    ):
        return None
    return {
        key: value
        for key, value in projection.items()
        if key not in {"status", "detail_code"}
    }


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
        or (
            stdout_bytes == 0
            and capture["stdout_sha256"] != _EMPTY_CAPTURE_SHA256
        )
        or type(capture["stderr_present"]) is not bool
        or type(stderr_bytes) is not int
        or stderr_bytes < 0
        or capture["stderr_present"] != (stderr_bytes > 0)
        or type(capture["stderr_sha256"]) is not str
        or not re.fullmatch(r"[0-9a-f]{64}", capture["stderr_sha256"])
        or (
            stderr_bytes == 0
            and capture["stderr_sha256"] != _EMPTY_CAPTURE_SHA256
        )
        or capture["captures_truncated"] is not False
        or type(capture["hash_input"]) is not str
        or capture["hash_input"] != "full_raw_subprocess_capture_bytes"
        or capture["output_disclosed"] is not False
    ):
        return None
    return capture


def _project_result(stage_name: str, source: object, *, role: str = "postgres") -> dict[str, Any] | None:
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
        result = {"status": status, "exit_code": exit_code, "terminal_capture": capture}
        if role == "pgbouncer" and (
            set(source) != set(result)
            or not isinstance(source.get("terminal_capture"), Mapping)
            or set(source["terminal_capture"]) != set(_CAPTURE_KEYS)
        ):
            return None
        return result
    if status == "validated" and stage_name == "container_readback":
        metadata = _project_container_metadata(source)
        if source.get("detail_code") is None and metadata is not None:
            return {"status": status, "detail_code": None, **metadata}
        return None
    if status == "validation_failed" and stage_name == "container_readback":
        detail = source.get("detail_code")
        leaf_failure = _project_container_failure(source, role=role)
        if detail == f"formal_{role}_container_readback_failed" and leaf_failure:
            return {
                "status": status,
                "detail_code": detail,
                **leaf_failure,
            }
        return None
    if status in {"timeout", "exec_error"}:
        expected = (
            _STAGE_ERRORS.get(stage_name, {}).get(status)
            if role == "postgres"
            else {
                "timeout": (
                    f"formal_pgbouncer_{stage_name}_terminal_deadline_exceeded"
                ),
                "exec_error": f"formal_pgbouncer_{stage_name}_unavailable",
            }[status]
        )
        error_code = source.get("error_code")
        if expected is not None and type(error_code) is str and error_code == expected:
            return {"status": status, "error_code": expected}
        return None
    if status == "result_invalid" and (
        stage_name in _STAGE_ERRORS or role == "pgbouncer"
    ):
        error_code = source.get("error_code")
        expected_codes = _RESULT_INVALID_CODES if role == "postgres" else {
            f"formal_{role}_readiness_result_invalid", f"formal_{role}_readiness_capture_invalid"
        }
        if type(error_code) is str and error_code in expected_codes:
            return {"status": status, "error_code": error_code}
    return None


def _project_stage(
    stage_name: str, source: object, *, role: str = "postgres"
) -> dict[str, Any] | None:
    if not isinstance(source, Mapping):
        return None
    attempted = source.get("attempted")
    attempts = source.get("attempt_count")
    successes = source.get("success_count")
    passed = source.get("passed")
    raw_result = source.get("last_result")
    result = _project_result(stage_name, raw_result, role=role)
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
        or (role == "pgbouncer" and set(source) != {
            "attempted", "attempt_count", "success_count", "passed", "last_result"
        })
        or (
            role == "pgbouncer"
            and isinstance(raw_result, Mapping)
            and isinstance(result, Mapping)
            and set(raw_result) != set(result)
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
    if name == "pgbouncer_readiness":
        from .drill_pgbouncer_gate_receipt import project_pgbouncer_gate_receipt

        return project_pgbouncer_gate_receipt(name, source)
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
