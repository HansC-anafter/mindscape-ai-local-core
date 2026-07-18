"""Fail-closed delivery gate for formal container escalation results."""

from __future__ import annotations

import hashlib
import os
import re
import stat
import subprocess
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .drill_docker_runtime import (
    CANONICAL_DOCKER_CLI_ENTRY_PATH,
    validate_canonical_docker_argv,
)


FORMAL_DOCKER_OPERATION_RESULT_KINDS = {
    "docker_create_disposable_isolated_network": "identifier",
    "docker_run_disposable_isolated_postgresql_bootstrap": "identifier",
    "docker_run_disposable_isolated_pgbouncer_bootstrap": "identifier",
    "docker_run_disposable_isolated_observer": "identifier",
    "docker_run_disposable_isolated_client": "identifier",
    "docker_exec_disposable_isolated_signal_sender": "terminal_zero",
    "docker_stop_disposable_isolated_client": "terminal_zero",
    "docker_remove_disposable_isolated_client": "terminal_zero",
    "docker_stop_disposable_isolated_observer": "terminal_zero",
    "docker_remove_disposable_isolated_observer": "terminal_zero",
    "docker_stop_disposable_isolated_pgbouncer": "terminal_zero",
    "docker_remove_disposable_isolated_pgbouncer": "terminal_zero",
    "docker_stop_disposable_isolated_postgresql": "terminal_zero",
    "docker_remove_disposable_isolated_postgresql": "terminal_zero",
    "docker_remove_disposable_isolated_network": "terminal_zero",
}
FORMAL_POSTGRES_STARTUP_DEADLINE_SECONDS = 10.0
FORMAL_POSTGRES_STARTUP_POLL_SECONDS = 0.25
FORMAL_DOCKER_OPERATION_CLASSES = frozenset(FORMAL_DOCKER_OPERATION_RESULT_KINDS)
MAX_FORMAL_EXEC_OUTPUT_BYTES = 65_536
_CONTAINER_ID = re.compile(r"^[0-9a-f]{64}$")
_CANONICAL_ENV_VALUE = re.compile(r"^[A-Za-z0-9._~:/+@%-]+$")
MAX_POSTGRES_ENVIRONMENT_BYTES = 4_096
POSTGRES_BOOTSTRAP_ENVIRONMENT_KEYS = (
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
)


