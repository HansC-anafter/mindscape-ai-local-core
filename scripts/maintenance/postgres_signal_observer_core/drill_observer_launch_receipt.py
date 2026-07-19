"""Strict payload-free projection for one formal observer launch result."""

from __future__ import annotations

import hashlib
import re
from typing import Any, Mapping

from .service import (
    canonical_observer_failure_detail_code,
    canonical_observer_startup_phase,
)


FORMAL_OBSERVER_LAUNCH_RECEIPT_SCHEMA_VERSION = (
    "mindscape.postgres-signal-observer-formal-launch.v2"
)
FORMAL_OBSERVER_LAUNCH_FAILURES = frozenset(
    {
        "disposable_drill_observer_launch_terminal_deadline_exceeded",
        "disposable_drill_observer_launch_unavailable",
        "disposable_drill_observer_launch_failed",
        "disposable_drill_observer_id_invalid",
        "observer_health_identity_mismatch",
        "observer_health_startup_deadline_exceeded",
        "fail_closed_tracefs",
        "fail_closed_capacity_exhausted",
        "fail_closed_observer_error",
    }
)
_OBSERVER_HEALTH_STATES = frozenset(
    {
        "health_unavailable",
        "health_invalid",
        "starting",
        "ready",
        "fail_closed_tracefs",
        "fail_closed_capacity_exhausted",
        "fail_closed_observer_error",
    }
)
_PRE_CONTAINER_FAILURES = frozenset(
    {
        "disposable_drill_observer_launch_terminal_deadline_exceeded",
        "disposable_drill_observer_launch_unavailable",
        "disposable_drill_observer_launch_failed",
        "disposable_drill_observer_id_invalid",
    }
)
_STARTUP_DEADLINE_HEALTH_STATES = frozenset(
    {"health_unavailable", "health_invalid", "starting"}
)
_TERMINAL_CAPTURE_KEYS = frozenset(
    {
        "terminal",
        "exit_code",
        "stdout_present",
        "stdout_bytes",
        "stdout_sha256",
        "stderr_present",
        "stderr_bytes",
        "stderr_sha256",
        "captures_truncated",
        "hash_input",
        "output_disclosed",
    }
)


def _project_terminal_capture(source: object) -> dict[str, Any] | None:
    if not isinstance(source, Mapping):
        return None
    capture = dict(source)
    if set(capture) != _TERMINAL_CAPTURE_KEYS:
        return None
    exit_code = capture.get("exit_code")
    if type(exit_code) is not int or exit_code == 0:
        return None
    if (
        capture.get("terminal") is not True
        or capture.get("captures_truncated") is not False
        or type(capture.get("hash_input")) is not str
        or capture.get("hash_input") != "full_raw_subprocess_capture_bytes"
        or capture.get("output_disclosed") is not False
    ):
        return None
    empty_sha256 = hashlib.sha256(b"").hexdigest()
    for prefix in ("stdout", "stderr"):
        present = capture.get(f"{prefix}_present")
        byte_count = capture.get(f"{prefix}_bytes")
        sha256 = capture.get(f"{prefix}_sha256")
        if (
            type(present) is not bool
            or type(byte_count) is not int
            or byte_count < 0
            or present is not (byte_count > 0)
            or type(sha256) is not str
            or re.fullmatch(r"[0-9a-f]{64}", sha256) is None
            or (byte_count == 0 and sha256 != empty_sha256)
        ):
            return None
    return capture


def _failure_state_correlates(
    first_failure: str,
    *,
    container_started: bool,
    health_journal_observed: bool,
    health_state: str,
) -> bool:
    if first_failure in _PRE_CONTAINER_FAILURES:
        return (
            container_started is False
            and health_journal_observed is False
            and health_state == "health_unavailable"
        )
    if first_failure == "observer_health_identity_mismatch":
        return (
            container_started is True
            and health_journal_observed is True
            and health_state == "ready"
        )
    if first_failure == "observer_health_startup_deadline_exceeded":
        return (
            container_started is True
            and health_state in _STARTUP_DEADLINE_HEALTH_STATES
            and (
                health_state == "health_unavailable"
                or health_journal_observed is True
            )
        )
    return (
        first_failure.startswith("fail_closed_")
        and container_started is True
        and health_journal_observed is True
        and health_state == first_failure
    )


