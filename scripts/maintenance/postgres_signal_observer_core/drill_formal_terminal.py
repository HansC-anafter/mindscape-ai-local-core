"""Preconditions and terminal cleanup/readback for the formal drill CLI."""

from __future__ import annotations

import secrets
import stat
import subprocess
from dataclasses import dataclass
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


FORMAL_TEMP_ROOT_MATERIALIZATION_FAILED = (
    "formal_drill_temp_root_materialization_failed"
)
FORMAL_OBSERVER_JOURNAL_PARENT_MATERIALIZATION_FAILED = (
    "formal_observer_journal_host_parent_not_materialized_before_evidence_root"
)
FORMAL_OBSERVER_EVIDENCE_ROOT_MATERIALIZATION_FAILED = (
    "formal_observer_evidence_host_root_materialization_failed"
)
FORMAL_SECRET_PRECONDITION_SERIALIZATION_FAILED = (
    "formal_drill_secret_precondition_serialization_failed"
)
FORMAL_SECRET_PRECONDITION_MATERIALIZATION_FAILED = (
    "formal_drill_secret_precondition_materialization_failed"
)
FORMAL_MATERIALIZED_PRECONDITION_VALIDATION_FAILED = (
    "formal_drill_materialized_precondition_validation_failed"
)

FORMAL_PRECONDITION_DETAIL_CODES = frozenset(
    {
        FORMAL_TEMP_ROOT_MATERIALIZATION_FAILED,
        FORMAL_OBSERVER_JOURNAL_PARENT_MATERIALIZATION_FAILED,
        FORMAL_OBSERVER_EVIDENCE_ROOT_MATERIALIZATION_FAILED,
        FORMAL_SECRET_PRECONDITION_SERIALIZATION_FAILED,
        FORMAL_SECRET_PRECONDITION_MATERIALIZATION_FAILED,
        FORMAL_MATERIALIZED_PRECONDITION_VALIDATION_FAILED,
    }
)


@dataclass(frozen=True)
class InvocationOwnedPath:
    """One filesystem object created and identity-pinned by this invocation."""

    path: Path
    device: int
    inode: int
    kind: str


@dataclass(frozen=True)
class FormalPreconditionState:
    """Invocation-owned precondition files and directories."""

    owned_files: tuple[InvocationOwnedPath, ...] = ()
    owned_directories: tuple[InvocationOwnedPath, ...] = ()
    unverified_created_paths: tuple[Path, ...] = ()

    @property
    def files(self) -> tuple[Path, ...]:
        return tuple(item.path for item in self.owned_files)


class FormalPreconditionFailure(RuntimeError):
    """Stable fail-closed precondition result without source payload details."""

    def __init__(
        self,
        detail_code: str,
        state: FormalPreconditionState,
        *,
        cleanup_completed: bool,
    ) -> None:
        if detail_code not in FORMAL_PRECONDITION_DETAIL_CODES:
            raise ValueError("formal_precondition_detail_code_invalid")
        super().__init__(detail_code)
        self.detail_code = detail_code
        self.state = state
        self.cleanup_completed = cleanup_completed


def _read_invocation_owned_path(
    path: Path, *, kind: str
) -> tuple[InvocationOwnedPath, Any]:
    metadata = path.lstat()
    return (
        InvocationOwnedPath(
            path=path,
            device=metadata.st_dev,
            inode=metadata.st_ino,
            kind=kind,
        ),
        metadata,
    )


def _validate_invocation_owned_path(
    item: InvocationOwnedPath, metadata: Any
) -> None:
    kind = item.kind
    expected_kind = stat.S_ISDIR if kind == "directory" else stat.S_ISREG
    expected_mode = 0o700 if kind == "directory" else 0o600
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not expected_kind(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != expected_mode
    ):
        raise RuntimeError("formal_precondition_path_contract_invalid")


def _create_directory(path: Path) -> None:
    path.mkdir(mode=0o700, parents=False, exist_ok=False)


def _materialize_owned_directory(
    state: FormalPreconditionState,
    path: Path,
    detail_code: str,
) -> FormalPreconditionState:
    try:
        _create_directory(path)
    except BaseException:
        raise _precondition_failure(detail_code, state) from None
    try:
        owned_path, metadata = _read_invocation_owned_path(
            path, kind="directory"
        )
    except BaseException:
        uncertain_state = FormalPreconditionState(
            owned_files=state.owned_files,
            owned_directories=state.owned_directories,
            unverified_created_paths=(*state.unverified_created_paths, path),
        )
        raise _precondition_failure(detail_code, uncertain_state) from None
    next_state = FormalPreconditionState(
        owned_files=state.owned_files,
        owned_directories=(*state.owned_directories, owned_path),
        unverified_created_paths=state.unverified_created_paths,
    )
    try:
        _validate_invocation_owned_path(owned_path, metadata)
    except BaseException:
        raise _precondition_failure(detail_code, next_state) from None
    return next_state


def _same_invocation_object(item: InvocationOwnedPath) -> bool:
    try:
        metadata = item.path.lstat()
    except FileNotFoundError:
        return False
    expected_kind = stat.S_ISDIR if item.kind == "directory" else stat.S_ISREG
    return bool(
        not stat.S_ISLNK(metadata.st_mode)
        and expected_kind(metadata.st_mode)
        and (metadata.st_dev, metadata.st_ino) == (item.device, item.inode)
    )


