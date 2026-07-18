"""Preconditions and terminal cleanup/readback for the formal drill CLI."""

from __future__ import annotations

import secrets
import subprocess
from pathlib import Path
from typing import Any, Mapping

from backend.app.services.runtime_database_incident_core.journal import (
    RuntimeDatabaseIncidentJournal,
)

from .drill_admin_url import (
    serialize_disposable_pgbouncer_config,
    serialize_disposable_pgbouncer_userlist,
)
from .drill_docker_runtime import canonical_docker_argv
from .drill_escalation import serialize_postgres_bootstrap_environment
from .drill_formal_contract import FormalDrillCliConfig
from .drill_formal_executor import FormalDockerSubprocessExecutor
from .drill_preconditions import secure_create_precondition


def prepare_formal_preconditions(config: FormalDrillCliConfig) -> list[Path]:
    bootstrap = config.bootstrap
    bootstrap.temp_root.mkdir(mode=0o700, parents=False, exist_ok=False)
    config.observer.evidence_host_root.mkdir(mode=0o700, parents=False, exist_ok=False)
    assignments = {
        "POSTGRES_USER": config.client.database_user,
        "POSTGRES_PASSWORD": secrets.token_hex(16),
        "POSTGRES_DB": config.client.database_name,
    }
    paths = [
        bootstrap.postgres_environment_path,
        bootstrap.pgbouncer_config_path,
        bootstrap.pgbouncer_userlist_path,
    ]
    payloads = [
        serialize_postgres_bootstrap_environment(assignments),
        serialize_disposable_pgbouncer_config(assignments),
        serialize_disposable_pgbouncer_userlist(assignments),
    ]
    created: list[Path] = []
    try:
        for path, payload in zip(paths, payloads, strict=True):
            secure_create_precondition(path, payload)
            created.append(path)
    except BaseException:
        for path in reversed(created):
            path.unlink(missing_ok=True)
        config.observer.evidence_host_root.rmdir()
        bootstrap.temp_root.rmdir()
        raise
    return paths


def _remove_local_staging(config: FormalDrillCliConfig, paths: list[Path]) -> bool:
    try:
        for path in reversed(paths):
            path.unlink(missing_ok=True)
        evidence_root = config.observer.evidence_host_root
        if evidence_root.exists() and not any(evidence_root.iterdir()):
            evidence_root.rmdir()
        if config.bootstrap.temp_root.exists() and not any(
            config.bootstrap.temp_root.iterdir()
        ):
            config.bootstrap.temp_root.rmdir()
    except OSError:
        return False
    return all(not path.exists() and not path.is_symlink() for path in paths)


def remaining_resource_postflight(
    config: FormalDrillCliConfig,
    executor: FormalDockerSubprocessExecutor,
) -> dict[str, Any]:
    """Prove the four disposable containers and one network are absent."""

    names = (
        config.bootstrap.postgres_container_name,
        config.bootstrap.pgbouncer_container_name,
        config.bootstrap.observer_container_name,
        config.bootstrap.client_container_name,
    )
    receipts: list[dict[str, Any]] = []
    for name in names:
        argv = canonical_docker_argv("ps", "-aq", "--filter", f"name=^/{name}$")
        try:
            completed = executor.run(
                argv,
                check=False,
                capture_output=True,
                text=False,
                timeout=10.0,
                shell=False,
            )
        except (OSError, RuntimeError, subprocess.TimeoutExpired):
            receipts.append({"resource": name, "absent": False})
            continue
        raw = getattr(completed, "stdout", None)
        absent = bool(
            getattr(completed, "returncode", None) == 0
            and isinstance(raw, bytes)
            and not raw.strip()
        )
        receipts.append({"resource": name, "absent": absent})
    argv = canonical_docker_argv(
        "network",
        "ls",
        "-q",
        "--filter",
        f"name=^{config.bootstrap.network_name}$",
    )
    try:
        completed = executor.run(
            argv,
            check=False,
            capture_output=True,
            text=False,
            timeout=10.0,
            shell=False,
        )
        raw = getattr(completed, "stdout", None)
        absent = bool(
            getattr(completed, "returncode", None) == 0
            and isinstance(raw, bytes)
            and not raw.strip()
        )
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        absent = False
    receipts.append({"resource": config.bootstrap.network_name, "absent": absent})
    return {
        "remaining_resources_verified": all(item["absent"] for item in receipts),
        "resource_readback": receipts,
        "resource_contract": "four_disposable_containers_plus_one_network",
        "raw_payload_persisted": False,
    }


def terminal_finalize(
    config: FormalDrillCliConfig,
    executor: FormalDockerSubprocessExecutor,
    paths: list[Path],
    *,
    incident_id: str,
    terminal_reason: str,
) -> dict[str, Any]:
    local_cleanup = _remove_local_staging(config, paths)
    resource_postflight = remaining_resource_postflight(config, executor)
    journal = RuntimeDatabaseIncidentJournal(config.journal_root)
    try:
        current = journal.current()
    except Exception:
        current = None
    permit_absent = bool(
        current
        and current.incident_id == incident_id
        and current.diagnostic_permit is None
    )
    resources_verified = bool(
        local_cleanup and resource_postflight["remaining_resources_verified"] is True
    )
    handback_receipt: Mapping[str, Any] | None = None
    if permit_absent and resources_verified:
        try:
            handback_receipt = journal.record_diagnostic_ownership_handback(
                incident_id,
                owner="runtime-db-incident-owner",
                terminal_reason=terminal_reason,
                remaining_resources_verified=True,
            )
        except Exception:
            handback_receipt = None
    handed_back = bool(
        isinstance(handback_receipt, Mapping)
        and handback_receipt.get("owner_after") == "none"
    )
    return {
        **resource_postflight,
        "remaining_resources_verified": resources_verified,
        "local_staging_removed": local_cleanup,
        "observer_terminal_evidence_retained": config.observer.evidence_host_root.exists(),
        "diagnostic_permit_absent": permit_absent,
        "ownership_handback_receipt": dict(handback_receipt or {}),
        "terminal_owner": "none" if handed_back else "unknown",
        "handed_back": handed_back,
    }
