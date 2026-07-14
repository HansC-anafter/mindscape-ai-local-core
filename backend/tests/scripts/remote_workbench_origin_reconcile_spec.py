from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


TEST_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TEST_DIR))

from remote_workbench_origin_test_support import (
    REPO_ROOT,
    RecoveryExecutor,
    service_ports,
)
from remote_workbench_authorization_cutover.io import CutoverError
from remote_workbench_authorization_cutover.origin import (
    LOCKED_HOST_BINDINGS,
    OriginTopologyGate,
)
from remote_workbench_authorization_cutover.origin_recovery import (
    recover_persisted_reconcile_state,
    recover_pre_active_services,
)
from remote_workbench_authorization_cutover.resources import ResourceSnapshot


def test_origin_recovery_restores_only_pre_active_mutation_set_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = RecoveryExecutor()
    gate = OriginTopologyGate(repo_root=REPO_ROOT, executor=executor)
    pre_active = {"postgres", "pgbouncer", "backend", "frontend", "runner-apple"}
    monkeypatch.setattr(
        gate,
        "_active_services",
        lambda _project: pre_active,
    )
    inspected: list[str] = []
    monkeypatch.setattr(
        gate,
        "_inspect_service",
        lambda name, _expected: (inspected.append(name) or {}, []),
    )
    config = {
        "name": "mindscape-ai-local-core",
        "services": {name: {} for name in pre_active | {"backend-control"}},
    }
    before = ResourceSnapshot(
        totals={"pending": 0, "processing": 0, "delayed": 0, "deadletter": 0},
        inventory=(),
        runners={"count": 1, "capacity": 2, "inflight": 0},
    )

    recover_pre_active_services(
        gate,
        config=config,
        pre_active_services=pre_active,
        mutated_services=["postgres"],
        stopped_dependents=["backend", "frontend", "runner-apple"],
        before=before,
    )

    compose_calls = [
        call for call in executor.calls if call[:2] == ["docker", "compose"]
    ]
    assert compose_calls[0][-8:] == [
        "up",
        "-d",
        "--force-recreate",
        "--no-deps",
        "--wait",
        "--wait-timeout",
        "300",
        "postgres",
    ]
    assert compose_calls[1][-2:] == ["start", "backend"]
    assert compose_calls[2][-2:] == ["start", "frontend"]
    assert compose_calls[3][-2:] == ["start", "runner-apple"]
    assert set(inspected) == {"postgres", "backend", "frontend", "runner-apple"}


def test_origin_reconcile_blocks_runner_and_non_port_drift_before_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = RecoveryExecutor()
    gate = OriginTopologyGate(repo_root=REPO_ROOT, executor=executor)
    config = {
        "name": "mindscape-ai-local-core",
        "services": {
            "runner-apple": {},
            "frontend": service_ports(LOCKED_HOST_BINDINGS["frontend"]),
        },
    }
    monkeypatch.setattr(gate, "_compose_config", lambda **_kwargs: config)
    monkeypatch.setattr(
        gate,
        "_active_services",
        lambda _project: {"runner-apple", "frontend"},
    )

    with pytest.raises(CutoverError, match="Runner drift blocks"):
        gate.reconcile(
            {"runner-apple": ["command"]},
            secure_dir=tmp_path,
            workspace_id="workspace-a",
        )
    with pytest.raises(CutoverError, match="published-port drift"):
        gate.reconcile(
            {"frontend": ["bind_mounts"]},
            secure_dir=tmp_path,
            workspace_id="workspace-a",
        )
    assert executor.calls == []


