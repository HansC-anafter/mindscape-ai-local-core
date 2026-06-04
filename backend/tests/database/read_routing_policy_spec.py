import pytest

from backend.app.database import read_routing_policy


def test_smoke_route_is_allowed_by_default():
    assert read_routing_policy.is_readonly_route_allowed(
        read_routing_policy.READONLY_SMOKE_ROUTE_ID
    )


def test_future_read_model_route_must_be_registered_explicitly():
    route_id = "read_model.workspace_summary.list"

    assert not read_routing_policy.is_readonly_route_allowed(route_id)
    assert read_routing_policy.is_readonly_route_allowed(
        route_id,
        additional_route_ids={route_id},
    )
    assert (
        read_routing_policy.require_readonly_route_allowed(
            route_id,
            additional_route_ids={route_id},
        )
        == route_id
    )


@pytest.mark.parametrize(
    "route_id",
    [
        "task.claim",
        "runner.heartbeat",
        "migration.apply",
        "capability_pack.install",
        "queue.admission",
        "lock.acquire",
    ],
)
def test_mutating_or_locking_routes_are_rejected(route_id):
    assert not read_routing_policy.is_readonly_route_allowed(route_id)
    with pytest.raises(ValueError, match="Read-only PostgreSQL routing is not allowed"):
        read_routing_policy.require_readonly_route_allowed(route_id)
