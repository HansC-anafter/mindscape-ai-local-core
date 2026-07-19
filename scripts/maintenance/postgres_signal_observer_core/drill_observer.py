from __future__ import annotations

import hashlib
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from .evidence import EvidenceBudget, ObserverEvidenceStore
from .drill_admin_url import (
    DisposableDrillObserverEnvironment,
    PGBOUNCER_ADMIN_ENVIRONMENT_KEY,
)
from .drill_escalation import terminal_nonzero_capture_metadata
from .drill_names import validate_disposable_drill_name
from .drill_images import (
    OBSERVER_BACKEND_IMAGE_ROLE,
    drill_image_digest,
    validate_drill_image_ref,
)
from .drill_docker_runtime import canonical_docker_argv
from .artifact import OBSERVER_ARTIFACT_POSTGRES_DOCKERFILE
from .service import (
    canonical_observer_failure_detail_code,
    canonical_observer_startup_phase,
)
from .tracefs import INSTANCE_NAME, SIGNAL_FILTER


RunCommand = Callable[..., Any]
ReadHealth = Callable[[], Mapping[str, Any]]

OBSERVER_STARTUP_DEADLINE_SECONDS = 10.0
OBSERVER_HEALTH_POLL_SECONDS = 0.25
OBSERVER_DOCKER_TERMINAL_DEADLINE_SECONDS = 60.0
OBSERVER_HEALTH_COMMAND = (
    "/usr/local/bin/python /app/scripts/maintenance/postgres_signal_observer.py "
    "--healthcheck --max-health-age-seconds 30"
)


