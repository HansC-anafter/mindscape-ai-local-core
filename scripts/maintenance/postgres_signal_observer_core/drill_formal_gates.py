"""Readiness, active-session PID, and correlation gates for the formal drill."""

from __future__ import annotations

import json
import subprocess
import time
from typing import TYPE_CHECKING, Any, Callable, Mapping

from .drill_client_readiness import evaluate_client_readiness
from .drill_docker_runtime import canonical_docker_argv
from .drill_formal_contract import FormalDrillCliConfig
from .drill_gate_receipt import (
    project_client_container_readback_outcome,
    project_pgbouncer_container_readback_outcome,
    project_postgres_container_readback_outcome,
)
from .drill_pgbouncer_readiness import (
    FORMAL_PGBOUNCER_STARTUP_DEADLINE_SECONDS,
    FORMAL_PGBOUNCER_STARTUP_POLL_SECONDS,
    evaluate_pgbouncer_startup,
)
from .drill_escalation import (
    FORMAL_POSTGRES_STARTUP_DEADLINE_SECONDS,
    FORMAL_POSTGRES_STARTUP_POLL_SECONDS,
    terminal_capture_metadata,
)
from .drill_readback import (
    CONTAINER_READBACK_TERMINAL_DEADLINE_SECONDS,
    DisposableDrillContainerReadbackContract,
    execute_disposable_container_readback,
)
from .drill_readback_projection import (
    CONTAINER_READBACK_MAX_BYTES,
    CONTAINER_READBACK_SCHEMA_VERSION,
)
from .drill_readiness_stage import empty_psql_stage, empty_stage, replace_psql_result
from .evidence import ObserverEvidenceStore

if TYPE_CHECKING:
    from .drill_formal_executor import FormalDockerSubprocessExecutor
FORMAL_CORRELATION_DEADLINE_SECONDS = 10.0
FORMAL_CORRELATION_POLL_SECONDS = 0.25
_PSQL = "/usr/lib/postgresql/16/bin/psql"
_PG_ISREADY = "/usr/lib/postgresql/16/bin/pg_isready"


