from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.app.services.host_runtime_execution_permit_coordinator import (
    HostRuntimeExecutionPermitCoordinator,
)


class Facade:
    def __init__(self, *, failures: int, blockers: list[str]):
        self.failures = failures
        self.blockers = blockers
        self.issue_calls = 0
        self.resolve_calls = 0
        self.attestations: list[tuple[object, str]] = []

    def issue_execution_permit(self, **_kwargs):
        self.issue_calls += 1
        if self.issue_calls <= self.failures:
            raise ValueError(
                f"host_execution_admission_blocked:{self.blockers[0]}"
            )
        return "permit"

    def resolve_effective_admission(self, **_kwargs):
        self.resolve_calls += 1
        return SimpleNamespace(
            binding_id="binding-a",
            blockers=self.blockers,
        )

    def get_binding(self, binding_id):
        assert binding_id == "binding-a"
        return "binding"

    def record_attestation(self, command, *, actor_id):
        self.attestations.append((command, actor_id))


class DeviceClient:
    def __init__(self):
        self.calls = 0

    async def attest_binding(self, binding):
        assert binding == "binding"
        self.calls += 1
        return "attestation-command"


def _arguments():
    return {
        "workspace_id": "workspace-a",
        "capability_code": "live_interface_interpreter",
        "requirement_code": "live_interface_automation",
        "operation": "watch-screenshots",
        "operation_args": ["--workspace-id", "workspace-a"],
        "ttl_seconds": 15,
        "actor_id": "user-a",
    }


@pytest.mark.asyncio
async def test_fresh_permit_has_one_read_and_zero_device_refresh():
    facade = Facade(failures=0, blockers=[])
    client = DeviceClient()
    coordinator = HostRuntimeExecutionPermitCoordinator(
        facade=facade,
        device_node_client=client,
    )

    assert await coordinator.issue(**_arguments()) == "permit"
    assert facade.issue_calls == 1
    assert facade.resolve_calls == 0
    assert client.calls == 0


@pytest.mark.asyncio
async def test_stale_attestation_refreshes_once_then_issues():
    facade = Facade(failures=1, blockers=["attestation_stale"])
    client = DeviceClient()
    coordinator = HostRuntimeExecutionPermitCoordinator(
        facade=facade,
        device_node_client=client,
    )

    assert await coordinator.issue(**_arguments()) == "permit"
    assert facade.issue_calls == 2
    assert facade.resolve_calls == 1
    assert client.calls == 1
    assert facade.attestations == [("attestation-command", "user-a")]


@pytest.mark.asyncio
async def test_nonrefreshable_blocker_never_calls_device_node():
    facade = Facade(
        failures=1,
        blockers=["attestation_stale", "grant_expired"],
    )
    client = DeviceClient()
    coordinator = HostRuntimeExecutionPermitCoordinator(
        facade=facade,
        device_node_client=client,
    )

    with pytest.raises(ValueError, match="attestation_stale"):
        await coordinator.issue(**_arguments())
    assert facade.issue_calls == 1
    assert client.calls == 0
    assert facade.attestations == []


@pytest.mark.asyncio
async def test_refresh_path_has_no_second_refresh_or_retry_loop():
    facade = Facade(failures=2, blockers=["attestation_stale"])
    client = DeviceClient()
    coordinator = HostRuntimeExecutionPermitCoordinator(
        facade=facade,
        device_node_client=client,
    )

    with pytest.raises(ValueError, match="attestation_stale"):
        await coordinator.issue(**_arguments())
    assert facade.issue_calls == 2
    assert client.calls == 1
    assert len(facade.attestations) == 1
