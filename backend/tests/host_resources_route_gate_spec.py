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


def test_route_gate_detects_drain_after_current_controls():
    active_reservations = [
        {
            "reservation_id": "res-1",
            "state": "reserved_waiting",
            "route_request": {
                "target_lane": "comfyui_runtime:flux2_klein_true_v2_q6_local",
                "resource_groups": ["apple_metal_heavy"],
                "drain_policy": "drain_after_current",
            },
        },
        {
            "reservation_id": "res-2",
            "state": "reserved_waiting",
            "route_request": {
                "target_lane": "runner:default_local",
                "resource_groups": ["default_local"],
                "drain_policy": "prefer_only",
            },
        },
    ]

    drain_reservations = route_gate.drain_after_current_reservations(
        active_reservations
    )

    assert route_gate.has_drain_after_current_controls(active_reservations) is True
    assert [reservation["reservation_id"] for reservation in drain_reservations] == ["res-1"]


def test_worker_reads_runner_claim_gate(monkeypatch):
    import backend.app.services.host_resources as host_resources

    monkeypatch.setattr(
        host_resources,
        "get_runner_claim_gate",
        lambda: {
            "state": "paused",
            "reason": "postgres_maintenance",
            "source": "redis",
            "persisted": True,
        },
    )

    gate = worker._runner_claim_gate_status()

    assert gate["state"] == "paused"
    assert gate["reason"] == "postgres_maintenance"


@pytest.mark.asyncio
async def test_worker_maintenance_cycle_skips_when_claim_gate_paused(monkeypatch):
    monkeypatch.setattr(
        worker,
        "_runner_claim_gate_status",
        lambda: {
            "state": "paused",
            "reason": "postgres_maintenance",
            "source": "redis",
            "persisted": True,
        },
    )

    def fail_if_called(*args, **kwargs):
        raise AssertionError("maintenance should not run while claim gate is paused")

    monkeypatch.setattr(worker, "_reap_stale_running_tasks", fail_if_called)
    monkeypatch.setattr(worker, "_request_watchdog_abort_for_no_progress_tasks", fail_if_called)
    monkeypatch.setattr(worker, "_reap_redis_queues", fail_if_called)
    monkeypatch.setattr(worker, "_cleanup_stale_locks", fail_if_called)

    await worker._run_maintenance_cycle(
        tasks_store=object(),
        runner_id="runner-1",
        redis_queue=object(),
        ready_queues={"default_local": object()},
        ready_targets={"default_local": 1},
        queue_cycle=[],
    )


def test_worker_reads_route_drain_gate(monkeypatch):
    monkeypatch.setattr(
        route_gate,
        "get_active_route_reservations",
        lambda: [
            {
                "reservation_id": "res-drain",
                "state": "reserved_waiting",
                "route_request": {
                    "target_lane": "comfyui_runtime:flux2_klein_true_v2_q6_local",
                    "resource_groups": ["apple_metal_heavy"],
                    "drain_policy": "drain_after_current",
                },
            }
        ],
    )

    status = worker._route_drain_after_current_status()

    assert status["active"] is True
    assert status["reservation_ids"] == ["res-drain"]


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
