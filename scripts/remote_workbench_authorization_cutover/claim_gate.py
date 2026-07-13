"""Durable runner-claim pause, drain, snapshot, and resume facade."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from .http import HttpClient
from .io import CutoverError
from .resources import (
    RESOURCE_WINDOWS,
    RedisResourceSampler,
    ResourceSnapshot,
    resource_snapshot_label,
)


CLAIM_GATE_TTL_SECONDS = 6_300
RUNNER_DRAIN_BUDGET_SECONDS = 120.0
CLAIM_GATE_BASE = "http://localhost:8200/api/v1/host-resources/runner-claim-gate"


class RunnerClaimGate:
    """Use the existing durable claim-gate API as the only pause seam."""

    def __init__(
        self,
        *,
        http: HttpClient,
        resources: RedisResourceSampler,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.http = http
        self.resources = resources
        self.sleep = sleep
        self.monotonic = monotonic

    def _post(self, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self.http.request(
            "POST",
            f"{CLAIM_GATE_BASE}{path}",
            payload=payload,
            timeout_seconds=10.0,
            max_response_bytes=32_768,
        )
        if not 200 <= response.status < 300:
            raise CutoverError(f"Runner claim gate returned status {response.status}")
        return response.json()

    @staticmethod
    def _require_pause(payload: dict[str, Any]) -> None:
        if (
            payload.get("state") != "paused"
            or payload.get("reason") != "remote_workbench_origin_hardening"
            or payload.get("ttl_seconds") != CLAIM_GATE_TTL_SECONDS
            or payload.get("persisted") is not True
            or payload.get("durable") is not True
        ):
            raise CutoverError("Runner claim gate did not persist a durable Phase06 pause")

    def pause_and_drain(self, secure_dir: Path, window: str) -> ResourceSnapshot:
        """Pause new claims and wait only for processing/inflight work to drain."""

        if window not in RESOURCE_WINDOWS:
            raise CutoverError("Runner claim window is not in the Phase06 contract")
        paused = self._post(
            "/pause",
            {
                "reason": "remote_workbench_origin_hardening",
                "requested_by": "remote_workbench_phase06_runner",
                "ttl_seconds": CLAIM_GATE_TTL_SECONDS,
            },
        )
        self._require_pause(paused)
        deadline = self.monotonic() + RUNNER_DRAIN_BUDGET_SECONDS
        while self.monotonic() < deadline:
            snapshot = self.resources.capture()
            if (
                snapshot.totals.get("processing") == 0
                and snapshot.runners.get("inflight") == 0
            ):
                self.resources.persist(
                    snapshot,
                    secure_dir,
                    resource_snapshot_label(window, "before"),
                )
                return snapshot
            self.sleep(min(2.0, max(0.0, deadline - self.monotonic())))
        raise CutoverError("Runner workloads did not drain before origin maintenance")

    def verify_after(
        self,
        before: ResourceSnapshot,
        secure_dir: Path,
        window: str,
    ) -> None:
        """Require byte-equivalent queues and stable runner capacity while paused."""

        paused = self.http.get_json(
            CLAIM_GATE_BASE,
            timeout_seconds=10.0,
            max_response_bytes=32_768,
        )
        self._require_pause(paused)
        after = self.resources.capture()
        self.resources.persist(
            after,
            secure_dir,
            resource_snapshot_label(window, "after"),
        )
        self.resources.compare(before, after)

    def load_before(self, secure_dir: Path, window: str) -> ResourceSnapshot:
        """Load the durable baseline owned by an interrupted paused window."""

        return self.resources.load(
            secure_dir,
            resource_snapshot_label(window, "before"),
        )

    def resume(self) -> None:
        """Resume local claims only after closure or completed backout."""

        payload = self._post("/resume")
        if (
            payload.get("state") != "open"
            or payload.get("persisted") is not True
            or payload.get("durable") is not True
            or payload.get("resume_blocked_reason") is not None
        ):
            raise CutoverError("Runner claim gate did not reopen durably")