def project_formal_observer_launch_receipt(
    source: object,
) -> dict[str, Any] | None:
    """Project one launcher receipt without paths, ids, env, or raw payloads."""

    if not isinstance(source, Mapping):
        return None
    receipt = dict(source)
    bool_fields = (
        "launched",
        "container_started",
        "ready",
        "health_journal_observed",
    )
    if any(type(receipt.get(field)) is not bool for field in bool_fields):
        return None
    container_id = receipt.get("container_id")
    container_started = receipt["container_started"]
    if container_started is not bool(
        type(container_id) is str
        and re.fullmatch(r"[0-9a-f]{12,64}", container_id)
    ):
        return None
    health_state = receipt.get("health_state")
    health_detail = receipt.get("health_failure_detail_code")
    health_startup_phase = receipt.get("health_startup_phase")
    if type(health_state) is not str or health_state not in _OBSERVER_HEALTH_STATES:
        return None
    success = receipt["ready"] is True
    common_keys = {
        "launched",
        "container_started",
        "ready",
        "container_id",
        "health_failure_detail_code",
        "health_journal_observed",
        "health_state",
        "health_startup_phase",
        "pgbouncer_admin_environment",
        "spec",
    }
    projected: dict[str, Any] = {
        "schema_version": FORMAL_OBSERVER_LAUNCH_RECEIPT_SCHEMA_VERSION,
        "launched": receipt["launched"],
        "container_started": container_started,
        "ready": receipt["ready"],
        "container_id_persisted": False,
        "health_journal_observed": receipt["health_journal_observed"],
        "health_state": health_state,
        "health_startup_phase": health_startup_phase,
        "health_failure_detail_code": health_detail,
        "raw_payload_persisted": False,
    }
    if success:
        if (
            set(receipt) != common_keys
            or receipt["launched"] is not True
            or container_started is not True
            or receipt["health_journal_observed"] is not True
            or health_state != "ready"
            or health_startup_phase is not None
            or health_detail is not None
        ):
            return None
        projected["first_failure"] = None
        projected["cleanup"] = {
            "attempted": False,
            "stop_succeeded": None,
            "remove_succeeded": None,
        }
        return projected

    allowed_keys = common_keys | {"first_failure", "cleanup"}
    first_failure = receipt.get("first_failure")
    if "docker_terminal_result" in receipt:
        allowed_keys.add("docker_terminal_result")
    cleanup = receipt.get("cleanup")
    if (
        set(receipt) != allowed_keys
        or receipt["launched"] is not False
        or receipt["ready"] is not False
        or type(first_failure) is not str
        or first_failure not in FORMAL_OBSERVER_LAUNCH_FAILURES
        or not _failure_state_correlates(
            first_failure,
            container_started=container_started,
            health_journal_observed=receipt["health_journal_observed"],
            health_state=health_state,
        )
        or not isinstance(cleanup, Mapping)
        or set(cleanup) != {"stop_succeeded", "remove_succeeded"}
        or any(type(cleanup.get(field)) is not bool for field in cleanup)
    ):
        return None
    fail_closed = first_failure.startswith("fail_closed_")
    startup_deadline = first_failure == "observer_health_startup_deadline_exceeded"
    if startup_deadline and health_state == "starting":
        if canonical_observer_startup_phase(health_startup_phase) is None:
            return None
    elif health_startup_phase is not None:
        return None
    if fail_closed:
        if type(health_detail) is not str:
            return None
    elif health_detail is not None:
        return None
    if (
        fail_closed
        and canonical_observer_failure_detail_code(health_detail) != health_detail
    ):
        return None
    terminal_result = receipt.get("docker_terminal_result")
    if first_failure == "disposable_drill_observer_launch_failed":
        projected_terminal = _project_terminal_capture(terminal_result)
        if projected_terminal is None:
            return None
        projected["docker_terminal_result"] = projected_terminal
    elif terminal_result is not None:
        return None
    projected["first_failure"] = first_failure
    projected["cleanup"] = {
        "attempted": True,
        "stop_succeeded": cleanup["stop_succeeded"],
        "remove_succeeded": cleanup["remove_succeeded"],
    }
    return projected
