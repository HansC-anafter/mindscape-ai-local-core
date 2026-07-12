from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from remote_workbench_authorization_cutover.claim_gate import (
    CLAIM_GATE_TTL_SECONDS,
    RunnerClaimGate,
)
from remote_workbench_authorization_cutover.http import HttpResponse
from remote_workbench_authorization_cutover.io import CutoverError
from remote_workbench_authorization_cutover.resources import ResourceSnapshot


def _snapshot(*, processing: int = 0, inflight: int = 0) -> ResourceSnapshot:
    return ResourceSnapshot(
        totals={
            "pending": 4,
            "processing": processing,
            "delayed": 2,
            "deadletter": 1,
        },
        inventory=("mindscape:queue:pending:default|list",),
        runners={"count": 2, "capacity": 6, "inflight": inflight},
    )


class ClaimHttp:
    def __init__(self, *, durable: bool = True) -> None:
        self.durable = durable
        self.calls: list[dict] = []

    def request(self, method, url, **kwargs) -> HttpResponse:
        self.calls.append({"method": method, "url": url, **kwargs})
        if url.endswith("/pause"):
            body = {
                "state": "paused",
                "reason": "remote_workbench_origin_hardening",
                "ttl_seconds": CLAIM_GATE_TTL_SECONDS,
                "persisted": True,
                "durable": self.durable,
            }
        else:
            body = {
                "state": "open",
                "persisted": True,
                "durable": True,
            }
        return HttpResponse(200, {}, json.dumps(body).encode("utf-8"))

    def get_json(self, _url, **_kwargs) -> dict:
        return {
            "state": "paused",
            "reason": "remote_workbench_origin_hardening",
            "ttl_seconds": CLAIM_GATE_TTL_SECONDS,
            "persisted": True,
            "durable": True,
        }


class ClaimResources:
    def __init__(self, snapshots: list[ResourceSnapshot]) -> None:
        self.snapshots = list(snapshots)
        self.persisted: list[str] = []
        self.compared = False

    def capture(self) -> ResourceSnapshot:
        return self.snapshots.pop(0)

    def persist(self, _snapshot, _directory, label: str) -> None:
        self.persisted.append(label)

    def compare(self, before, after) -> None:
        assert before == after
        self.compared = True


def test_claim_gate_uses_literal_ttl_drains_and_closes_each_window(tmp_path: Path) -> None:
    snapshot = _snapshot()
    http = ClaimHttp()
    resources = ClaimResources([_snapshot(processing=1, inflight=1), snapshot, snapshot])
    clock = iter([0.0, 0.0, 1.0, 2.0, 2.0])
    gate = RunnerClaimGate(
        http=http,
        resources=resources,
        sleep=lambda _seconds: None,
        monotonic=lambda: next(clock),
    )

    before = gate.pause_and_drain(tmp_path, "06a-infra")
    gate.verify_after(before, tmp_path, "06a-infra")
    gate.resume()

    assert http.calls[0]["payload"] == {
        "reason": "remote_workbench_origin_hardening",
        "requested_by": "remote_workbench_phase06_runner",
        "ttl_seconds": 6300,
    }
    assert resources.persisted == ["06a-infra-before", "06a-infra-after"]
    assert resources.compared is True
    assert http.calls[-1]["url"].endswith("/resume")


def test_claim_gate_rejects_memory_only_pause_before_drain(tmp_path: Path) -> None:
    with pytest.raises(CutoverError, match="durable Phase06 pause"):
        RunnerClaimGate(
            http=ClaimHttp(durable=False),
            resources=ClaimResources([_snapshot()]),
        ).pause_and_drain(tmp_path, "06a-infra")


def test_claim_gate_rejects_unknown_window_before_api_mutation(tmp_path: Path) -> None:
    http = ClaimHttp()
    with pytest.raises(CutoverError, match="Phase06 contract"):
        RunnerClaimGate(
            http=http,
            resources=ClaimResources([_snapshot()]),
        ).pause_and_drain(tmp_path, "../../escape")
    assert http.calls == []
