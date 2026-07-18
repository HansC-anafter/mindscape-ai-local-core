"""Exact disposable observer startup contract for the isolated drill."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from .evidence import EvidenceBudget, ObserverEvidenceStore
from .drill_names import validate_disposable_drill_name
from .service import canonical_observer_failure_detail_code
from .tracefs import INSTANCE_NAME, SIGNAL_FILTER


_PINNED_IMAGE = re.compile(r"^[A-Za-z0-9_./:-]+@sha256:[0-9a-f]{64}$")
RunCommand = Callable[..., Any]
ReadHealth = Callable[[], Mapping[str, Any]]

OBSERVER_STARTUP_DEADLINE_SECONDS = 10.0
OBSERVER_HEALTH_POLL_SECONDS = 0.25
OBSERVER_DOCKER_TERMINAL_DEADLINE_SECONDS = 60.0
OBSERVER_HEALTH_COMMAND = (
    "python /app/scripts/maintenance/postgres_signal_observer.py "
    "--healthcheck --max-health-age-seconds 30"
)


@dataclass(frozen=True)
class DisposableDrillObserverConfig:
    """Exact isolated observer container and local startup-journal contract."""

    container_name: str
    pgbouncer_container_name: str
    image_ref: str
    journal_host_root: Path
    repo_root: Path
    artifact_sha256: str
    source_commit: str

    def validate(self) -> None:
        for field_name, value in {
            "container_name": self.container_name,
            "pgbouncer_container_name": self.pgbouncer_container_name,
        }.items():
            try:
                validate_disposable_drill_name(str(value))
            except ValueError:
                raise ValueError(f"drill_observer_{field_name}_invalid")
        if not _PINNED_IMAGE.fullmatch(str(self.image_ref)):
            raise ValueError("drill_observer_image_must_be_pinned_by_sha256")
        if not re.fullmatch(r"[0-9a-f]{64}", str(self.artifact_sha256)):
            raise ValueError("drill_observer_artifact_sha256_invalid")
        if not re.fullmatch(r"[0-9a-f]{8,64}", str(self.source_commit)):
            raise ValueError("drill_observer_source_commit_invalid")
        for field_name, path in {
            "journal_host_root": self.journal_host_root,
            "repo_root": self.repo_root,
            "backend_root": self.repo_root / "backend",
            "scripts_root": self.repo_root / "scripts",
        }.items():
            candidate = Path(path)
            resolved = candidate.resolve()
            if (
                not candidate.is_absolute()
                or not resolved.is_dir()
                or candidate.is_symlink()
            ):
                raise ValueError(f"drill_observer_{field_name}_invalid")
            if any(character in str(resolved) for character in ("\n", "\r", ",")):
                raise ValueError(f"drill_observer_{field_name}_invalid")

    @property
    def image_digest(self) -> str:
        self.validate()
        return "sha256:" + self.image_ref.rpartition("@sha256:")[2]

    @property
    def evidence_host_root(self) -> Path:
        return Path(self.journal_host_root).resolve() / "signal-observer"

    def docker_argv(self) -> tuple[str, ...]:
        """Override the backend image healthcheck and preserve exact budgets."""

        self.validate()
        backend_root = (self.repo_root / "backend").resolve()
        scripts_root = (self.repo_root / "scripts").resolve()
        journal_root = self.journal_host_root.resolve()
        return (
            "docker",
            "run",
            "-d",
            "--name",
            self.container_name,
            "--init",
            "--restart",
            "no",
            "--pid",
            "host",
            "--network",
            f"container:{self.pgbouncer_container_name}",
            "--cpus",
            "0.10",
            "--memory",
            "64m",
            "--pids-limit",
            "16",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=16m",
            "--security-opt",
            "no-new-privileges:true",
            "--cap-drop",
            "ALL",
            "--cap-add",
            "SYS_ADMIN",
            "--health-cmd",
            OBSERVER_HEALTH_COMMAND,
            "--health-interval",
            "10s",
            "--health-timeout",
            "3s",
            "--health-retries",
            "3",
            "--health-start-period",
            "10s",
            "--log-driver",
            "json-file",
            "--log-opt",
            "max-size=1m",
            "--log-opt",
            "max-file=3",
            "--mount",
            f"type=bind,src={backend_root},dst=/app/backend,readonly",
            "--mount",
            f"type=bind,src={scripts_root},dst=/app/scripts,readonly",
            "--mount",
            f"type=bind,src={journal_root},dst=/app/data/runtime-database-incidents",
            "--env",
            "PYTHONPATH=/app:/app/backend",
            "--env",
            "PYTHONDONTWRITEBYTECODE=1",
            "--env",
            "RUNTIME_DATABASE_INCIDENT_DIR=/app/data/runtime-database-incidents",
            "--env",
            "POSTGRES_SIGNAL_OBSERVER_EVIDENCE_DIR="
            "/app/data/runtime-database-incidents/signal-observer",
            "--env",
            "POSTGRES_SIGNAL_OBSERVER_REPO_ROOT=/app",
            "--env",
            f"POSTGRES_SIGNAL_OBSERVER_ARTIFACT_SHA256={self.artifact_sha256}",
            "--env",
            f"POSTGRES_SIGNAL_OBSERVER_SOURCE_COMMIT={self.source_commit}",
            "--env",
            f"POSTGRES_SIGNAL_OBSERVER_IMAGE_DIGEST={self.image_digest}",
            "--env",
            "PGBOUNCER_ADMIN_URL",
            "--entrypoint",
            "python",
            self.image_ref,
            "/app/scripts/maintenance/postgres_signal_observer.py",
        )

    def redacted_spec(self) -> dict[str, Any]:
        argv = self.docker_argv()
        return {
            "container_name": self.container_name,
            "pgbouncer_container_name": self.pgbouncer_container_name,
            "image_ref": self.image_ref,
            "artifact_sha256": self.artifact_sha256,
            "source_commit": self.source_commit,
            "image_digest": self.image_digest,
            "health_command": OBSERVER_HEALTH_COMMAND,
            "docker_terminal_deadline_seconds": (
                OBSERVER_DOCKER_TERMINAL_DEADLINE_SECONDS
            ),
            "startup_deadline_seconds": OBSERVER_STARTUP_DEADLINE_SECONDS,
            "health_poll_seconds": OBSERVER_HEALTH_POLL_SECONDS,
            "secret_environment_keys": ["PGBOUNCER_ADMIN_URL"],
            "shell": False,
            "argv_sha256": hashlib.sha256("\0".join(argv).encode("utf-8")).hexdigest(),
        }


def _cleanup_disposable_observer(
    container_name: str,
    *,
    run: RunCommand,
    environment: Mapping[str, str],
) -> dict[str, bool]:
    try:
        stopped = run(
            ["docker", "stop", "--time", "5", container_name],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
            shell=False,
            env=dict(environment),
        )
        stop_succeeded = stopped.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        stop_succeeded = False
    try:
        removed = run(
            ["docker", "rm", "--force", container_name],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
            shell=False,
            env=dict(environment),
        )
        remove_succeeded = removed.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        remove_succeeded = False
    return {
        "stop_succeeded": stop_succeeded,
        "remove_succeeded": remove_succeeded,
    }


def _health_identity_matches(
    health: Mapping[str, Any],
    config: DisposableDrillObserverConfig,
) -> bool:
    return bool(
        health.get("artifact_sha256") == config.artifact_sha256
        and health.get("source_commit") == config.source_commit
        and health.get("image_digest") == config.image_digest
        and health.get("filter") == SIGNAL_FILTER
        and health.get("trace_instance") == INSTANCE_NAME
        and health.get("budget_sha256") == EvidenceBudget().sha256()
    )


def _failure_receipt(
    config: DisposableDrillObserverConfig,
    *,
    container_id: str | None,
    first_failure: str,
    health_journal_observed: bool,
    health_state: str,
    cleanup: Mapping[str, bool],
    health_failure_detail_code: str | None = None,
) -> dict[str, Any]:
    container_started = container_id is not None
    return {
        # Compatibility: `launched` means the canonical ready/health gate
        # passed. `container_started` separately records a terminal Docker
        # start that subsequently entered the fail-closed cleanup path.
        "launched": False,
        "container_started": container_started,
        "ready": False,
        "container_id": container_id,
        "first_failure": first_failure,
        "health_failure_detail_code": health_failure_detail_code,
        "health_journal_observed": health_journal_observed,
        "health_state": health_state,
        "cleanup": dict(cleanup),
        "spec": config.redacted_spec(),
    }


def launch_disposable_drill_observer(
    config: DisposableDrillObserverConfig,
    *,
    environment: Mapping[str, str] | None = None,
    run: RunCommand = subprocess.run,
    read_health: ReadHealth | None = None,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Launch once, wait only on the local journal, and clean up on first failure."""

    config.validate()
    inherited = dict(os.environ if environment is None else environment)
    if not str(inherited.get("PGBOUNCER_ADMIN_URL") or ""):
        raise ValueError("drill_observer_pgbouncer_admin_url_environment_missing")
    if config.evidence_host_root.exists() and any(config.evidence_host_root.iterdir()):
        raise ValueError("drill_observer_evidence_root_not_empty")
    try:
        completed = run(
            list(config.docker_argv()),
            check=False,
            capture_output=True,
            text=True,
            timeout=OBSERVER_DOCKER_TERMINAL_DEADLINE_SECONDS,
            shell=False,
            env=inherited,
        )
    except subprocess.TimeoutExpired:
        launch_failure = "disposable_drill_observer_launch_terminal_deadline_exceeded"
    except OSError:
        launch_failure = "disposable_drill_observer_launch_unavailable"
    else:
        launch_failure = None
    if launch_failure is not None:
        cleanup = _cleanup_disposable_observer(
            config.container_name, run=run, environment=inherited
        )
        return _failure_receipt(
            config,
            container_id=None,
            first_failure=launch_failure,
            health_journal_observed=False,
            health_state="health_unavailable",
            cleanup=cleanup,
        )
    if completed.returncode != 0:
        cleanup = _cleanup_disposable_observer(
            config.container_name, run=run, environment=inherited
        )
        return _failure_receipt(
            config,
            container_id=None,
            first_failure="disposable_drill_observer_launch_failed",
            health_journal_observed=False,
            health_state="health_unavailable",
            cleanup=cleanup,
        )
    container_id = str(completed.stdout or "").strip()
    if not re.fullmatch(r"[0-9a-f]{12,64}", container_id):
        cleanup = _cleanup_disposable_observer(
            config.container_name, run=run, environment=inherited
        )
        return _failure_receipt(
            config,
            container_id=None,
            first_failure="disposable_drill_observer_id_invalid",
            health_journal_observed=False,
            health_state="health_unavailable",
            cleanup=cleanup,
        )

    health_reader = (
        read_health or ObserverEvidenceStore(config.evidence_host_root).read_health
    )
    deadline = monotonic() + OBSERVER_STARTUP_DEADLINE_SECONDS
    health_state = "health_unavailable"
    health_journal_observed = False
    while True:
        try:
            health = dict(health_reader())
            health_journal_observed = True
            health_state = str(health.get("state") or "health_invalid")
            if health.get("ready") is True and health_state == "ready":
                if not _health_identity_matches(health, config):
                    cleanup = _cleanup_disposable_observer(
                        config.container_name,
                        run=run,
                        environment=inherited,
                    )
                    return _failure_receipt(
                        config,
                        container_id=container_id,
                        first_failure="observer_health_identity_mismatch",
                        health_journal_observed=True,
                        health_state=health_state,
                        cleanup=cleanup,
                    )
                return {
                    "launched": True,
                    "container_started": True,
                    "ready": True,
                    "container_id": container_id,
                    "health_journal_observed": True,
                    "health_state": health_state,
                    "health_failure_detail_code": None,
                    "spec": config.redacted_spec(),
                }
            if health_state.startswith("fail_closed_"):
                failure_detail_code = canonical_observer_failure_detail_code(
                    health.get("failure_detail_code") or "observer_error_unclassified"
                )
                cleanup = _cleanup_disposable_observer(
                    config.container_name,
                    run=run,
                    environment=inherited,
                )
                return _failure_receipt(
                    config,
                    container_id=container_id,
                    first_failure=health_state,
                    health_journal_observed=True,
                    health_state=health_state,
                    cleanup=cleanup,
                    health_failure_detail_code=failure_detail_code,
                )
        except RuntimeError:
            health_state = "health_unavailable"
        remaining = deadline - monotonic()
        if remaining <= 0:
            break
        sleep(min(OBSERVER_HEALTH_POLL_SECONDS, remaining))

    cleanup = _cleanup_disposable_observer(
        config.container_name,
        run=run,
        environment=inherited,
    )
    return _failure_receipt(
        config,
        container_id=container_id,
        first_failure="observer_health_startup_deadline_exceeded",
        health_journal_observed=health_journal_observed,
        health_state=health_state,
        cleanup=cleanup,
    )
