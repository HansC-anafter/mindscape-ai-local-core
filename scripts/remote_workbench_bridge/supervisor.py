"""Host-side Remote Workbench tunnel supervisor."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from dataclasses import dataclass
from typing import Any, Callable

from .probes import BridgeProbes, ProbeResult
from .settings import BridgeSettings
from .state_store import BridgeStateStore, utc_now


LAUNCHER_DEADLINE_SECONDS = 60.0
LAUNCHER_TERMINATE_GRACE_SECONDS = 5.0
LAUNCHER_KILL_GRACE_SECONDS = 5.0


def _process_group_exists(process_group: int) -> bool:
    try:
        os.killpg(process_group, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _wait_for_process_group_exit(process_group: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while _process_group_exists(process_group):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(0.05, remaining))
    return True


@dataclass
class SupervisorRuntime:
    """Mutable bounded counters used across monitor cycles."""

    connector_failures: int = 0
    repair_failures: int = 0
    next_repair_at: float = 0.0
    origin_failures: int = 0
    origin_repair_attempts: int = 0
    next_origin_repair_at: float = 0.0


class BridgeSupervisor:
    """Monitor the bridge and delegate repairs to the canonical launcher."""

    def __init__(
        self,
        *,
        settings: BridgeSettings,
        state_store: BridgeStateStore,
        probes: BridgeProbes,
        supervisor_build_id: str,
        supervisor_pid: int,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.settings = settings
        self.state_store = state_store
        self.probes = probes
        self.supervisor_build_id = supervisor_build_id
        self.supervisor_pid = supervisor_pid
        self.sleep = sleep
        self.monotonic = monotonic
        self.runtime = SupervisorRuntime()
        self.stop_requested = False

    def _launcher(self, action: str) -> bool:
        try:
            process = subprocess.Popen(
                [str(self.settings.launcher_path), action],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError:
            return False
        try:
            return process.wait(timeout=LAUNCHER_DEADLINE_SECONDS) == 0
        except subprocess.TimeoutExpired:
            pass
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except OSError:
            return False
        try:
            process.wait(timeout=LAUNCHER_TERMINATE_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            pass
        if _process_group_exists(process.pid):
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except OSError:
                return False
            try:
                process.wait(timeout=LAUNCHER_KILL_GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                return False
        if not _wait_for_process_group_exit(
            process.pid, LAUNCHER_KILL_GRACE_SECONDS
        ):
            return False
        return False

    def _repair_delay(self) -> float:
        exponent = min(16, max(0, self.runtime.repair_failures - 1))
        return min(
            self.settings.backoff_initial_seconds * (2**exponent),
            self.settings.backoff_max_seconds,
        )

    def _repair_allowed(self) -> bool:
        return self.monotonic() >= self.runtime.next_repair_at

    def _schedule_repair_gate(self) -> None:
        self.runtime.next_repair_at = self.monotonic() + self._repair_delay()

    def _clear_repair_gate(self) -> None:
        self.runtime.repair_failures = 0
        self.runtime.next_repair_at = 0.0

    def _origin_repair_delay(self) -> float:
        exponent = min(16, max(0, self.runtime.origin_repair_attempts - 1))
        return min(
            self.settings.backoff_initial_seconds * (2**exponent),
            self.settings.backoff_max_seconds,
        )

    def _origin_repair_allowed(self) -> bool:
        return self.monotonic() >= self.runtime.next_origin_repair_at

    def _schedule_origin_repair_gate(self) -> None:
        self.runtime.next_origin_repair_at = (
            self.monotonic() + self._origin_repair_delay()
        )

    def _clear_origin_repair_gate(self) -> None:
        self.runtime.origin_failures = 0
        self.runtime.origin_repair_attempts = 0
        self.runtime.next_origin_repair_at = 0.0

    def _status(
        self,
        *,
        state: str,
        ready: bool,
        probes: dict[str, ProbeResult],
        repair_action: str | None = None,
    ) -> dict[str, Any]:
        return {
            "checked_at": utc_now(),
            "state": state,
            "ready": ready,
            "maintenance": self.state_store.maintenance(),
            "probes": {name: probe.as_dict() for name, probe in probes.items()},
            "repair_action": repair_action,
            "repair_failures": self.runtime.repair_failures,
            "origin_failures": self.runtime.origin_failures,
            "origin_repair_attempts": self.runtime.origin_repair_attempts,
            "connector_failures": self.runtime.connector_failures,
            "supervisor_build_id": self.supervisor_build_id,
            "supervisor_pid": self.supervisor_pid,
            "poll_interval_seconds": self.settings.poll_interval_seconds,
            "authorization_conformant": False,
        }

    def _persist(self, status: dict[str, Any]) -> dict[str, Any]:
        previous = self.state_store.read_status()
        self.state_store.write_status(status)
        previous_state = previous.get("state") if isinstance(previous, dict) else None
        if previous_state != status["state"] or status["repair_action"] is not None:
            self.state_store.append_event(
                {
                    "at": status["checked_at"],
                    "previous_state": previous_state,
                    "state": status["state"],
                    "ready": status["ready"],
                    "repair_action": status["repair_action"],
                }
            )
        return status

    def run_once(self, *, repair: bool = True) -> dict[str, Any]:
        """Run one bounded monitor cycle without touching unrelated services."""

        maintenance = self.state_store.maintenance()
        docker = self.probes.docker()
        if maintenance.get("enabled") is True:
            probes = {"docker": docker}
            if docker.ok:
                probes["local_origin"] = self.probes.local_origin()
                probes["tunnel"] = self.probes.tunnel()
            return self._persist(
                self._status(state="maintenance", ready=False, probes=probes)
            )

        if not docker.ok:
            self.runtime.repair_failures = min(16, self.runtime.repair_failures + 1)
            return self._persist(
                self._status(state="waiting_docker", ready=False, probes={"docker": docker})
            )

        local_origin = self.probes.local_origin()
        tunnel = self.probes.tunnel()
        probes = {
            "docker": docker,
            "local_origin": local_origin,
            "tunnel": tunnel,
        }
        if not local_origin.ok:
            self.runtime.connector_failures = 0
            control_plane = self.probes.control_plane()
            probes["control_plane"] = control_plane
            repair_action = None
            state = "degraded_origin"
            if control_plane.ok:
                self.runtime.origin_failures = min(
                    self.settings.origin_failure_threshold,
                    self.runtime.origin_failures + 1,
                )
                if (
                    self.runtime.origin_failures
                    >= self.settings.origin_failure_threshold
                    and repair
                    and self._origin_repair_allowed()
                ):
                    recovered = self._launcher("recover-origin")
                    repair_action = (
                        "recover-origin" if recovered else "recover-origin-failed"
                    )
                    self.runtime.origin_repair_attempts = min(
                        16, self.runtime.origin_repair_attempts + 1
                    )
                    self._schedule_origin_repair_gate()
                    state = "recovering_origin"
            else:
                self.runtime.origin_failures = 0
            return self._persist(
                self._status(
                    state=state,
                    ready=False,
                    probes=probes,
                    repair_action=repair_action,
                )
            )

        self._clear_origin_repair_gate()
        if not tunnel.ok:
            repair_action = None
            if repair and self._repair_allowed():
                repaired = self._launcher("ensure")
                repair_action = "ensure" if repaired else "ensure_failed"
                self.runtime.repair_failures = (
                    0 if repaired else min(16, self.runtime.repair_failures + 1)
                )
                self._schedule_repair_gate()
            return self._persist(
                self._status(
                    state="recovering_tunnel",
                    ready=False,
                    probes=probes,
                    repair_action=repair_action,
                )
            )

        connector = self.probes.connector()
        probes["connector"] = connector
        if not connector.ok:
            self.runtime.connector_failures = min(
                self.settings.connector_failure_threshold,
                self.runtime.connector_failures + 1,
            )
            repair_action = None
            state = "degraded_tunnel"
            if (
                self.runtime.connector_failures
                >= self.settings.connector_failure_threshold
                and repair
                and self._repair_allowed()
            ):
                repaired = self._launcher("restart")
                repair_action = "restart" if repaired else "restart_failed"
                self.runtime.repair_failures = (
                    0 if repaired else min(16, self.runtime.repair_failures + 1)
                )
                if repaired:
                    self.runtime.connector_failures = 0
                self._schedule_repair_gate()
                state = "recovering_tunnel"
            return self._persist(
                self._status(
                    state=state,
                    ready=False,
                    probes=probes,
                    repair_action=repair_action,
                )
            )

        self.runtime.connector_failures = 0
        public_origin = self.probes.public_origin()
        probes["public_origin"] = public_origin
        if not public_origin.ok:
            return self._persist(
                self._status(state="degraded_remote", ready=False, probes=probes)
            )

        self._clear_repair_gate()
        return self._persist(self._status(state="ready", ready=True, probes=probes))

    def request_stop(self, *_args: object) -> None:
        """Request a graceful stop after the current bounded operation."""

        self.stop_requested = True

    def run_forever(self, *, repair: bool = True) -> None:
        """Run bounded monitor cycles until the host service stops the process."""

        while not self.stop_requested:
            self.run_once(repair=repair)
            delay = self.settings.poll_interval_seconds
            if self.runtime.repair_failures:
                delay = max(delay, self._repair_delay())
            if self.runtime.origin_repair_attempts:
                delay = max(delay, self._origin_repair_delay())
            remaining = delay
            while not self.stop_requested and remaining > 0:
                interval = min(1.0, remaining)
                self.sleep(interval)
                remaining -= interval