def _cleanup_precondition_state(
    state: FormalPreconditionState,
    *,
    preserve_nonempty_evidence: Path | None = None,
) -> bool:
    cleanup_completed = not state.unverified_created_paths
    retained_ancestors: set[Path] = set()
    if preserve_nonempty_evidence is not None:
        try:
            if (
                preserve_nonempty_evidence.is_dir()
                and any(preserve_nonempty_evidence.iterdir())
            ):
                retained_ancestors = set(preserve_nonempty_evidence.parents)
                retained_ancestors.add(preserve_nonempty_evidence)
        except OSError:
            cleanup_completed = False
    for item in reversed(state.owned_files):
        if not item.path.exists() and not item.path.is_symlink():
            continue
        if not _same_invocation_object(item):
            cleanup_completed = False
            continue
        try:
            item.path.unlink()
        except OSError:
            cleanup_completed = False
    for item in reversed(state.owned_directories):
        if item.path in retained_ancestors:
            continue
        if not item.path.exists() and not item.path.is_symlink():
            continue
        if not _same_invocation_object(item):
            cleanup_completed = False
            continue
        try:
            item.path.rmdir()
        except OSError:
            cleanup_completed = False
    return cleanup_completed


def _precondition_failure(
    detail_code: str,
    state: FormalPreconditionState,
) -> FormalPreconditionFailure:
    return FormalPreconditionFailure(
        detail_code,
        state,
        cleanup_completed=_cleanup_precondition_state(state),
    )


def prepare_formal_preconditions(
    config: FormalDrillCliConfig,
) -> FormalPreconditionState:
    bootstrap = config.bootstrap
    expected_journal_root = bootstrap.temp_root / "observer-evidence"
    expected_evidence_root = expected_journal_root / "signal-observer"
    if (
        config.observer.journal_host_root != expected_journal_root
        or config.observer.evidence_host_root != expected_evidence_root
    ):
        raise _precondition_failure(
            FORMAL_OBSERVER_JOURNAL_PARENT_MATERIALIZATION_FAILED,
            FormalPreconditionState(),
        )
    state = FormalPreconditionState()
    state = _materialize_owned_directory(
        state,
        bootstrap.temp_root,
        FORMAL_TEMP_ROOT_MATERIALIZATION_FAILED,
    )
    state = _materialize_owned_directory(
        state,
        expected_journal_root,
        FORMAL_OBSERVER_JOURNAL_PARENT_MATERIALIZATION_FAILED,
    )
    state = _materialize_owned_directory(
        state,
        expected_evidence_root,
        FORMAL_OBSERVER_EVIDENCE_ROOT_MATERIALIZATION_FAILED,
    )
    paths = [
        bootstrap.postgres_environment_path,
        bootstrap.pgbouncer_config_path,
        bootstrap.pgbouncer_userlist_path,
    ]
    try:
        assignments = {
            "POSTGRES_USER": config.client.database_user,
            "POSTGRES_PASSWORD": secrets.token_hex(16),
            "POSTGRES_DB": config.client.database_name,
        }
        payloads = [
            serialize_postgres_bootstrap_environment(assignments),
            serialize_disposable_pgbouncer_config(assignments),
            serialize_disposable_pgbouncer_userlist(assignments),
        ]
    except BaseException:
        raise _precondition_failure(
            FORMAL_SECRET_PRECONDITION_SERIALIZATION_FAILED,
            state,
        ) from None
    for path, payload in zip(paths, payloads, strict=True):
        try:
            secure_create_precondition(path, payload)
        except BaseException:
            raise _precondition_failure(
                FORMAL_SECRET_PRECONDITION_MATERIALIZATION_FAILED,
                state,
            ) from None
        try:
            owned_file, metadata = _read_invocation_owned_path(
                path, kind="file"
            )
        except BaseException:
            uncertain_state = FormalPreconditionState(
                owned_files=state.owned_files,
                owned_directories=state.owned_directories,
                unverified_created_paths=(
                    *state.unverified_created_paths,
                    path,
                ),
            )
            raise _precondition_failure(
                FORMAL_SECRET_PRECONDITION_MATERIALIZATION_FAILED,
                uncertain_state,
            ) from None
        state = FormalPreconditionState(
            owned_files=(*state.owned_files, owned_file),
            owned_directories=state.owned_directories,
            unverified_created_paths=state.unverified_created_paths,
        )
        try:
            _validate_invocation_owned_path(owned_file, metadata)
        except BaseException:
            raise _precondition_failure(
                FORMAL_SECRET_PRECONDITION_MATERIALIZATION_FAILED,
                state,
            ) from None
    return state


def _remove_local_staging(
    config: FormalDrillCliConfig,
    state: FormalPreconditionState,
    *,
    preserve_observer_evidence: bool,
) -> bool:
    return _cleanup_precondition_state(
        state,
        preserve_nonempty_evidence=(
            config.observer.evidence_host_root
            if preserve_observer_evidence
            else None
        ),
    )


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
    paths: FormalPreconditionState,
    *,
    incident_id: str,
    terminal_reason: str,
) -> dict[str, Any]:
    local_cleanup = _remove_local_staging(
        config,
        paths,
        preserve_observer_evidence=(
            terminal_reason != "formal_drill_precondition_failed"
        ),
    )
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