def test_origin_reconcile_uses_single_service_wait_and_exact_runner_start(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = RecoveryExecutor()
    gate = OriginTopologyGate(repo_root=REPO_ROOT, executor=executor)
    active = {
        "postgres",
        "backend",
        "backend-control",
        "frontend",
        "runner-apple",
    }
    config = {
        "name": "mindscape-ai-local-core",
        "services": {
            "postgres": service_ports(LOCKED_HOST_BINDINGS["postgres"]),
            "backend": service_ports(LOCKED_HOST_BINDINGS["backend"]),
            "backend-control": service_ports(
                LOCKED_HOST_BINDINGS["backend-control"]
            ),
            "frontend": service_ports(LOCKED_HOST_BINDINGS["frontend"]),
            "runner-apple": {},
        },
    }
    monkeypatch.setattr(gate, "_compose_config", lambda **_kwargs: config)
    monkeypatch.setattr(gate, "_active_services", lambda _project: active)
    monkeypatch.setattr(gate, "_inspect_service", lambda _name, _expected: ({}, []))
    monkeypatch.setattr(
        gate,
        "inspect",
        lambda _directory, _workspace: {"drift": {}, "lan_reachable_ports": []},
    )

    gate.reconcile(
        {
            "postgres": ["port_bindings", "lan_reachable"],
            "backend": ["port_bindings"],
        },
        secure_dir=tmp_path,
        workspace_id="workspace-a",
    )

    compose_calls = [
        call for call in executor.calls if call[:2] == ["docker", "compose"]
    ]
    up_calls = [call for call in compose_calls if "up" in call]
    assert [call[-1] for call in up_calls] == ["postgres", "backend"]
    for call in up_calls:
        assert call[-8:-1] == [
            "up",
            "-d",
            "--force-recreate",
            "--no-deps",
            "--wait",
            "--wait-timeout",
            "300",
        ]
    start_calls = [call for call in compose_calls if "start" in call]
    assert [call[-2:] for call in start_calls] == [
        ["start", "backend-control"],
        ["start", "frontend"],
        ["start", "runner-apple"],
    ]
    runner_calls = [
        call for call in compose_calls if call[-2:] == ["start", "runner-apple"]
    ]
    assert runner_calls == [start_calls[-1]]


def test_origin_recovery_rejects_runner_recreate_and_non_pre_active_mutation() -> None:
    executor = RecoveryExecutor()
    gate = OriginTopologyGate(repo_root=REPO_ROOT, executor=executor)
    before = ResourceSnapshot(
        totals={"pending": 0, "processing": 0, "delayed": 0, "deadletter": 0},
        inventory=(),
        runners={"count": 1, "capacity": 2, "inflight": 0},
    )
    config = {"services": {"runner-apple": {}, "frontend": {}}}

    with pytest.raises(CutoverError, match="cannot recreate a runner"):
        recover_pre_active_services(
            gate,
            config=config,
            pre_active_services={"runner-apple"},
            mutated_services=["runner-apple"],
            stopped_dependents=[],
            before=before,
        )
    with pytest.raises(CutoverError, match="non-pre-active"):
        recover_pre_active_services(
            gate,
            config=config,
            pre_active_services={"frontend"},
            mutated_services=["runner-apple"],
            stopped_dependents=[],
            before=before,
        )
    assert executor.calls == []


def test_completed_origin_reconcile_receipt_is_exact_noop(
    tmp_path: Path,
) -> None:
    state = tmp_path / "origin-reconcile-state.json"
    state.write_text(
        json.dumps(
            {
                "reconcile_completed": True,
                "pre_active_services": ["frontend"],
                "mutated_services": ["frontend"],
                "stopped_dependents": [],
                "resource_before": {
                    "totals": {
                        "pending": 0,
                        "processing": 0,
                        "delayed": 0,
                        "deadletter": 0,
                    },
                    "inventory": [],
                    "runners": {"count": 0, "capacity": 0, "inflight": 0},
                },
            }
        ),
        encoding="utf-8",
    )
    state.chmod(0o600)
    executor = RecoveryExecutor()
    gate = OriginTopologyGate(repo_root=REPO_ROOT, executor=executor)

    assert recover_persisted_reconcile_state(gate, tmp_path) is False
    assert executor.calls == []
    readback = json.loads(
        (tmp_path / "origin-recovery-readback.json").read_text(encoding="utf-8")
    )
    assert readback["reconcile_completed"] is True


def test_internal_listener_probe_distinguishes_host_gate_from_missing_token() -> None:
    class ListenerExecutor:
        def __init__(self, rows):
            self.rows = rows

        def run(self, _args, **_kwargs):
            return json.dumps(self.rows)

    rows = [
        {
            "host": "spoof.invalid",
            "status": 403,
            "stage": "identity_rejected",
            "reason": "invalid_public_host",
        },
        {
            "host": "localhost",
            "status": 403,
            "stage": "identity_rejected",
            "reason": "invalid_public_host",
        },
        {
            "host": "remote-workbench.mindscapeai.app",
            "status": 403,
            "stage": "identity_rejected",
            "reason": "missing_access_token",
        },
    ]
    gate = OriginTopologyGate(repo_root=REPO_ROOT, executor=ListenerExecutor(rows))
    assert gate._internal_listener_probe("workspace-a")["state"] == "default_deny"

    rows[0]["reason"] = "missing_access_token"
    with pytest.raises(CutoverError, match="did not default deny"):
        gate._internal_listener_probe("workspace-a")
