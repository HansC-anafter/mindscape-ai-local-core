"""Strict payload-free schema for the formal PgBouncer readiness gate."""

from __future__ import annotations

from typing import Any, Mapping

from .drill_gate_receipt import _project_stage
from .drill_pgbouncer_readiness import (
    FORMAL_PGBOUNCER_STARTUP_DEADLINE_SECONDS,
    FORMAL_PGBOUNCER_STARTUP_MAX_ATTEMPTS,
    FORMAL_PGBOUNCER_STARTUP_POLL_SECONDS,
)


FORMAL_PGBOUNCER_READINESS_TERMINAL_DEADLINE_SECONDS = (
    FORMAL_PGBOUNCER_STARTUP_DEADLINE_SECONDS
)
_STAGES = ("container_readback", "pg_isready", "show_version")
_DETAIL_CODES = frozenset(
    {
        "formal_pgbouncer_container_readback_failed",
        "formal_pgbouncer_pg_isready_failed",
        "formal_pgbouncer_show_version_failed",
    }
)


def _status(stage: Mapping[str, Any]) -> object:
    result = stage["last_result"]
    return result.get("status") if isinstance(result, Mapping) else None


def project_pgbouncer_gate_receipt(name: str, source: object) -> dict[str, Any]:
    """Reject any stage or dependency drift and persist no raw child output."""

    invalid = {
        "name": name,
        "kind": "gate",
        "passed": False,
        "detail_code": "formal_pgbouncer_readiness_receipt_invalid",
    }
    if not isinstance(source, Mapping) or set(source) != {
        "passed",
        "gate",
        "detail_code",
        "startup_deadline_seconds",
        "poll_seconds",
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
        or type(source.get("startup_deadline_seconds")) is not float
        or source.get("startup_deadline_seconds")
        != FORMAL_PGBOUNCER_STARTUP_DEADLINE_SECONDS
        or type(source.get("poll_seconds")) is not float
        or source.get("poll_seconds") != FORMAL_PGBOUNCER_STARTUP_POLL_SECONDS
        or not isinstance(raw_stages, Mapping)
        or set(raw_stages) != set(_STAGES)
    ):
        return invalid
    stages: dict[str, Any] = {}
    for stage_name in _STAGES:
        stage = _project_stage(stage_name, raw_stages.get(stage_name), role="pgbouncer")
        if (
            stage is None
            or stage["attempt_count"] > FORMAL_PGBOUNCER_STARTUP_MAX_ATTEMPTS
        ):
            return invalid
        stages[stage_name] = stage
    container, pg_ready, show_version = (stages[key] for key in _STAGES)
    consistent = bool(
        container["attempt_count"] == 1
        and _status(container)
        == ("validated" if container["passed"] else "validation_failed")
        and show_version["success_count"] <= 1
        and show_version["attempt_count"] <= pg_ready["success_count"]
        and pg_ready["success_count"] - show_version["attempt_count"] in {0, 1}
        and (
            (
                not container["passed"]
                and not passed
                and detail == "formal_pgbouncer_container_readback_failed"
                and not pg_ready["attempted"]
                and not show_version["attempted"]
            )
            or (
                container["passed"]
                and 1 <= pg_ready["attempt_count"]
                and (
                    (
                        not passed
                        and detail == "formal_pgbouncer_pg_isready_failed"
                        and _status(pg_ready) != "terminal_zero"
                        and not show_version["passed"]
                        and show_version["attempt_count"]
                        == pg_ready["success_count"]
                    )
                    or (
                        pg_ready["passed"]
                        and _status(pg_ready) == "terminal_zero"
                        and not passed
                        and detail == "formal_pgbouncer_show_version_failed"
                        and not show_version["passed"]
                        and (
                            (
                                show_version["attempt_count"]
                                == pg_ready["success_count"]
                                and _status(show_version)
                                in {
                                    "terminal_nonzero",
                                    "timeout",
                                    "exec_error",
                                    "result_invalid",
                                }
                            )
                            or (
                                show_version["attempt_count"] + 1
                                == pg_ready["success_count"]
                                and (
                                    not show_version["attempted"]
                                    or _status(show_version)
                                    in {"terminal_nonzero", "result_invalid"}
                                )
                            )
                        )
                    )
                    or (
                        pg_ready["passed"]
                        and _status(pg_ready) == "terminal_zero"
                        and passed
                        and detail is None
                        and show_version["attempt_count"]
                        == pg_ready["success_count"]
                        and show_version["success_count"] == 1
                        and show_version["passed"]
                        and _status(show_version) == "terminal_zero"
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
        "startup_deadline_seconds": FORMAL_PGBOUNCER_STARTUP_DEADLINE_SECONDS,
        "poll_seconds": FORMAL_PGBOUNCER_STARTUP_POLL_SECONDS,
        "stages": stages,
    }
