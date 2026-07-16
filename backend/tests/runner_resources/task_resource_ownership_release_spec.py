from types import SimpleNamespace

import pytest

from backend.app.services.runner_resources import NodeBudgetReservation
from backend.app.services.runner_resources.ownership_release import (
    release_task_resource_ownership,
    release_task_resource_ownership_from_context,
)


def _reservation(owner_id: str, *, revision: int = 7) -> NodeBudgetReservation:
    return NodeBudgetReservation(
        owner_id=owner_id,
        bytes=123,
        revision=revision,
        expires_at_epoch=1000.0,
        policy_fingerprint="policy",
        resource_profile_fingerprint="profile",
        allocatable_bytes=999,
        policy_mode="calibrated",
    )


class _LeaseStore:
    def __init__(self, owners=None, *, error=False):
        self.owners = dict(owners or {})
        self.error = error

    async def release(self, lease_key, owner_id):
        if self.error:
            raise RuntimeError("lease unavailable")
        if self.owners.get(lease_key) != owner_id:
            return False
        self.owners.pop(lease_key)
        return True


class _NodeStore:
    def __init__(self, reservation=None, *, error=False):
        self.reservation = reservation
        self.error = error

    async def release(self, reservation):
        if self.error:
            raise RuntimeError("node budget unavailable")
        if self.reservation != reservation:
            return False
        self.reservation = None
        return True


@pytest.mark.asyncio
async def test_exact_owner_releases_all_persisted_resource_ownership():
    owner = "runner-a:task-1"
    lease_store = _LeaseStore({"lease-a": owner, "lease-b": owner})
    node_store = _NodeStore(_reservation(owner))

    result = await release_task_resource_ownership(
        SimpleNamespace(),
        owner_id=owner,
        lease_keys=["lease-a", "lease-b", "lease-a"],
        node_budget_reservation=node_store.reservation,
        lease_store=lease_store,
        node_budget_store=node_store,
    )

    assert result.complete is True
    assert result.requested_lease_keys == ("lease-a", "lease-b")
    assert result.released_lease_keys == ("lease-a", "lease-b")
    assert lease_store.owners == {}
    assert node_store.reservation is None


@pytest.mark.asyncio
async def test_mismatched_owner_is_preserved_and_reported_incomplete():
    owner = "runner-a:task-1"
    foreign_owner = "runner-b:task-2"
    lease_store = _LeaseStore({"lease-a": foreign_owner})
    foreign_reservation = _reservation(foreign_owner)
    node_store = _NodeStore(foreign_reservation)

    result = await release_task_resource_ownership(
        SimpleNamespace(),
        owner_id=owner,
        lease_keys=["lease-a"],
        node_budget_reservation=foreign_reservation,
        lease_store=lease_store,
        node_budget_store=node_store,
    )

    assert result.complete is False
    assert result.unreleased_lease_keys == ("lease-a",)
    assert result.node_reservation_owner_mismatch is True
    assert lease_store.owners == {"lease-a": foreign_owner}
    assert node_store.reservation == foreign_reservation


@pytest.mark.asyncio
async def test_store_errors_are_bounded_and_returned_as_evidence():
    owner = "runner-a:task-1"
    reservation = _reservation(owner)

    result = await release_task_resource_ownership(
        SimpleNamespace(),
        owner_id=owner,
        lease_keys=["lease-a"],
        node_budget_reservation=reservation,
        lease_store=_LeaseStore(error=True),
        node_budget_store=_NodeStore(reservation, error=True),
    )

    assert result.complete is False
    assert result.unreleased_lease_keys == ("lease-a",)
    assert len(result.errors) == 2
    assert result.errors[0].startswith("lease:lease-a:RuntimeError")
    assert result.errors[1].startswith("node_reservation:RuntimeError")


@pytest.mark.asyncio
async def test_context_adapter_derives_canonical_runner_task_owner():
    owner = "runner-a:task-1"
    reservation = _reservation(owner)
    lease_store = _LeaseStore({"lease-a": owner})
    node_store = _NodeStore(reservation)

    result = await release_task_resource_ownership_from_context(
        SimpleNamespace(),
        task_id="task-1",
        runner_id="runner-a",
        execution_context={
            "runner_resource_leases": [{"lease_key": "lease-a"}],
            "runner_node_budget_reservation": reservation.to_context(),
        },
        lease_store=lease_store,
        node_budget_store=node_store,
    )

    assert result.complete is True
    assert result.owner_id == owner


@pytest.mark.asyncio
async def test_missing_owner_or_queue_fails_closed_without_release():
    result = await release_task_resource_ownership(
        None,
        owner_id="",
        lease_keys=["lease-a"],
    )

    assert result.complete is False
    assert result.errors == ("owner_id_required",)
    assert result.unreleased_lease_keys == ("lease-a",)
