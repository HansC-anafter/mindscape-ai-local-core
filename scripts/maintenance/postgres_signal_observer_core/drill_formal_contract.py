"""Exact source-owned identities for the executable formal drill entry."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .drill import DisposableDrillClientConfig
from .drill_bootstrap import DisposableDrillBootstrapConfig
from .drill_formal_sequence import canonical_formal_drill_sequence
from .drill_observer import DisposableDrillObserverConfig


@dataclass(frozen=True)
class FormalDrillCliConfig:
    """All source-owned identities required by the executable facade entry."""

    bootstrap: DisposableDrillBootstrapConfig
    observer: DisposableDrillObserverConfig
    client: DisposableDrillClientConfig
    journal_root: Path
    artifact_sha256: str

    def validate(self) -> None:
        self.bootstrap.validate()
        self.client.validate()
        if not re.fullmatch(r"[0-9a-f]{64}", self.artifact_sha256):
            raise ValueError("formal_drill_artifact_sha256_invalid")
        if not self.journal_root.is_absolute():
            raise ValueError("formal_drill_journal_root_invalid")

    def validate_materialized(self) -> None:
        """Validate mount-backed observer argv only after permit-gated staging."""

        self.validate()
        canonical_formal_drill_sequence(
            self.bootstrap,
            self.observer,
            self.client,
        )


def build_formal_drill_cli_config(
    *,
    drill_suffix: str,
    temp_root: Path,
    journal_root: Path,
    postgres_image_ref: str,
    observer_image_ref: str,
    repo_root: Path,
    artifact_sha256: str,
    source_commit: str,
    database_user: str,
    database_name: str,
    pgbouncer_port: int,
    sleep_seconds: int,
) -> FormalDrillCliConfig:
    """Build every role from one canonical CLI-owned identity set."""

    bootstrap = DisposableDrillBootstrapConfig(
        drill_suffix=drill_suffix,
        temp_root=temp_root,
        postgres_image_ref=postgres_image_ref,
    )
    observer = DisposableDrillObserverConfig(
        container_name=bootstrap.observer_container_name,
        pgbouncer_container_name=bootstrap.pgbouncer_container_name,
        observer_image_ref=observer_image_ref,
        journal_host_root=journal_root,
        evidence_host_root=temp_root / "observer-evidence" / "signal-observer",
        repo_root=repo_root,
        artifact_sha256=artifact_sha256,
        source_commit=source_commit,
    )
    client = DisposableDrillClientConfig(
        container_name=bootstrap.client_container_name,
        network_name=bootstrap.network_name,
        postgres_image_ref=postgres_image_ref,
        pgbouncer_host=bootstrap.pgbouncer_container_name,
        pgbouncer_port=pgbouncer_port,
        database_user=database_user,
        database_name=database_name,
        sleep_seconds=sleep_seconds,
    )
    config = FormalDrillCliConfig(
        bootstrap=bootstrap,
        observer=observer,
        client=client,
        journal_root=journal_root,
        artifact_sha256=artifact_sha256,
    )
    config.validate()
    return config
