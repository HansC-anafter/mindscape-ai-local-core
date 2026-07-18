"""Canonical disposable PostgreSQL and PgBouncer bootstrap contract."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .drill_names import (
    DRILL_SUFFIX_PATTERN,
    canonical_disposable_drill_name,
)
from .drill_images import (
    POSTGRES_DRILL_IMAGE_ROLE,
    drill_image_digest,
    validate_drill_image_ref,
)
from .drill_docker_runtime import canonical_docker_argv
from .drill_readback_projection import container_readback_argv


POSTGRES_DATA_TMPFS = "/var/lib/postgresql/data:rw,nosuid,size=192m"
PGBOUNCER_DECLARED_VOLUME_TMPFS = "/var/lib/postgresql/data:rw,noexec,nosuid,size=1m"
PGBOUNCER_RUNTIME_TMPFS = "/tmp:rw,noexec,nosuid,size=4m"


def _argv_sha256(argv: tuple[str, ...]) -> str:
    return hashlib.sha256("\0".join(argv).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DisposableDrillBootstrapConfig:
    """Build the two receipt-pinned Docker argv values without secrets."""

    drill_suffix: str
    temp_root: Path
    postgres_image_ref: str

    def validate(self) -> None:
        if not DRILL_SUFFIX_PATTERN.fullmatch(str(self.drill_suffix)):
            raise ValueError("drill_bootstrap_suffix_invalid")
        expected_root = Path(
            f"/private/tmp/mindscape-postgres-signal-drill-{self.drill_suffix}"
        )
        candidate = Path(self.temp_root)
        if (
            not candidate.is_absolute()
            or str(candidate) != str(expected_root)
            or candidate.is_symlink()
        ):
            raise ValueError("drill_bootstrap_temp_root_invalid")
        validate_drill_image_ref(
            self.postgres_image_ref,
            role=POSTGRES_DRILL_IMAGE_ROLE,
        )

    @property
    def network_name(self) -> str:
        self.validate()
        return canonical_disposable_drill_name("network", self.drill_suffix)

    @property
    def postgres_container_name(self) -> str:
        self.validate()
        return canonical_disposable_drill_name("postgres", self.drill_suffix)

    @property
    def pgbouncer_container_name(self) -> str:
        self.validate()
        return canonical_disposable_drill_name("pgbouncer", self.drill_suffix)

    @property
    def observer_container_name(self) -> str:
        self.validate()
        return canonical_disposable_drill_name("observer", self.drill_suffix)

    @property
    def client_container_name(self) -> str:
        self.validate()
        return canonical_disposable_drill_name("client", self.drill_suffix)

    @property
    def image_digest(self) -> str:
        return drill_image_digest(
            self.postgres_image_ref,
            role=POSTGRES_DRILL_IMAGE_ROLE,
        )

    @property
    def pgbouncer_config_path(self) -> Path:
        self.validate()
        return self.temp_root / "pgbouncer.ini"

    @property
    def postgres_environment_path(self) -> Path:
        self.validate()
        return self.temp_root / "synthetic-postgres.env"

    @property
    def pgbouncer_userlist_path(self) -> Path:
        self.validate()
        return self.temp_root / "userlist.txt"

    def postgres_docker_argv(self) -> tuple[str, ...]:
        self.validate()
        return canonical_docker_argv(
            "run",
            "-d",
            "--name",
            self.postgres_container_name,
            "--network",
            self.network_name,
            "--network-alias",
            "runtime-db-observer-drill-postgres",
            "--cpus",
            "0.50",
            "--memory",
            "256m",
            "--pids-limit",
            "64",
            "--read-only",
            "--tmpfs",
            POSTGRES_DATA_TMPFS,
            "--tmpfs",
            "/var/run/postgresql:rw,nosuid,size=8m",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=16m",
            "--security-opt",
            "no-new-privileges:true",
            "--env",
            "POSTGRES_USER",
            "--env",
            "POSTGRES_PASSWORD",
            "--env",
            "POSTGRES_DB",
            self.postgres_image_ref,
        )

    def pgbouncer_docker_argv(self) -> tuple[str, ...]:
        """Neutralize the image VOLUME with one bounded unused tmpfs."""

        self.validate()
        return canonical_docker_argv(
            "run",
            "-d",
            "--name",
            self.pgbouncer_container_name,
            "--network",
            self.network_name,
            "--user",
            "postgres",
            "--cpus",
            "0.10",
            "--memory",
            "32m",
            "--pids-limit",
            "16",
            "--read-only",
            "--tmpfs",
            PGBOUNCER_RUNTIME_TMPFS,
            "--tmpfs",
            PGBOUNCER_DECLARED_VOLUME_TMPFS,
            "--security-opt",
            "no-new-privileges:true",
            "--mount",
            "type=bind,src="
            f"{self.pgbouncer_config_path},"
            "dst=/etc/pgbouncer/pgbouncer.ini,readonly",
            "--mount",
            "type=bind,src="
            f"{self.pgbouncer_userlist_path},"
            "dst=/etc/pgbouncer/userlist.txt,readonly",
            "--entrypoint",
            "pgbouncer",
            self.postgres_image_ref,
            "/etc/pgbouncer/pgbouncer.ini",
        )

    def lifecycle_docker_argv(self) -> dict[str, tuple[str, ...]]:
        """Return every source-owned network and container lifecycle argv."""

        self.validate()
        operations = {
            "network_create": canonical_docker_argv(
                "network", "create", self.network_name
            ),
            "network_inspect": canonical_docker_argv(
                "network", "inspect", self.network_name
            ),
            "network_remove": canonical_docker_argv("network", "rm", self.network_name),
        }
        for role, container_name, attached_network_name in (
            ("postgres", self.postgres_container_name, self.network_name),
            ("pgbouncer", self.pgbouncer_container_name, self.network_name),
            ("observer", self.observer_container_name, None),
            ("client", self.client_container_name, self.network_name),
        ):
            operations[f"{role}_inspect"] = container_readback_argv(
                role=role,
                container_name=container_name,
                attached_network_name=attached_network_name,
            )
            operations[f"{role}_stop"] = canonical_docker_argv(
                "stop", "--time", "5", container_name
            )
            operations[f"{role}_remove"] = canonical_docker_argv(
                "rm", "--force", container_name
            )
        return operations

    def redacted_spec(self) -> dict[str, Any]:
        postgres_argv = self.postgres_docker_argv()
        pgbouncer_argv = self.pgbouncer_docker_argv()
        lifecycle_argv = self.lifecycle_docker_argv()
        return {
            "network_name": self.network_name,
            "postgres_container_name": self.postgres_container_name,
            "pgbouncer_container_name": self.pgbouncer_container_name,
            "observer_container_name": self.observer_container_name,
            "client_container_name": self.client_container_name,
            "image_role": POSTGRES_DRILL_IMAGE_ROLE,
            "image_ref": self.postgres_image_ref,
            "image_digest": self.image_digest,
            "postgres_argv": list(postgres_argv),
            "postgres_argv_sha256": _argv_sha256(postgres_argv),
            "pgbouncer_argv": list(pgbouncer_argv),
            "pgbouncer_argv_sha256": _argv_sha256(pgbouncer_argv),
            "lifecycle_argv": {
                operation: list(argv)
                for operation, argv in sorted(lifecycle_argv.items())
            },
            "lifecycle_argv_sha256": {
                operation: _argv_sha256(argv)
                for operation, argv in sorted(lifecycle_argv.items())
            },
            "postgres_secret_environment_keys": [
                "POSTGRES_USER",
                "POSTGRES_PASSWORD",
                "POSTGRES_DB",
            ],
            "postgres_environment_precondition": {
                "path": str(self.postgres_environment_path),
                "mode": "0600",
                "grammar": "exact_unquoted_key_value_v1",
                "shell_source": False,
                "atomic_load": "open_once_o_nofollow_fstat_bounded_fd_read",
                "required_keys": [
                    "POSTGRES_USER",
                    "POSTGRES_PASSWORD",
                    "POSTGRES_DB",
                ],
                "values_serialized": False,
            },
            "secret_file_paths": [
                str(self.postgres_environment_path),
                str(self.pgbouncer_config_path),
                str(self.pgbouncer_userlist_path),
            ],
            "pgbouncer_declared_volume_neutralization": {
                "path": "/var/lib/postgresql/data",
                "type": "tmpfs",
                "options": "rw,noexec,nosuid,size=1m",
                "budget_bytes": 1048576,
                "path_used_by_pgbouncer": False,
            },
            "shell": False,
        }