def serialize_postgres_bootstrap_environment(
    assignments: Mapping[str, str],
) -> bytes:
    """Produce the only accepted non-shell key=value grammar."""

    if set(assignments) != set(POSTGRES_BOOTSTRAP_ENVIRONMENT_KEYS):
        raise RuntimeError("formal_escalation_postgres_environment_keys_invalid")
    lines: list[str] = []
    for key in POSTGRES_BOOTSTRAP_ENVIRONMENT_KEYS:
        value = assignments.get(key)
        if not isinstance(value, str) or not value:
            raise RuntimeError(
                "formal_escalation_postgres_environment_required_value_missing"
            )
        if not _CANONICAL_ENV_VALUE.fullmatch(value):
            raise RuntimeError(
                "formal_escalation_postgres_environment_value_grammar_invalid"
            )
        lines.append(f"{key}={value}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def load_postgres_bootstrap_environment(path: Path) -> dict[str, str]:
    """Open once, verify the fd, and load exact assignments without a shell."""

    candidate = Path(path)
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if not isinstance(nofollow, int):
        raise RuntimeError(
            "formal_escalation_postgres_environment_nofollow_unavailable"
        )
    flags = os.O_RDONLY | nofollow
    cloexec = getattr(os, "O_CLOEXEC", None)
    if isinstance(cloexec, int):
        flags |= cloexec
    try:
        file_descriptor = os.open(candidate, flags)
    except OSError as exc:
        raise RuntimeError(
            "formal_escalation_postgres_environment_unavailable"
        ) from exc
    try:
        metadata = os.fstat(file_descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_size > MAX_POSTGRES_ENVIRONMENT_BYTES
        ):
            raise RuntimeError(
                "formal_escalation_postgres_environment_contract_invalid"
            )
        chunks: list[bytes] = []
        remaining = MAX_POSTGRES_ENVIRONMENT_BYTES + 1
        while remaining > 0:
            chunk = os.read(file_descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        if len(content) > MAX_POSTGRES_ENVIRONMENT_BYTES:
            raise RuntimeError(
                "formal_escalation_postgres_environment_contract_invalid"
            )
    except OSError as exc:
        raise RuntimeError(
            "formal_escalation_postgres_environment_unavailable"
        ) from exc
    finally:
        os.close(file_descriptor)
    try:
        decoded = content.decode("utf-8")
    except UnicodeError as exc:
        raise RuntimeError(
            "formal_escalation_postgres_environment_assignment_invalid"
        ) from exc
    assignments: dict[str, str] = {}
    for source in decoded.splitlines():
        if "=" not in source:
            raise RuntimeError(
                "formal_escalation_postgres_environment_assignment_invalid"
            )
        key, value = source.split("=", 1)
        if key not in POSTGRES_BOOTSTRAP_ENVIRONMENT_KEYS:
            raise RuntimeError(
                "formal_escalation_postgres_environment_assignment_unexpected"
            )
        if key in assignments:
            raise RuntimeError(
                "formal_escalation_postgres_environment_assignment_duplicate"
            )
        assignments[key] = value
    if any(not assignments.get(key) for key in POSTGRES_BOOTSTRAP_ENVIRONMENT_KEYS):
        raise RuntimeError(
            "formal_escalation_postgres_environment_required_value_missing"
        )
    if content != serialize_postgres_bootstrap_environment(assignments):
        raise RuntimeError(
            "formal_escalation_postgres_environment_canonical_encoding_invalid"
        )
    return assignments


def execute_formal_postgres_bootstrap(
    argv: Sequence[str],
    *,
    environment_path: Path,
    base_environment: Mapping[str, str] | None = None,
    run: Callable[..., Any] = subprocess.run,
) -> int:
    """Atomically load the 0600 precondition into one shell-free child env."""

    try:
        exact_argv = validate_canonical_docker_argv(argv)
    except ValueError as exc:
        raise RuntimeError("formal_escalation_postgres_argv_invalid") from exc
    if exact_argv[:3] != (
        str(CANONICAL_DOCKER_CLI_ENTRY_PATH),
        "run",
        "-d",
    ):
        raise RuntimeError("formal_escalation_postgres_argv_invalid")
    environment_keys = tuple(
        exact_argv[index + 1]
        for index in range(len(exact_argv) - 1)
        if exact_argv[index] == "--env"
    )
    if environment_keys != POSTGRES_BOOTSTRAP_ENVIRONMENT_KEYS:
        raise RuntimeError("formal_escalation_postgres_argv_environment_drift")
    loaded = load_postgres_bootstrap_environment(Path(environment_path))
    environment = dict(base_environment if base_environment is not None else os.environ)
    environment.update(loaded)
    completed = run(
        exact_argv,
        check=False,
        env=environment,
        shell=False,
    )
    return_code = getattr(completed, "returncode", None)
    if type(return_code) is not int:
        raise RuntimeError("formal_escalation_postgres_child_result_invalid")
    return return_code


def validate_formal_exec_result(
    source: Mapping[str, Any],
    *,
    operation_class: str,
) -> dict[str, Any]:
    """Permit container-id delivery only from a terminal successful result."""

    if operation_class not in FORMAL_DOCKER_OPERATION_CLASSES:
        raise ValueError("formal_escalation_operation_class_invalid")
    if not isinstance(source, Mapping):
        raise ValueError("formal_escalation_exec_result_invalid")
    output = source.get("output")
    output_text = output if isinstance(output, str) else ""
    output_bytes = len(output_text.encode("utf-8"))
    receipt: dict[str, Any] = {
        "operation_class": operation_class,
        "terminal": False,
        "poll_required": False,
        "delivery_allowed": False,
        "first_failure": None,
        "output_bytes": output_bytes,
        "output_sha256": hashlib.sha256(output_text.encode("utf-8")).hexdigest(),
        "secret_or_output_value_disclosed": False,
    }
    if "session_id" in source or "exit_code" not in source:
        receipt.update(
            {
                "poll_required": True,
                "first_failure": "formal_escalation_cli_nonterminal_result",
            }
        )
        return receipt
    if output_bytes > MAX_FORMAL_EXEC_OUTPUT_BYTES:
        receipt.update(
            {
                "terminal": True,
                "first_failure": "formal_escalation_exec_output_budget_exceeded",
            }
        )
        return receipt
    exit_code = source.get("exit_code")
    if type(exit_code) is not int:
        receipt.update(
            {
                "terminal": True,
                "first_failure": "formal_escalation_exec_exit_code_invalid",
            }
        )
        return receipt
    receipt["terminal"] = True
    receipt["exit_code"] = exit_code
    if exit_code != 0:
        capture = source.get("terminal_nonzero_capture")
        if isinstance(capture, Mapping):
            allowed_capture_keys = {
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
            exact_capture = dict(capture)
            if (
                set(exact_capture) == allowed_capture_keys
                and exact_capture.get("terminal") is True
                and exact_capture.get("exit_code") == exit_code
                and exact_capture.get("output_disclosed") is False
                and exact_capture.get("hash_input")
                == "full_raw_subprocess_capture_bytes"
            ):
                receipt["terminal_nonzero_capture"] = exact_capture
        receipt["first_failure"] = "formal_escalation_cli_terminal_failure"
        return receipt
    result_kind = FORMAL_DOCKER_OPERATION_RESULT_KINDS[operation_class]
    if result_kind == "identifier":
        container_id = output_text.strip()
        if not _CONTAINER_ID.fullmatch(container_id):
            receipt["first_failure"] = "formal_escalation_container_id_invalid"
            return receipt
        receipt["container_id"] = container_id
    receipt["delivery_allowed"] = True
    return receipt


def terminal_capture_metadata(
    stdout: object,
    stderr: object,
    *,
    exit_code: int,
) -> dict[str, Any]:
    """Hash full raw binary captures without persisting subprocess payload."""

    if type(exit_code) is not int:
        raise ValueError("formal_escalation_terminal_exit_code_invalid")

    def as_bytes(value: object) -> bytes:
        if value is None:
            return b""
        if isinstance(value, bytes):
            return value
        raise ValueError("formal_escalation_terminal_capture_type_invalid")

    stdout_bytes = as_bytes(stdout)
    stderr_bytes = as_bytes(stderr)
    return {
        "terminal": True,
        "exit_code": exit_code,
        "stdout_present": bool(stdout_bytes),
        "stdout_bytes": len(stdout_bytes),
        "stdout_sha256": hashlib.sha256(stdout_bytes).hexdigest(),
        "stderr_present": bool(stderr_bytes),
        "stderr_bytes": len(stderr_bytes),
        "stderr_sha256": hashlib.sha256(stderr_bytes).hexdigest(),
        "captures_truncated": False,
        "hash_input": "full_raw_subprocess_capture_bytes",
        "output_disclosed": False,
    }


def terminal_nonzero_capture_metadata(
    stdout: object,
    stderr: object,
    *,
    exit_code: int,
) -> dict[str, Any]:
    """Hash full raw binary captures from one terminal nonzero result."""

    if type(exit_code) is not int or exit_code == 0:
        raise ValueError("formal_escalation_terminal_nonzero_exit_code_invalid")
    return terminal_capture_metadata(stdout, stderr, exit_code=exit_code)
