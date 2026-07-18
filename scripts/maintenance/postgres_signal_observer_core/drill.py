"""Exact disposable client command for the isolated sender-attribution drill."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .drill_names import validate_disposable_drill_name


DRILL_APPLICATION_NAME = "postgres-signal-observer-drill-client"
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,62}$")
_PINNED_IMAGE = re.compile(r"^[A-Za-z0-9_./:-]+@sha256:[0-9a-f]{64}$")


RunCommand = Callable[..., Any]


@dataclass(frozen=True)
class DisposableDrillClientConfig:
    """Validated, non-shell container command with a fixed application identity."""

    container_name: str
    network_name: str
    image_ref: str
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
        if not _PINNED_IMAGE.fullmatch(str(self.image_ref)):
            raise ValueError("drill_image_must_be_pinned_by_sha256")
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
        return (
            "docker",
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
            self.image_ref,
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
            "image_ref": self.image_ref,
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
