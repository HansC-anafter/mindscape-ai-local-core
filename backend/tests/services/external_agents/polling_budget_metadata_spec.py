from backend.app.services.external_agents.bridge.polling_budget_metadata import (
    attach_polling_budget_metadata,
    build_polling_budget_metadata,
)


class _Client:
    POLLING_LEASE_SECONDS = 45
    POLLING_WAIT_SECONDS = 20
    POLLING_HEARTBEAT_INTERVAL = 10

    def __init__(self) -> None:
        self._active_tasks = 2


def test_build_polling_budget_metadata_describes_bounded_transport_budget():
    metadata = build_polling_budget_metadata(
        reason="task_result",
        client=_Client(),
    )

    assert metadata == {
        "bounded": True,
        "reason": "task_result",
        "reserve_limit": 1,
        "lease_seconds": 45.0,
        "wait_seconds": 20.0,
        "heartbeat_interval_seconds": 10.0,
        "active_tasks": 2,
    }


def test_attach_polling_budget_metadata_preserves_existing_metadata():
    metadata = attach_polling_budget_metadata(
        {"transport": "polling", "runtime_id": "vision"},
        reason="timeout_without_terminal_result",
        wait_slice_seconds=5,
    )

    assert metadata["transport"] == "polling"
    assert metadata["runtime_id"] == "vision"
    assert metadata["polling_budget"]["bounded"] is True
    assert metadata["polling_budget"]["wait_slice_seconds"] == 5.0