@dataclass(frozen=True)
class DisposableDrillObserverConfig:
    container_name: str
    pgbouncer_container_name: str
    observer_image_ref: str
    journal_host_root: Path
    evidence_host_root: Path
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
        validate_drill_image_ref(
            self.observer_image_ref,
            role=OBSERVER_BACKEND_IMAGE_ROLE,
        )
        if not re.fullmatch(r"[0-9a-f]{64}", str(self.artifact_sha256)):
            raise ValueError("drill_observer_artifact_sha256_invalid")
        if not re.fullmatch(r"[0-9a-f]{8,64}", str(self.source_commit)):
            raise ValueError("drill_observer_source_commit_invalid")
        for field_name, path in {
            "journal_host_root": self.journal_host_root,
            "evidence_host_root": self.evidence_host_root,
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
        postgres_dockerfile = (
            self.repo_root.resolve() / OBSERVER_ARTIFACT_POSTGRES_DOCKERFILE
        )
        if self.journal_host_root.resolve() == self.evidence_host_root.resolve():
            raise ValueError("drill_observer_journal_role_sources_conflict")
        if (
            postgres_dockerfile.is_symlink()
            or not postgres_dockerfile.is_file()
            or postgres_dockerfile.resolve() != postgres_dockerfile
            or any(
                character in str(postgres_dockerfile)
                for character in ("\n", "\r", ",")
            )
        ):
            raise ValueError("drill_observer_postgres_dockerfile_invalid")

    @property
    def image_digest(self) -> str:
        return drill_image_digest(
            self.observer_image_ref,
            role=OBSERVER_BACKEND_IMAGE_ROLE,
        )

    def docker_argv(self) -> tuple[str, ...]:
        self.validate()
        backend_root = (self.repo_root / "backend").resolve()
        scripts_root = (self.repo_root / "scripts").resolve()
        postgres_dockerfile = (
            self.repo_root.resolve() / OBSERVER_ARTIFACT_POSTGRES_DOCKERFILE
        )
        journal_root = self.journal_host_root.resolve()
        evidence_root = self.evidence_host_root.resolve()
        return canonical_docker_argv(
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
            "--health-start-interval",
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
            f"type=bind,src={postgres_dockerfile},"
            "dst=/app/docker/postgres/Dockerfile,readonly",
            "--mount",
            f"type=bind,src={journal_root},dst=/app/data/runtime-database-incidents",
            "--mount",
            f"type=bind,src={evidence_root},"
            "dst=/app/data/runtime-database-incidents/signal-observer",
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
            self.observer_image_ref,
            "/app/scripts/maintenance/postgres_signal_observer.py",
        )

    def redacted_spec(self) -> dict[str, Any]:
        argv = self.docker_argv()
        return {
            "container_name": self.container_name,
            "pgbouncer_container_name": self.pgbouncer_container_name,
            "image_role": OBSERVER_BACKEND_IMAGE_ROLE,
            "image_ref": self.observer_image_ref,
            "artifact_sha256": self.artifact_sha256,
            "source_commit": self.source_commit,
            "image_digest": self.image_digest,
            "health_command": OBSERVER_HEALTH_COMMAND,
            "docker_terminal_deadline_seconds": (
                OBSERVER_DOCKER_TERMINAL_DEADLINE_SECONDS
            ),
            "startup_deadline_seconds": OBSERVER_STARTUP_DEADLINE_SECONDS,
            "health_poll_seconds": OBSERVER_HEALTH_POLL_SECONDS,
            "secret_environment_keys": [PGBOUNCER_ADMIN_ENVIRONMENT_KEY],
            "pgbouncer_admin_environment_contract": {
                "source": "canonical_isolated_preconditions",
                "child_environment_only": True,
                "host_environment_value_inherited": False,
                "url_or_credential_disclosed": False,
            },
            "artifact_source_contract": {
                "relative_source": OBSERVER_ARTIFACT_POSTGRES_DOCKERFILE,
                "container_target": "/app/docker/postgres/Dockerfile",
                "read_only": True,
                "host_source_disclosed": False,
            },
            "journal_role_contract": {
                "incident_journal_target": "/app/data/runtime-database-incidents",
                "observer_evidence_target": "/app/data/runtime-database-incidents/signal-observer",
                "distinct_host_sources": self.journal_host_root.resolve()
                != self.evidence_host_root.resolve(),
                "host_sources_disclosed": False,
            },
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
            list(canonical_docker_argv("stop", "--time", "5", container_name)),
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
            list(canonical_docker_argv("rm", "--force", container_name)),
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
    return {"stop_succeeded": stop_succeeded, "remove_succeeded": remove_succeeded}


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
    environment_contract_spec: Mapping[str, Any],
    health_startup_phase: str | None = None,
    health_failure_detail_code: str | None = None,
    docker_terminal_result: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    container_started = container_id is not None
    receipt = {
        "launched": False,
        "container_started": container_started,
        "ready": False,
        "container_id": container_id,
        "first_failure": first_failure,
        "health_failure_detail_code": health_failure_detail_code,
        "health_journal_observed": health_journal_observed,
        "health_state": health_state,
        "health_startup_phase": health_startup_phase,
        "cleanup": dict(cleanup),
        "pgbouncer_admin_environment": dict(environment_contract_spec),
        "spec": config.redacted_spec(),
    }
    if docker_terminal_result is not None:
        receipt["docker_terminal_result"] = dict(docker_terminal_result)
    return receipt


def launch_disposable_drill_observer(
    config: DisposableDrillObserverConfig,
    *,
    environment_contract: DisposableDrillObserverEnvironment,
    run: RunCommand = subprocess.run,
    read_health: ReadHealth | None = None,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    config.validate()
    if not isinstance(environment_contract, DisposableDrillObserverEnvironment):
        raise TypeError("drill_observer_environment_contract_required")
    environment_contract.validate_for(config.pgbouncer_container_name)
    observer_environment = environment_contract.subprocess_environment()
    executor_environment = environment_contract.executor_environment()
    environment_contract_spec = environment_contract.redacted_spec()
    if config.evidence_host_root.exists() and any(config.evidence_host_root.iterdir()):
        raise ValueError("drill_observer_evidence_root_not_empty")
    try:
        completed = run(
            list(config.docker_argv()),
            check=False,
            capture_output=True,
            text=False,
            timeout=OBSERVER_DOCKER_TERMINAL_DEADLINE_SECONDS,
            shell=False,
            env=observer_environment,
        )
    except subprocess.TimeoutExpired:
        launch_failure = "disposable_drill_observer_launch_terminal_deadline_exceeded"
    except OSError:
        launch_failure = "disposable_drill_observer_launch_unavailable"
    else:
        launch_failure = None
    if launch_failure is not None:
        cleanup = _cleanup_disposable_observer(
            config.container_name, run=run, environment=executor_environment
        )
        return _failure_receipt(
            config,
            container_id=None,
            first_failure=launch_failure,
            health_journal_observed=False,
            health_state="health_unavailable",
            cleanup=cleanup,
            environment_contract_spec=environment_contract_spec,
        )
    if completed.returncode != 0:
        docker_terminal_result = terminal_nonzero_capture_metadata(
            getattr(completed, "stdout", None),
            getattr(completed, "stderr", None),
            exit_code=completed.returncode,
        )
        cleanup = _cleanup_disposable_observer(
            config.container_name, run=run, environment=executor_environment
        )
        return _failure_receipt(
            config,
            container_id=None,
            first_failure="disposable_drill_observer_launch_failed",
            health_journal_observed=False,
            health_state="health_unavailable",
            cleanup=cleanup,
            environment_contract_spec=environment_contract_spec,
            docker_terminal_result=docker_terminal_result,
        )
    raw_container_id = getattr(completed, "stdout", None)
    try:
        container_id = (
            raw_container_id.strip().decode("ascii")
            if isinstance(raw_container_id, bytes)
            else ""
        )
    except UnicodeDecodeError:
        container_id = ""
    if not re.fullmatch(r"[0-9a-f]{12,64}", container_id):
        cleanup = _cleanup_disposable_observer(
            config.container_name, run=run, environment=executor_environment
        )
        return _failure_receipt(
            config,
            container_id=None,
            first_failure="disposable_drill_observer_id_invalid",
            health_journal_observed=False,
            health_state="health_unavailable",
            cleanup=cleanup,
            environment_contract_spec=environment_contract_spec,
        )

    health_reader = (
        read_health or ObserverEvidenceStore(config.evidence_host_root).read_health
    )
    deadline = monotonic() + OBSERVER_STARTUP_DEADLINE_SECONDS
    health_state = "health_unavailable"
    health_startup_phase = None
    health_journal_observed = False
    while True:
        try:
            health = dict(health_reader())
            health_journal_observed = True
            health_state = str(health.get("state") or "health_invalid")
            health_startup_phase = None
            if health_state == "starting":
                health_startup_phase = canonical_observer_startup_phase(
                    health.get("startup_phase")
                )
            if health.get("ready") is True and health_state == "ready":
                if not _health_identity_matches(health, config):
                    cleanup = _cleanup_disposable_observer(
                        config.container_name,
                        run=run,
                        environment=executor_environment,
                    )
                    return _failure_receipt(
                        config,
                        container_id=container_id,
                        first_failure="observer_health_identity_mismatch",
                        health_journal_observed=True,
                        health_state=health_state,
                        cleanup=cleanup,
                        environment_contract_spec=environment_contract_spec,
                    )
                return {
                    "launched": True,
                    "container_started": True,
                    "ready": True,
                    "container_id": container_id,
                    "health_journal_observed": True,
                    "health_state": health_state,
                    "health_startup_phase": None,
                    "health_failure_detail_code": None,
                    "spec": config.redacted_spec(),
                    "pgbouncer_admin_environment": environment_contract_spec,
                }
            if health_state.startswith("fail_closed_"):
                failure_detail_code = canonical_observer_failure_detail_code(
                    health.get("failure_detail_code") or "observer_error_unclassified"
                )
                cleanup = _cleanup_disposable_observer(
                    config.container_name,
                    run=run,
                    environment=executor_environment,
                )
                return _failure_receipt(
                    config,
                    container_id=container_id,
                    first_failure=health_state,
                    health_journal_observed=True,
                    health_state=health_state,
                    cleanup=cleanup,
                    environment_contract_spec=environment_contract_spec,
                    health_failure_detail_code=failure_detail_code,
                )
        except RuntimeError:
            health_state = "health_unavailable"
            health_startup_phase = None
        remaining = deadline - monotonic()
        if remaining <= 0:
            break
        sleep(min(OBSERVER_HEALTH_POLL_SECONDS, remaining))

    cleanup = _cleanup_disposable_observer(
        config.container_name,
        run=run,
        environment=executor_environment,
    )
    return _failure_receipt(
        config,
        container_id=container_id,
        first_failure="observer_health_startup_deadline_exceeded",
        health_journal_observed=health_journal_observed,
        health_state=health_state,
        health_startup_phase=health_startup_phase,
        cleanup=cleanup,
        environment_contract_spec=environment_contract_spec,
    )