class FormalDrillGateOwner:
    """Interleave the existing readback/health/correlation owners."""

    def __init__(
        self,
        config: FormalDrillCliConfig,
        executor: FormalDockerSubprocessExecutor,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config = config
        self.executor = executor
        self.monotonic = monotonic
        self.sleep = sleep

    def _container_readback(
        self, role: str, argv: tuple[str, ...], image: str
    ) -> Mapping[str, Any]:
        return execute_disposable_container_readback(
            DisposableDrillContainerReadbackContract(role, argv, image),
            run=self.executor.run,
        )

    def _terminal_command(
        self,
        argv: tuple[str, ...],
        *,
        environment: Mapping[str, str] | None = None,
        timeout: float = 10.0,
    ) -> Any:
        return self.executor.run(
            argv,
            check=False,
            capture_output=True,
            text=False,
            timeout=timeout,
            shell=False,
            env=(dict(environment) if environment is not None else None),
        )

    @staticmethod
    def _terminal_zero(completed: Any) -> bool:
        return getattr(completed, "returncode", None) == 0

    @staticmethod
    def _stage_result(
        completed: Any, *, role: str = "postgres"
    ) -> dict[str, Any]:
        prefix = f"formal_{role}_readiness"
        code = getattr(completed, "returncode", None)
        if type(code) is not int:
            return {
                "status": "result_invalid",
                "error_code": f"{prefix}_result_invalid",
            }
        try:
            capture = terminal_capture_metadata(
                getattr(completed, "stdout", b""),
                getattr(completed, "stderr", b""),
                exit_code=code,
            )
        except ValueError:
            return {
                "status": "result_invalid",
                "error_code": f"{prefix}_capture_invalid",
            }
        return {
            "status": "terminal_zero" if code == 0 else "terminal_nonzero",
            "exit_code": code,
            "terminal_capture": capture,
        }

    @staticmethod
    def _stage_error(status: str, error_code: str) -> dict[str, str]:
        return {"status": status, "error_code": error_code}

    def _postgres_readiness(self) -> Mapping[str, Any]:
        bootstrap = self.config.bootstrap
        stages = {
            "container_readback": empty_stage(),
            "pg_isready": empty_stage(),
            "psql_select_one": empty_psql_stage(empty_stage()),
        }
        try:
            container_receipt = self._container_readback(
                "postgres",
                bootstrap.postgres_docker_argv(),
                bootstrap.postgres_image_ref,
            )
        except (OSError, RuntimeError):
            container_receipt = {
                "validation_passed": False, "role": "postgres",
                "first_failure": "formal_postgres_readback_unavailable",
                "failures": ["formal_postgres_readback_unavailable"],
                "projection_schema_version": CONTAINER_READBACK_SCHEMA_VERSION,
                "projection_max_bytes": CONTAINER_READBACK_MAX_BYTES,
                "terminal_deadline_seconds": CONTAINER_READBACK_TERMINAL_DEADLINE_SECONDS,
            }
        container_outcome = project_postgres_container_readback_outcome(
            container_receipt
        )
        container_passed = bool(
            container_outcome is not None and container_outcome["passed"] is True
        )
        stages["container_readback"] = {
            "attempted": True,
            "attempt_count": 1,
            "success_count": int(container_passed),
            "passed": container_passed,
            "last_result": (
                container_outcome["last_result"]
                if container_outcome is not None
                else {
                    "status": "validation_failed",
                    "detail_code": "formal_postgres_container_readback_failed",
                }
            ),
        }
        if not container_passed:
            return {
                "passed": False,
                "gate": "postgres_readiness",
                "detail_code": "formal_postgres_container_readback_failed",
                "startup_deadline_seconds": FORMAL_POSTGRES_STARTUP_DEADLINE_SECONDS,
                "poll_seconds": FORMAL_POSTGRES_STARTUP_POLL_SECONDS,
                "stages": stages,
            }

        pg_isready = canonical_docker_argv(
            "exec",
            bootstrap.postgres_container_name,
            _PG_ISREADY,
            "-U",
            self.config.client.database_user,
            "-d",
            self.config.client.database_name,
        )
        select_one = canonical_docker_argv(
            "exec",
            bootstrap.postgres_container_name,
            _PSQL,
            "-X",
            "-U",
            self.config.client.database_user,
            "-d",
            self.config.client.database_name,
            "--tuples-only",
            "--no-align",
            "--command",
            "SELECT 1;",
        )
        deadline = self.monotonic() + FORMAL_POSTGRES_STARTUP_DEADLINE_SECONDS
        detail_code = "formal_postgres_pg_isready_deadline_exceeded"

        while True:
            remaining = deadline - self.monotonic()
            if remaining <= 0:
                break
            final_attempt = remaining <= FORMAL_POSTGRES_STARTUP_POLL_SECONDS
            pg_stage = stages["pg_isready"]
            pg_stage["attempted"] = True
            pg_stage["attempt_count"] += 1
            try:
                completed = self._terminal_command(pg_isready, timeout=remaining)
            except subprocess.TimeoutExpired:
                pg_stage["last_result"] = self._stage_error(
                    "timeout", "formal_postgres_pg_isready_deadline_exceeded"
                )
                detail_code = "formal_postgres_pg_isready_deadline_exceeded"
                break
            except (OSError, RuntimeError):
                pg_stage["last_result"] = self._stage_error(
                    "exec_error", "formal_postgres_pg_isready_unavailable"
                )
                detail_code = "formal_postgres_pg_isready_unavailable"
                break
            pg_result = self._stage_result(completed)
            pg_stage["last_result"] = pg_result
            pg_attempt_passed = pg_result.get("status") == "terminal_zero"
            if pg_attempt_passed:
                pg_stage["success_count"] += 1
                pg_stage["passed"] = True

            if pg_attempt_passed:
                remaining = deadline - self.monotonic()
                if remaining <= 0:
                    detail_code = (
                        "formal_postgres_psql_select_one_not_attempted_"
                        "deadline_exceeded"
                    )
                    break
                psql_stage = stages["psql_select_one"]
                psql_stage["attempted"] = True
                psql_stage["attempt_count"] += 1
                try:
                    completed = self._terminal_command(select_one, timeout=remaining)
                except subprocess.TimeoutExpired:
                    replace_psql_result(
                        psql_stage,
                        self._stage_error(
                            "timeout",
                            "formal_postgres_psql_select_one_deadline_exceeded",
                        ),
                    )
                    detail_code = "formal_postgres_psql_select_one_deadline_exceeded"
                    break
                except (OSError, RuntimeError):
                    replace_psql_result(
                        psql_stage,
                        self._stage_error(
                            "exec_error", "formal_postgres_psql_select_one_unavailable"
                        ),
                    )
                    detail_code = "formal_postgres_psql_select_one_unavailable"
                    break
                psql_result = self._stage_result(completed)
                replace_psql_result(psql_stage, psql_result)
                psql_attempt_passed = psql_result.get("status") == "terminal_zero"
                if psql_attempt_passed:
                    psql_stage["success_count"] += 1
                    psql_stage["passed"] = True
                    return {
                        "passed": True,
                        "gate": "postgres_readiness",
                        "detail_code": None,
                        "startup_deadline_seconds": FORMAL_POSTGRES_STARTUP_DEADLINE_SECONDS,
                        "poll_seconds": FORMAL_POSTGRES_STARTUP_POLL_SECONDS,
                        "stages": stages,
                    }
                detail_code = "formal_postgres_psql_select_one_deadline_exceeded"
            else:
                detail_code = "formal_postgres_pg_isready_deadline_exceeded"

            if final_attempt:
                break
            remaining = deadline - self.monotonic()
            if remaining <= 0:
                break
            if remaining <= FORMAL_POSTGRES_STARTUP_POLL_SECONDS:
                continue
            self.sleep(FORMAL_POSTGRES_STARTUP_POLL_SECONDS)

        return {
            "passed": False,
            "gate": "postgres_readiness",
            "detail_code": detail_code,
            "startup_deadline_seconds": FORMAL_POSTGRES_STARTUP_DEADLINE_SECONDS,
            "poll_seconds": FORMAL_POSTGRES_STARTUP_POLL_SECONDS,
            "stages": stages,
        }

    def _pgbouncer_readiness(self) -> Mapping[str, Any]:
        bootstrap = self.config.bootstrap
        stages = {
            "container_readback": empty_stage(),
            "pg_isready": empty_stage(),
            "show_version": empty_stage(),
        }
        try:
            container_receipt = self._container_readback(
                "pgbouncer", bootstrap.pgbouncer_docker_argv(), bootstrap.postgres_image_ref
            )
        except (OSError, RuntimeError):
            container_receipt = {
                "validation_passed": False, "role": "pgbouncer",
                "first_failure": "formal_pgbouncer_readback_unavailable",
                "failures": ["formal_pgbouncer_readback_unavailable"],
                "projection_schema_version": CONTAINER_READBACK_SCHEMA_VERSION,
                "projection_max_bytes": CONTAINER_READBACK_MAX_BYTES,
                "terminal_deadline_seconds": CONTAINER_READBACK_TERMINAL_DEADLINE_SECONDS,
            }
        outcome = project_pgbouncer_container_readback_outcome(container_receipt)
        container_passed = bool(outcome and outcome["passed"] is True)
        stages["container_readback"] = {
            "attempted": True,
            "attempt_count": 1,
            "success_count": int(container_passed),
            "passed": container_passed,
            "last_result": (
                outcome["last_result"]
                if outcome is not None
                else {
                    "status": "validation_failed",
                    "detail_code": "formal_pgbouncer_container_readback_failed",
                }
            ),
        }

        if not container_passed:
            return {
                "passed": False,
                "gate": "pgbouncer_readiness",
                "detail_code": "formal_pgbouncer_container_readback_failed",
                "startup_deadline_seconds": (
                    FORMAL_PGBOUNCER_STARTUP_DEADLINE_SECONDS
                ),
                "poll_seconds": FORMAL_PGBOUNCER_STARTUP_POLL_SECONDS,
                "stages": stages,
            }
        prefix = (
            "exec",
            "--env",
            "PGPASSWORD",
            bootstrap.postgres_container_name,
        )
        shared = (
            "-h",
            bootstrap.pgbouncer_container_name,
            "-p",
            str(self.config.client.pgbouncer_port),
            "-U",
            self.config.client.database_user,
            "-d",
            "pgbouncer",
        )
        return evaluate_pgbouncer_startup(
            stages=stages,
            pg_isready_argv=canonical_docker_argv(*prefix, _PG_ISREADY, *shared),
            show_version_argv=canonical_docker_argv(
                *prefix,
                _PSQL,
                "-X",
                *shared,
                "--tuples-only",
                "--no-align",
                "--command",
                "SHOW VERSION;",
            ),
            run=self._terminal_command,
            environment=self.executor.client_environment,
            stage_result=lambda completed: self._stage_result(
                completed, role="pgbouncer"
            ),
            monotonic=self.monotonic,
            sleep=self.sleep,
        )

    def _client_readiness(self) -> Mapping[str, Any]:
        bootstrap = self.config.bootstrap
        try:
            container_receipt = self._container_readback(
                "client",
                self.config.client.docker_argv(),
                bootstrap.postgres_image_ref,
            )
        except (OSError, RuntimeError):
            container_receipt = {
                "validation_passed": False,
                "role": "client",
                "first_failure": "formal_client_readback_unavailable",
                "failures": ["formal_client_readback_unavailable"],
                "projection_schema_version": CONTAINER_READBACK_SCHEMA_VERSION,
                "projection_max_bytes": CONTAINER_READBACK_MAX_BYTES,
                "terminal_deadline_seconds": (
                    CONTAINER_READBACK_TERMINAL_DEADLINE_SECONDS
                ),
            }
        receipt, signal = evaluate_client_readiness(
            container_outcome=project_client_container_readback_outcome(
                container_receipt
            ),
            bootstrap=bootstrap,
            client=self.config.client,
            run=self._terminal_command,
            stage_result=lambda completed: self._stage_result(
                completed, role="client"
            ),
        )
        self.executor.signal_config = signal
        return receipt

    def _correlation(self) -> bool:
        signal = self.executor.signal_config
        if signal is None:
            return False
        deadline = self.monotonic() + FORMAL_CORRELATION_DEADLINE_SECONDS
        store = ObserverEvidenceStore(self.config.observer.evidence_host_root)
        while True:
            for path in sorted(store.events_root.glob("event-*.json")):
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError, TypeError):
                    continue
                if (
                    payload.get("target_postgres_pid") == signal.target_postgres_pid
                    and isinstance(payload.get("pgbouncer"), Mapping)
                    and payload["pgbouncer"].get("status") == "correlated"
                ):
                    return True
            remaining = deadline - self.monotonic()
            if remaining <= 0:
                return False
            self.sleep(min(FORMAL_CORRELATION_POLL_SECONDS, remaining))

    def evaluate(self, name: str) -> Mapping[str, Any]:
        if name == "postgres_readiness":
            return self._postgres_readiness()
        elif name == "pgbouncer_readiness":
            return self._pgbouncer_readiness()
        elif name == "observer_health":
            passed = bool(
                self.executor.observer_receipt
                and self.executor.observer_receipt.get("ready") is True
            )
        elif name == "client_ready":
            return self._client_readiness()
        elif name == "sender_target_correlation":
            passed = self._correlation()
        else:
            passed = False
        return {"passed": passed, "gate": name}
