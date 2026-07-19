"""Single bounded Docker subprocess owner for the formal drill CLI."""

from __future__ import annotations

import os
import re
import subprocess
from typing import Any, Callable, Mapping

from .drill import (
    DisposableDrillSignalConfig,
    launch_disposable_drill_client,
    send_disposable_drill_signal,
)
from .drill_admin_url import DisposableDrillObserverEnvironment
from .drill_docker_runtime import canonical_docker_argv, validate_canonical_docker_argv
from .drill_formal_contract import FormalDrillCliConfig
from .drill_formal_sequence import FormalDockerExecutionEnvelope
from .drill_escalation import terminal_nonzero_capture_metadata
from .drill_observer import launch_disposable_drill_observer
from .evidence import ObserverEvidenceStore


FORMAL_DOCKER_TERMINAL_DEADLINE_SECONDS = 60.0


class FormalDockerSubprocessExecutor:
    """The only shell-free subprocess owner used by the full-sequence entry."""

    def __init__(self, *, run: Callable[..., Any] = subprocess.run) -> None:
        self._run = run
        self.operation_classes: list[str] = []
        self.observer_receipt: Mapping[str, Any] | None = None
        self.client_receipt: Mapping[str, Any] | None = None
        self.signal_receipt: Mapping[str, Any] | None = None
        self.signal_config: DisposableDrillSignalConfig | None = None
        self.observer_environment: DisposableDrillObserverEnvironment | None = None
        self.client_environment: Mapping[str, str] | None = None
        self.bootstrap_environment: Mapping[str, str] | None = None

    def run(self, argv: Any, **kwargs: Any) -> Any:
        exact = validate_canonical_docker_argv(tuple(str(item) for item in argv))
        if kwargs.get("shell") is not False:
            raise RuntimeError("formal_executor_shell_must_be_false")
        timeout = kwargs.get("timeout")
        if not isinstance(timeout, (int, float)) or not 0 < float(timeout) <= 60:
            raise RuntimeError("formal_executor_terminal_deadline_invalid")
        return self._run(list(exact), **kwargs)

    def bind_signal_target(
        self,
        config: FormalDrillCliConfig,
        signal: DisposableDrillSignalConfig,
    ) -> bool:
        argv = canonical_docker_argv(
            "top",
            config.bootstrap.postgres_container_name,
            "-eo",
            "pid,args",
        )
        try:
            completed = self.run(
                argv,
                check=False,
                capture_output=True,
                text=False,
                timeout=10.0,
                shell=False,
            )
        except (OSError, RuntimeError, subprocess.TimeoutExpired, ValueError):
            return False
        if getattr(completed, "returncode", None) != 0:
            return False
        raw = getattr(completed, "stdout", None)
        if not isinstance(raw, bytes) or not raw or len(raw) > 32_768:
            return False
        try:
            lines = raw.decode("ascii").splitlines()
        except UnicodeDecodeError:
            return False
        if not lines or lines[0].split() != ["PID", "COMMAND"]:
            return False
        command_pattern = re.compile(
            rf"postgres: {re.escape(config.client.database_user)} "
            rf"{re.escape(config.client.database_name)} \S+ SELECT"
        )
        host_pids: list[int] = []
        for line in lines[1:]:
            try:
                pid_text, command = line.strip().split(maxsplit=1)
                host_pid = int(pid_text)
            except (ValueError, TypeError):
                return False
            if command_pattern.fullmatch(command):
                host_pids.append(host_pid)
        if len(host_pids) != 1:
            return False
        try:
            ObserverEvidenceStore(
                config.observer.evidence_host_root
            ).write_signal_target(
                postgres_pid=signal.target_postgres_pid,
                host_pid=host_pids[0],
            )
        except (OSError, RuntimeError, ValueError):
            return False
        return True

    @staticmethod
    def _source(completed: Any) -> dict[str, Any]:
        code = getattr(completed, "returncode", None)
        raw = getattr(completed, "stdout", b"")
        stderr = getattr(completed, "stderr", b"")
        output = ""
        if code == 0 and isinstance(raw, bytes):
            try:
                output = raw.strip().decode("ascii")
            except UnicodeDecodeError:
                output = ""
        source: dict[str, Any] = {"exit_code": code, "output": output}
        if type(code) is int and code != 0:
            source["terminal_nonzero_capture"] = terminal_nonzero_capture_metadata(
                raw,
                stderr,
                exit_code=code,
            )
        return source

    def execute(
        self,
        envelope: FormalDockerExecutionEnvelope,
        *,
        config: FormalDrillCliConfig,
    ) -> Mapping[str, Any]:
        self.operation_classes.append(envelope.operation_class)
        operation = envelope.operation_class
        try:
            if operation == "docker_run_disposable_isolated_postgresql_bootstrap":
                environment = dict(os.environ)
                environment.update(dict(self.bootstrap_environment or {}))
                completed = self.run(
                    envelope.argv,
                    check=False,
                    capture_output=True,
                    text=False,
                    timeout=FORMAL_DOCKER_TERMINAL_DEADLINE_SECONDS,
                    shell=False,
                    env=environment,
                )
                return self._source(completed)
            if operation == "docker_run_disposable_isolated_observer":
                if self.observer_environment is None:
                    raise RuntimeError("formal_observer_environment_missing")
                receipt = launch_disposable_drill_observer(
                    config.observer,
                    environment_contract=self.observer_environment,
                    run=self.run,
                )
                self.observer_receipt = receipt
                if receipt.get("ready") is True:
                    return {
                        "exit_code": 0,
                        "output": receipt.get("container_id", ""),
                        "observer_launch_receipt": receipt,
                    }
                cleanup = receipt.get("cleanup")
                resource_may_exist = bool(
                    isinstance(cleanup, Mapping)
                    and not all(value is True for value in cleanup.values())
                )
                return {
                    "exit_code": 1,
                    "output": "",
                    "failure_code": str(receipt.get("first_failure") or ""),
                    "resource_may_exist": resource_may_exist,
                    "observer_launch_receipt": receipt,
                }
            if operation == "docker_run_disposable_isolated_client":
                completed: Any | None = None

                def tracked_run(argv: Any, **kwargs: Any) -> Any:
                    nonlocal completed
                    completed = self.run(argv, **kwargs)
                    return completed

                try:
                    receipt = launch_disposable_drill_client(
                        config.client,
                        environment=self.client_environment,
                        run=tracked_run,
                    )
                except RuntimeError as exc:
                    return {
                        "exit_code": getattr(completed, "returncode", 1),
                        "output": "",
                        "failure_code": str(exc),
                        "resource_may_exist": bool(
                            completed is not None
                            and getattr(completed, "returncode", None) == 0
                        ),
                    }
                self.client_receipt = receipt
                return {"exit_code": 0, "output": receipt.get("container_id", "")}
            if operation == "docker_exec_disposable_isolated_signal_sender":
                if self.signal_config is None:
                    raise RuntimeError("formal_signal_target_pid_not_source_owned")
                if tuple(envelope.argv) != self.signal_config.docker_argv():
                    raise RuntimeError("formal_signal_envelope_argv_mismatch")
                receipt = send_disposable_drill_signal(self.signal_config, run=self.run)
                self.signal_receipt = receipt
                return {
                    "exit_code": 0 if receipt.get("signal_sent") is True else 1,
                    "output": "",
                    "failure_code": str(receipt.get("first_failure") or ""),
                    "signal_sender_receipt": receipt,
                }
            completed = self.run(
                envelope.argv,
                check=False,
                capture_output=True,
                text=False,
                timeout=FORMAL_DOCKER_TERMINAL_DEADLINE_SECONDS,
                shell=False,
            )
            return self._source(completed)
        except subprocess.TimeoutExpired:
            return {
                "exit_code": 1,
                "output": "",
                "failure_code": "formal_executor_docker_terminal_deadline_exceeded",
            }
        except OSError:
            return {
                "exit_code": 1,
                "output": "",
                "failure_code": "formal_executor_docker_runtime_unavailable",
            }
        except RuntimeError as exc:
            failure = str(exc)
            return {
                "exit_code": 1,
                "output": "",
                "failure_code": (
                    failure
                    if re.fullmatch(r"[a-z0-9_]{3,160}", failure)
                    else envelope.terminal_failure_code
                ),
            }
