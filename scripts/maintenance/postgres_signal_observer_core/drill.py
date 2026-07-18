"""Exact disposable client command for the isolated sender-attribution drill."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .drill_names import (
    canonical_disposable_drill_name,
    validate_disposable_drill_name,
)
from .drill_images import (
    POSTGRES_DRILL_IMAGE_ROLE,
    drill_image_digest,
    validate_drill_image_ref,
)
from .drill_docker_runtime import canonical_docker_argv


DRILL_APPLICATION_NAME = "postgres-signal-observer-drill-client"
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,62}$")
POSTGRES_SIGNAL_SENDER_EXECUTABLE = "/usr/lib/postgresql/16/bin/pg_ctl"
POSTGRES_SIGNAL_NAME = "QUIT"
POSTGRES_SIGNAL_TERMINAL_DEADLINE_SECONDS = 10.0
POSTGRES_SIGNAL_OUTPUT_BUDGET_BYTES = 4_096
POSTGRES_BACKEND_PID_MAX = 4_194_304


RunCommand = Callable[..., Any]


@dataclass(frozen=True)
class DisposableDrillClientConfig:
    """Validated, non-shell container command with a fixed application identity."""

    container_name: str
    network_name: str
    postgres_image_ref: str
    pgbouncer_host: str
    pgbouncer_port: int
    database_user: str
    database_name: str
    sleep_seconds: int = 120

    def validate(self) -> None:
        for field_name, value in {
            "container_name": self.container_name,
            "network_name": self.network_name,
            "pgbouncer_host": self.pgbouncer_host,
        }.items():
            try:
                validate_disposable_drill_name(str(value))
            except ValueError:
                raise ValueError(f"drill_{field_name}_invalid")
        for field_name, value in {
            "database_user": self.database_user,
            "database_name": self.database_name,
        }.items():
            if not _IDENTIFIER.fullmatch(str(value)):
                raise ValueError(f"drill_{field_name}_invalid")
        validate_drill_image_ref(
            self.postgres_image_ref,
            role=POSTGRES_DRILL_IMAGE_ROLE,
        )
        if not 1 <= int(self.pgbouncer_port) <= 65535:
            raise ValueError("drill_pgbouncer_port_invalid")
        if not 1 <= int(self.sleep_seconds) <= 180:
            raise ValueError("drill_sleep_seconds_out_of_bounds")

    @property
    def statement(self) -> str:
        self.validate()
        return f"SELECT pg_backend_pid(), pg_sleep({int(self.sleep_seconds)});"

    def docker_argv(self) -> tuple[str, ...]:
        """Return argv only; no shell and no credential value is accepted."""

        self.validate()
        return canonical_docker_argv(
            "run",
            "-d",
            "--name",
            self.container_name,
            "--network",
            self.network_name,
            "--cpus",
            "0.10",
            "--memory",
            "32m",
            "--pids-limit",
            "16",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=4m",
            "--security-opt",
            "no-new-privileges:true",
            "--env",
            f"PGAPPNAME={DRILL_APPLICATION_NAME}",
            "--env",
            "PGPASSWORD",
            "--entrypoint",
            "psql",
            self.postgres_image_ref,
            "-X",
            "-h",
            self.pgbouncer_host,
            "-p",
            str(int(self.pgbouncer_port)),
            "-U",
            self.database_user,
            "-d",
            self.database_name,
            "--set",
            "ON_ERROR_STOP=1",
            "--command",
            self.statement,
        )

    def redacted_spec(self) -> dict[str, Any]:
        """Return durable metadata without SQL text or secret values."""

        argv = self.docker_argv()
        return {
            "container_name": self.container_name,
            "network_name": self.network_name,
            "image_role": POSTGRES_DRILL_IMAGE_ROLE,
            "image_ref": self.postgres_image_ref,
            "image_digest": drill_image_digest(
                self.postgres_image_ref,
                role=POSTGRES_DRILL_IMAGE_ROLE,
            ),
            "application_name": DRILL_APPLICATION_NAME,
            "pgbouncer_host": self.pgbouncer_host,
            "pgbouncer_port": int(self.pgbouncer_port),
            "database_user_sha256": hashlib.sha256(
                self.database_user.encode("utf-8")
            ).hexdigest(),
            "database_name_sha256": hashlib.sha256(
                self.database_name.encode("utf-8")
            ).hexdigest(),
            "statement_sha256": hashlib.sha256(
                self.statement.encode("utf-8")
            ).hexdigest(),
            "statement_bytes": len(self.statement.encode("utf-8")),
            "sleep_seconds": int(self.sleep_seconds),
            "secret_environment_keys": ["PGPASSWORD"],
            "shell": False,
            "argv_sha256": hashlib.sha256("\0".join(argv).encode("utf-8")).hexdigest(),
        }


def launch_disposable_drill_client(
    config: DisposableDrillClientConfig,
    *,
    environment: Mapping[str, str] | None = None,
    run: RunCommand = subprocess.run,
) -> dict[str, Any]:
    """Launch through argv with PGPASSWORD inherited, never serialized."""

    inherited = dict(os.environ if environment is None else environment)
    if not str(inherited.get("PGPASSWORD") or ""):
        raise ValueError("drill_pgpassword_environment_missing")
    completed = run(
        list(config.docker_argv()),
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
        shell=False,
        env=inherited,
    )
    if completed.returncode != 0:
        raise RuntimeError("disposable_drill_client_launch_failed")
    container_id = str(completed.stdout or "").strip()
    if not re.fullmatch(r"[0-9a-f]{12,64}", container_id):
        raise RuntimeError("disposable_drill_client_id_invalid")
    return {
        "launched": True,
        "container_id": container_id,
        "spec": config.redacted_spec(),
    }


@dataclass(frozen=True)
class DisposableDrillSignalConfig:
    """Build the only permitted synthetic SIGQUIT sender command."""

    drill_suffix: str
    postgres_image_ref: str
    target_postgres_pid: int

    def validate(self) -> None:
        canonical_disposable_drill_name("postgres", self.drill_suffix)
        validate_drill_image_ref(
            self.postgres_image_ref,
            role=POSTGRES_DRILL_IMAGE_ROLE,
        )
        if (
            type(self.target_postgres_pid) is not int
            or not 1 <= self.target_postgres_pid <= POSTGRES_BACKEND_PID_MAX
        ):
            raise ValueError("drill_signal_target_postgres_pid_invalid")

    @property
    def container_name(self) -> str:
        self.validate()
        return canonical_disposable_drill_name("postgres", self.drill_suffix)

    def docker_argv(self) -> tuple[str, ...]:
        """Return one shell-free pg_ctl kill command for the target backend."""

        self.validate()
        return canonical_docker_argv(
            "exec",
            self.container_name,
            POSTGRES_SIGNAL_SENDER_EXECUTABLE,
            "kill",
            POSTGRES_SIGNAL_NAME,
            str(self.target_postgres_pid),
        )

    def redacted_spec(self) -> dict[str, Any]:
        """Return the command contract without persisting the target PID."""

        argv = self.docker_argv()
        return {
            "container_name": self.container_name,
            "image_role": POSTGRES_DRILL_IMAGE_ROLE,
            "image_ref": self.postgres_image_ref,
            "image_digest": drill_image_digest(
                self.postgres_image_ref,
                role=POSTGRES_DRILL_IMAGE_ROLE,
            ),
            "postgres_major": 16,
            "sender_executable": POSTGRES_SIGNAL_SENDER_EXECUTABLE,
            "signal_name": POSTGRES_SIGNAL_NAME,
            "target_postgres_pid_sha256": hashlib.sha256(
                str(self.target_postgres_pid).encode("ascii")
            ).hexdigest(),
            "target_postgres_pid_disclosed": False,
            "terminal_deadline_seconds": POSTGRES_SIGNAL_TERMINAL_DEADLINE_SECONDS,
            "output_budget_bytes": POSTGRES_SIGNAL_OUTPUT_BUDGET_BYTES,
            "argv_sha256": hashlib.sha256("\0".join(argv).encode("utf-8")).hexdigest(),
            "shell": False,
        }


def _signal_output_metadata(
    stdout: object,
    stderr: object,
) -> tuple[dict[str, object], bool]:
    def as_bytes(value: object) -> bytes:
        if value is None:
            return b""
        if isinstance(value, bytes):
            return value
        return str(value).encode("utf-8", errors="replace")

    stdout_bytes = as_bytes(stdout)
    stderr_bytes = as_bytes(stderr)
    over_budget = bool(
        len(stdout_bytes) > POSTGRES_SIGNAL_OUTPUT_BUDGET_BYTES
        or len(stderr_bytes) > POSTGRES_SIGNAL_OUTPUT_BUDGET_BYTES
    )
    return (
        {
            "stdout_bytes": len(stdout_bytes),
            "stdout_sha256": hashlib.sha256(stdout_bytes).hexdigest(),
            "stderr_bytes": len(stderr_bytes),
            "stderr_sha256": hashlib.sha256(stderr_bytes).hexdigest(),
            "output_disclosed": False,
            "output_budget_exceeded": over_budget,
        },
        over_budget,
    )


def send_disposable_drill_signal(
    config: DisposableDrillSignalConfig,
    *,
    run: RunCommand = subprocess.run,
) -> dict[str, Any]:
    """Send SIGQUIT only after one bounded shell-free terminal result."""

    argv = config.docker_argv()
    base_receipt: dict[str, Any] = {
        "signal_sent": False,
        "first_failure": None,
        "terminal": False,
        "target_postgres_pid": config.target_postgres_pid,
        "target_postgres_pid_scope": "required_sender_correlation_receipt",
        "spec": config.redacted_spec(),
    }
    try:
        completed = run(
            list(argv),
            check=False,
            capture_output=True,
            text=False,
            timeout=POSTGRES_SIGNAL_TERMINAL_DEADLINE_SECONDS,
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        output, _ = _signal_output_metadata(exc.stdout, exc.stderr)
        return {
            **base_receipt,
            **output,
            "first_failure": (
                "disposable_drill_signal_sender_terminal_deadline_exceeded"
            ),
        }
    except OSError:
        output, _ = _signal_output_metadata(None, None)
        return {
            **base_receipt,
            **output,
            "first_failure": "disposable_drill_signal_sender_unavailable",
        }

    output, over_budget = _signal_output_metadata(
        getattr(completed, "stdout", None),
        getattr(completed, "stderr", None),
    )
    return_code = getattr(completed, "returncode", None)
    receipt = {
        **base_receipt,
        **output,
        "terminal": True,
    }
    if type(return_code) is not int:
        receipt["first_failure"] = "disposable_drill_signal_sender_result_invalid"
        return receipt
    receipt["terminal_exit_code"] = return_code
    if over_budget:
        receipt[
            "first_failure"
        ] = "disposable_drill_signal_sender_output_budget_exceeded"
        return receipt
    if return_code != 0:
        receipt["first_failure"] = "disposable_drill_signal_sender_terminal_failure"
        return receipt
    receipt["signal_sent"] = True
    return receipt
