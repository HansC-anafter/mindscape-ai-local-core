from types import SimpleNamespace

import pytest

from backend.app.models.workspace import TaskStatus
from backend.app.runner import worker
from backend.app.services.host_resources import route_gate


def _task(task_id: str, route_request: dict):
    return SimpleNamespace(
        id=task_id,
        execution_context={"route_request": route_request},
    )


def test_route_gate_prefers_matching_reserved_lane(monkeypatch):
    monkeypatch.setattr(
        route_gate,
        "list_active_route_reservations",
        lambda: [
            {
                "reservation_id": "res-1",
                "state": "reserved_waiting",
                "route_request": {
                    "target_lane": "comfyui_runtime:flux2_klein_true_v2_q6_local",
                    "resource_groups": ["apple_metal_heavy"],
                },
            }
        ],
    )

    decision = route_gate.evaluate_route_candidate(
        _task(
            "task-1",
            {
                "target_lane": "comfyui_runtime:flux2_klein_true_v2_q6_local",
                "resource_groups": ["apple_metal_heavy"],
                "priority_class": "interactive_high",
            },
        )
    )

    assert decision.permit is True
    assert decision.reservation_id == "res-1"
    assert decision.score >= 1300


def test_route_gate_rejects_unmatched_candidate(monkeypatch):
    monkeypatch.setattr(
        route_gate,
        "list_active_route_reservations",
        lambda: [
            {
                "reservation_id": "res-1",
                "state": "reserved_waiting",
                "route_request": {
                    "target_lane": "comfyui_runtime:flux2_klein_true_v2_q6_local",
                    "resource_groups": ["apple_metal_heavy"],
                },
            }
        ],
    )

    decision = route_gate.evaluate_route_candidate(
        _task(
            "task-2",
            {
                "target_lane": "runner:default_local",
                "resource_groups": ["default_local"],
            },
        )
    )

    assert decision.permit is False
    assert decision.reason == "no_matching_route_reservation"


@pytest.mark.asyncio
async def test_worker_route_candidate_scan_promotes_permitted_task(monkeypatch):
    class _Client:
        async def lrange(self, key, start, end):
            return ["low-task", "high-task"]

    class _Queue:
        pack_id = "ig"
        q_pending = "pending"

        async def _get_client(self):
            return _Client()

        async def promote_pending_task_by_id(self, task_id, visibility_timeout_sec):
            self.promoted = task_id
            return task_id

    class _Store:
        def get_task(self, task_id):
            route_request = {
                "target_lane": "runner:default_local",
                "resource_groups": ["default_local"],
            }
            if task_id == "high-task":
                route_request = {
                    "target_lane": "comfyui_runtime:flux2_klein_true_v2_q6_local",
                    "resource_groups": ["apple_metal_heavy"],
                    "priority_class": "interactive_high",
                }
            return SimpleNamespace(
                id=task_id,
                status=TaskStatus.PENDING,
                execution_context={"route_request": route_request},
            )

    monkeypatch.setattr(worker, "runner_profile_can_claim_task", lambda profile, task: True)
    monkeypatch.setattr(
        route_gate,
        "list_active_route_reservations",
        lambda: [
            {
                "reservation_id": "res-1",
                "state": "reserved_waiting",
                "route_request": {
                    "target_lane": "comfyui_runtime:flux2_klein_true_v2_q6_local",
                    "resource_groups": ["apple_metal_heavy"],
                },
            }
        ],
    )

    queue = _Queue()
    task_id, task_queue = await worker._dequeue_preferred_route_candidate(
        [queue],
        tasks_store=_Store(),
        runner_profile=SimpleNamespace(profile_code="default"),
        visibility_timeout_sec=180,
        scan_limit=10,
    )

    assert task_id == "high-task"
    assert task_queue is queue
    assert queue.promoted == "high-task"
