"""Readiness, active-session PID, and correlation gates for the formal drill."""

from __future__ import annotations

import json
import subprocess
import time
from typing import Any, Callable, Mapping

from .drill import DisposableDrillSignalConfig
from .drill_docker_runtime import canonical_docker_argv
from .drill_formal_contract import FormalDrillCliConfig
from .drill_formal_executor import FormalDockerSubprocessExecutor
from .drill_readback import (
    DisposableDrillContainerReadbackContract,
    execute_disposable_container_readback,
)
from .evidence import ObserverEvidenceStore


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

    def _container_readback(self, role: str, argv: tuple[str, ...], image: str) -> bool:
        receipt = execute_disposable_container_readback(
            DisposableDrillContainerReadbackContract(role, argv, image),
            run=self.executor.run,
        )
        return receipt.get("validation_passed") is True

    def _terminal_command(
        self,
        argv: tuple[str, ...],
        *,
        environment: Mapping[str, str] | None = None,
    ) -> Any:
        return self.executor.run(
            argv,
            check=False,
            capture_output=True,
            text=False,
            timeout=10.0,
            shell=False,
            env=(dict(environment) if environment is not None else None),
        )

    @staticmethod
    def _terminal_zero(completed: Any) -> bool:
        return getattr(completed, "returncode", None) == 0

    def _postgres_ready(self) -> bool:
        bootstrap = self.config.bootstrap
        commands = (
            canonical_docker_argv(
                "exec",
                bootstrap.postgres_container_name,
                _PG_ISREADY,
                "-U",
                self.config.client.database_user,
                "-d",
                self.config.client.database_name,
            ),
            canonical_docker_argv(
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
            ),
        )
        try:
            return all(
                self._terminal_zero(self._terminal_command(argv)) for argv in commands
            )
        except (OSError, RuntimeError, subprocess.TimeoutExpired):
            return False

    def _pgbouncer_ready(self) -> bool:
        bootstrap = self.config.bootstrap
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
        commands = (
            canonical_docker_argv(*prefix, _PG_ISREADY, *shared),
            canonical_docker_argv(
                *prefix,
                _PSQL,
                "-X",
                *shared,
                "--tuples-only",
                "--no-align",
                "--command",
                "SHOW VERSION;",
            ),
        )
        try:
            return all(
                self._terminal_zero(
                    self._terminal_command(
                        argv,
                        environment=self.executor.client_environment,
                    )
                )
                for argv in commands
            )
        except (OSError, RuntimeError, subprocess.TimeoutExpired):
            return False

    def _source_owned_client_pid(self) -> bool:
        bootstrap = self.config.bootstrap
        query = (
            "SELECT pid FROM pg_stat_activity WHERE application_name = "
            "'postgres-signal-observer-drill-client' AND state <> 'idle' "
            "ORDER BY backend_start DESC LIMIT 1;"
        )
        argv = canonical_docker_argv(
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
            query,
        )
        try:
            completed = self._terminal_command(argv)
        except (OSError, RuntimeError, subprocess.TimeoutExpired):
            return False
        raw = getattr(completed, "stdout", None)
        if not self._terminal_zero(completed) or not isinstance(raw, bytes):
            return False
        try:
            pid = int(raw.strip().decode("ascii"))
            signal = DisposableDrillSignalConfig(
                drill_suffix=self.config.bootstrap.drill_suffix,
                postgres_image_ref=self.config.bootstrap.postgres_image_ref,
                target_postgres_pid=pid,
            )
            signal.validate()
        except (UnicodeError, ValueError):
            return False
        self.executor.signal_config = signal
        return True

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
        bootstrap = self.config.bootstrap
        image = bootstrap.postgres_image_ref
        if name == "postgres_readiness":
            passed = self._container_readback(
                "postgres", bootstrap.postgres_docker_argv(), image
            ) and self._postgres_ready()
        elif name == "pgbouncer_readiness":
            passed = self._container_readback(
                "pgbouncer", bootstrap.pgbouncer_docker_argv(), image
            ) and self._pgbouncer_ready()
        elif name == "observer_health":
            passed = bool(
                self.executor.observer_receipt
                and self.executor.observer_receipt.get("ready") is True
            )
        elif name == "client_ready":
            passed = self._container_readback(
                "client", self.config.client.docker_argv(), image
            ) and self._source_owned_client_pid()
        elif name == "sender_target_correlation":
            passed = self._correlation()
        else:
            passed = False
        return {"passed": passed, "gate": name}
