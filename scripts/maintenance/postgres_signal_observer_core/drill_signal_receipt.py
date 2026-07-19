"""Payload-free projection for the synthetic signal sender receipt."""

from __future__ import annotations

import hashlib
import re
from typing import Any, Mapping


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
_FAILURES = frozenset(
    {
        "disposable_drill_signal_sender_terminal_deadline_exceeded",
        "disposable_drill_signal_sender_unavailable",
        "disposable_drill_signal_sender_result_invalid",
        "disposable_drill_signal_sender_output_budget_exceeded",
        "disposable_drill_signal_sender_terminal_failure",
    }
)
_BASE_KEYS = frozenset(
    {
        "signal_sent",
        "first_failure",
        "terminal",
        "target_postgres_pid",
        "target_postgres_pid_scope",
        "spec",
        "stdout_bytes",
        "stdout_sha256",
        "stderr_bytes",
        "stderr_sha256",
        "output_disclosed",
        "output_budget_exceeded",
    }
)


def _capture_valid(source: Mapping[str, Any], stream: str) -> bool:
    byte_count = source.get(f"{stream}_bytes")
    digest = source.get(f"{stream}_sha256")
    return bool(
        type(byte_count) is int
        and byte_count >= 0
        and type(digest) is str
        and _SHA256.fullmatch(digest)
        and (byte_count != 0 or digest == _EMPTY_SHA256)
    )


def project_formal_signal_sender_receipt(source: object) -> dict[str, Any] | None:
    """Validate the canonical sender result while omitting PID, argv, and output."""

    if not isinstance(source, Mapping):
        return None
    terminal = source.get("terminal")
    failure = source.get("first_failure")
    exit_present = "terminal_exit_code" in source
    expected_keys = _BASE_KEYS | ({"terminal_exit_code"} if exit_present else set())
    if (
        set(source) != expected_keys
        or type(source.get("signal_sent")) is not bool
        or type(terminal) is not bool
        or not (failure is None or (type(failure) is str and failure in _FAILURES))
        or type(source.get("target_postgres_pid")) is not int
        or source.get("target_postgres_pid", 0) < 1
        or source.get("target_postgres_pid_scope")
        != "required_sender_correlation_receipt"
        or not isinstance(source.get("spec"), Mapping)
        or source.get("output_disclosed") is not False
        or type(source.get("output_budget_exceeded")) is not bool
        or not _capture_valid(source, "stdout")
        or not _capture_valid(source, "stderr")
    ):
        return None
    exit_code = source.get("terminal_exit_code")
    if exit_present and type(exit_code) is not int:
        return None
    sent = source["signal_sent"] is True
    over_budget = source["output_budget_exceeded"] is True
    valid_outcome = (
        sent
        and terminal is True
        and failure is None
        and exit_present
        and exit_code == 0
        and not over_budget
    ) or (
        not sent
        and (
            (
                failure == "disposable_drill_signal_sender_terminal_failure"
                and terminal is True
                and exit_present
                and exit_code != 0
                and not over_budget
            )
            or (
                failure == "disposable_drill_signal_sender_output_budget_exceeded"
                and terminal is True
                and exit_present
                and over_budget
            )
            or (
                failure == "disposable_drill_signal_sender_result_invalid"
                and terminal is True
                and not exit_present
                and not over_budget
            )
            or (
                failure == "disposable_drill_signal_sender_terminal_deadline_exceeded"
                and terminal is False
                and not exit_present
            )
            or (
                failure == "disposable_drill_signal_sender_unavailable"
                and terminal is False
                and not exit_present
                and not over_budget
            )
        )
    )
    if not valid_outcome:
        return None
    projection: dict[str, Any] = {
        "signal_sent": sent,
        "terminal": terminal,
        "first_failure": failure,
        "stdout_present": source["stdout_bytes"] > 0,
        "stdout_bytes": source["stdout_bytes"],
        "stdout_sha256": source["stdout_sha256"],
        "stderr_present": source["stderr_bytes"] > 0,
        "stderr_bytes": source["stderr_bytes"],
        "stderr_sha256": source["stderr_sha256"],
        "captures_truncated": False,
        "hash_input": "full_raw_subprocess_capture_bytes",
        "output_disclosed": False,
        "output_budget_exceeded": over_budget,
        "target_postgres_pid_disclosed": False,
    }
    if exit_present:
        projection["terminal_exit_code"] = exit_code
    return projection
