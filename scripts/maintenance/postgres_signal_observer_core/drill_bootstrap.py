"""Canonical disposable PostgreSQL and PgBouncer bootstrap contract."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


_PINNED_IMAGE = re.compile(r"^[a-zA-Z0-9_./-]+@sha256:[0-9a-f]{64}$")
_DRILL_SUFFIX = re.compile(r"^[0-9]{8}T[0-9]{6}Z$")

POSTGRES_DATA_TMPFS = "/var/lib/postgresql/data:rw,nosuid,size=192m"
PGBOUNCER_DECLARED_VOLUME_TMPFS = (
    "/var/lib/postgresql/data:rw,noexec,nosuid,size=1m"
)
PGBOUNCER_RUNTIME_TMPFS = "/tmp:rw,noexec,nosuid,size=4m"


def _argv_sha256(argv: tuple[str, ...]) -> str:
    return hashlib.sha256("\0".join(argv).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DisposableDrillBootstrapConfig:
    """Build the two receipt-pinned Docker argv values without secrets."""

    drill_suffix: str
    temp_root: Path
    image_ref: str

    def validate(self) -> None:
        if not _DRILL_SUFFIX.fullmatch(str(self.drill_suffix)):
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
        if not _PINNED_IMAGE.fullmatch(str(self.image_ref)):
            raise ValueError("drill_bootstrap_image_must_be_pinned_by_sha256")

    @property
    def network_name(self) -> str:
        self.validate()
        return f"runtime-db-observer-drill-{self.drill_suffix}"

    @property
    def postgres_container_name(self) -> str:
        self.validate()
        return f"runtime-db-observer-drill-postgres-{self.drill_suffix}"

    @property
    def pgbouncer_container_name(self) -> str:
        self.validate()
        return f"runtime-db-observer-drill-pgbouncer-{self.drill_suffix}"

    @property
    def image_digest(self) -> str:
        self.validate()
        return "sha256:" + self.image_ref.rpartition("@sha256:")[2]

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
        return (
            "docker",
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
            self.image_ref,
        )

    def pgbouncer_docker_argv(self) -> tuple[str, ...]:
        """Neutralize the image VOLUME with one bounded unused tmpfs."""

        self.validate()
        return (
            "docker",
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
            self.image_ref,
            "/etc/pgbouncer/pgbouncer.ini",
        )

    def redacted_spec(self) -> dict[str, Any]:
        postgres_argv = self.postgres_docker_argv()
        pgbouncer_argv = self.pgbouncer_docker_argv()
        return {
            "network_name": self.network_name,
            "postgres_container_name": self.postgres_container_name,
            "pgbouncer_container_name": self.pgbouncer_container_name,
            "image_ref": self.image_ref,
            "image_digest": self.image_digest,
            "postgres_argv": list(postgres_argv),
            "postgres_argv_sha256": _argv_sha256(postgres_argv),
            "pgbouncer_argv": list(pgbouncer_argv),
            "pgbouncer_argv_sha256": _argv_sha256(pgbouncer_argv),
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

    def validate_pgbouncer_readback(
        self,
        source: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Fail closed on any identity, mount, or tmpfs contract drift."""

        self.validate()
        failures: list[str] = []
        expected_name = f"/{self.pgbouncer_container_name}"
        expected_entrypoint = ["pgbouncer"]
        expected_command = ["/etc/pgbouncer/pgbouncer.ini"]
        expected_security = ["no-new-privileges:true"]
        expected_tmpfs = {
            "/tmp": "rw,noexec,nosuid,size=4m",
            "/var/lib/postgresql/data": "rw,noexec,nosuid,size=1m",
        }
        expected_mounts = [
            {
                "type": "bind",
                "source": str(self.pgbouncer_config_path),
                "destination": "/etc/pgbouncer/pgbouncer.ini",
                "rw": False,
            },
            {
                "type": "bind",
                "source": str(self.pgbouncer_userlist_path),
                "destination": "/etc/pgbouncer/userlist.txt",
                "rw": False,
            },
        ]
        identity_ok = bool(
            source.get("name") == expected_name
            and source.get("config_image") == self.image_ref
            and source.get("image_id") == self.image_digest
            and source.get("user") == "postgres"
            and source.get("entrypoint") == expected_entrypoint
            and source.get("cmd") == expected_command
        )
        if not identity_ok:
            failures.append("pgbouncer_bootstrap_identity_mismatch")
        resources_ok = bool(
            source.get("nano_cpus") == 100000000
            and source.get("memory_bytes") == 33554432
            and source.get("pids_limit") == 16
        )
        if not resources_ok:
            failures.append("pgbouncer_bootstrap_resource_budget_mismatch")
        isolation_ok = bool(
            source.get("read_only_rootfs") is True
            and source.get("security_opt") == expected_security
        )
        if not isolation_ok:
            failures.append("pgbouncer_bootstrap_isolation_mismatch")
        tmpfs = source.get("tmpfs")
        if not isinstance(tmpfs, Mapping) or (
            "/var/lib/postgresql/data" not in tmpfs
        ):
            failures.append("pgbouncer_declared_volume_neutralization_missing")
        elif dict(tmpfs) != expected_tmpfs:
            failures.append("pgbouncer_declared_volume_neutralization_drift")
        mounts = source.get("mounts")
        if isinstance(mounts, list) and any(
            item.get("type") == "volume" for item in mounts
        ):
            failures.append("pgbouncer_bootstrap_anonymous_volume_detected")
        if not isinstance(mounts, list) or mounts != expected_mounts:
            failures.append("pgbouncer_bootstrap_mount_contract_mismatch")
        networks = source.get("networks")
        network_ok = bool(
            isinstance(networks, list)
            and len(networks) == 1
            and networks[0].get("name") == self.network_name
        )
        if not network_ok:
            failures.append("pgbouncer_bootstrap_network_mismatch")
        state = source.get("state")
        state_ok = bool(
            isinstance(state, Mapping)
            and state.get("running") is True
            and state.get("exit_code") == 0
            and state.get("restarting") is False
            and state.get("restart_count") == 0
        )
        if not state_ok:
            failures.append("pgbouncer_bootstrap_state_unready")
        return {
            "validation_passed": not failures,
            "first_failure": failures[0] if failures else None,
            "failures": failures,
            "declared_volume_neutralized": not any(
                failure.startswith("pgbouncer_declared_volume_neutralization")
                or failure == "pgbouncer_bootstrap_anonymous_volume_detected"
                for failure in failures
            ),
            "expected_spec_sha256": hashlib.sha256(
                json.dumps(
                    self.redacted_spec(),
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest(),
        }
