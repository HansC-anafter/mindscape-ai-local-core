"""Host-side Remote Workbench tunnel supervisor."""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from typing import Any, Callable

from .probes import BridgeProbes, ProbeResult
from .settings import BridgeSettings
from .state_store import BridgeStateStore, utc_now


@dataclass
class SupervisorRuntime:
    """Mutable bounded counters used across monitor cycles."""

    connector_failures: int = 0
    repair_failures: int = 0


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
    ) -> None:
        self.settings = settings
        self.state_store = state_store
        self.probes = probes
        self.supervisor_build_id = supervisor_build_id
        self.supervisor_pid = supervisor_pid
        self.sleep = sleep
        self.runtime = SupervisorRuntime()

    def _launcher(self, action: str) -> bool:
        try:
            result = subprocess.run(
                [str(self.settings.launcher_path), action],
                check=False,
                capture_output=True,
                text=True,
                timeout=max(15.0, self.settings.probe_timeout_seconds * 5),
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return result.returncode == 0

    def _repair_delay(self) -> float:
        exponent = max(0, self.runtime.repair_failures - 1)
        return min(
            self.settings.backoff_initial_seconds * (2**exponent),
            self.settings.backoff_max_seconds,
        )

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
            "connector_failures": self.runtime.connector_failures,
            "supervisor_build_id": self.supervisor_build_id,
            "supervisor_pid": self.supervisor_pid,
            "authorization_conformant": False,
        }

    def _persist(self, status: dict[str, Any]) -> dict[str, Any]:
        previous = self.state_store.read_status()
        self.state_store.write_status(status)
        if previous is None or previous.get("state") != status["state"]:
            self.state_store.append_event(
                {
                    "at": status["checked_at"],
                    "state": status["state"],
                    "ready": status["ready"],
                    "repair_action": status["repair_action"],
                }
            )
        return status

    def run_once(self) -> dict[str, Any]:
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
            self.runtime.repair_failures += 1
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
            return self._persist(
                self._status(state="degraded_origin", ready=False, probes=probes)
            )

        if not tunnel.ok:
            repaired = self._launcher("ensure")
            self.runtime.repair_failures = 0 if repaired else self.runtime.repair_failures + 1
            return self._persist(
                self._status(
                    state="recovering_tunnel",
                    ready=False,
                    probes=probes,
                    repair_action="ensure" if repaired else "ensure_failed",
                )
            )

        connector = self.probes.connector()
        probes["connector"] = connector
        if not connector.ok:
            self.runtime.connector_failures += 1
            repair_action = None
            if self.runtime.connector_failures >= self.settings.connector_failure_threshold:
                repaired = self._launcher("restart")
                repair_action = "restart" if repaired else "restart_failed"
                self.runtime.repair_failures = (
                    0 if repaired else self.runtime.repair_failures + 1
                )
                if repaired:
                    self.runtime.connector_failures = 0
            return self._persist(
                self._status(
                    state="recovering_tunnel",
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

        self.runtime.repair_failures = 0
        return self._persist(self._status(state="ready", ready=True, probes=probes))

    def run_forever(self) -> None:
        """Run bounded monitor cycles until the host service stops the process."""

        while True:
            self.run_once()
            delay = self.settings.poll_interval_seconds
            if self.runtime.repair_failures:
                delay = max(delay, self._repair_delay())
            self.sleep(delay)
