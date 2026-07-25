from types import SimpleNamespace

import pytest

from backend.app.runner import worker
from backend.app.services.host_resources import route_gate
from backend.app.services.host_resources.route_identity_projection import (
    serialize_route_identity_projection,
)


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
                "target_lane": "runner:default_local_browser",
                "resource_groups": ["default_local_browser"],
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
                "target_lane": "runner:default_local_browser",
                "resource_groups": ["default_local_browser"],
                "drain_policy": "prefer_only",
            },
        },
    ]

    drain_reservations = route_gate.drain_after_current_reservations(
        active_reservations
    )

    assert route_gate.has_drain_after_current_controls(active_reservations) is True
    assert [reservation["reservation_id"] for reservation in drain_reservations] == ["res-1"]


def test_route_gate_drain_after_current_ignores_unrelated_candidates():
    selection = route_gate.select_candidate_policy(
        [
            {
                "task_id": "task-browser",
                "pack_id": "browser_batch_collect",
                "route_identity": {
                    "lane_id": "runner:default_local_browser",
                    "resource_groups": ["runner:default_local_browser"],
                    "priority_class": "default",
                },
            }
        ],
        active_reservations=[
            {
                "reservation_id": "res-mps",
                "state": "reserved_waiting",
                "route_request": {
                    "target_lane": "comfyui_runtime:flux2_klein_true_v2_q6_local",
                    "resource_groups": ["mps_generation", "comfyui_runtime"],
                    "resource_flavor": "local.mps.comfyui",
                    "drain_policy": "drain_after_current",
                },
            }
        ],
    )

    assert selection["selected"] is None
    assert selection["reason"] == "fifo_fallback"
    assert selection["drain_wait"] is False


def test_route_gate_drain_after_current_ignores_empty_route_identity():
    selection = route_gate.select_candidate_policy(
        [
            {
                "task_id": "task-browser",
                "pack_id": "browser_batch_collect",
                "route_identity": {},
            }
        ],
        active_reservations=[
            {
                "reservation_id": "res-mps",
                "state": "reserved_waiting",
                "route_request": {
                    "target_lane": "comfyui_runtime:flux2_klein_true_v2_q6_local",
                    "resource_groups": ["mps_generation", "comfyui_runtime"],
                    "resource_flavor": "local.mps.comfyui",
                    "drain_policy": "drain_after_current",
                },
            }
        ],
    )

    assert selection["selected"] is None
    assert selection["reason"] == "fifo_fallback"
    assert selection["drain_wait"] is False


def test_route_gate_drain_after_current_selects_matching_candidates():
    selection = route_gate.select_candidate_policy(
        [
            {
                "task_id": "task-comfy",
                "pack_id": "comfyui_runtime",
                "route_identity": {
                    "lane_id": "comfyui_runtime:flux2_klein_true_v2_q6_local",
                    "resource_groups": ["mps_generation"],
                    "priority_class": "default",
                    "resource_flavor": "local.mps.comfyui",
                },
            }
        ],
        active_reservations=[
            {
                "reservation_id": "res-mps",
                "state": "reserved_waiting",
                "route_request": {
                    "target_lane": "comfyui_runtime:flux2_klein_true_v2_q6_local",
                    "resource_groups": ["mps_generation", "comfyui_runtime"],
                    "resource_flavor": "local.mps.comfyui",
                    "drain_policy": "drain_after_current",
                },
            }
        ],
    )

    assert selection["selected"]["task_id"] == "task-comfy"
    assert selection["reason"] == "route_reservation"
    assert selection["drain_wait"] is False
    assert selection["decision"].reservation_id == "res-mps"


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
        ready_queues={"default_local_browser": object()},
        ready_targets={"default_local_browser": 1},
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
        def __init__(self):
            self.projections = {}

        async def lrange(self, key, start, end):
            return ["low-task", "high-task"]

        async def llen(self, key):
            return 2

        async def mget(self, keys):
            return [self.projections.get(key) for key in keys]

    class _Queue:
        pack_id = "ig"
        q_pending = "pending"

        def __init__(self):
            self.client = _Client()

        async def _get_client(self):
            return self.client

        async def promote_pending_task_by_id(self, task_id, visibility_timeout_sec):
            self.promoted = task_id
            return task_id

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
    for task_id, route_request in {
        "low-task": {
            "target_lane": "runner:default_local_browser",
            "resource_groups": ["default_local_browser"],
        },
        "high-task": {
            "target_lane": "comfyui_runtime:flux2_klein_true_v2_q6_local",
            "resource_groups": ["apple_metal_heavy"],
            "priority_class": "interactive_high",
        },
    }.items():
        queue.client.projections[
            f"mindscape:host_resources:route_identity:{task_id}"
        ] = serialize_route_identity_projection(
            task_id,
            {
                "task_id": task_id,
                "pack_id": "comfyui_runtime",
                "route_identity": {
                    **route_request,
                    "lane_id": route_request.get("target_lane"),
                },
            },
        )
    task_id, task_queue, drain_wait, profile_filter_wait = (
        await worker._dequeue_by_route_gate_policy(
        [queue],
        runner_profile=SimpleNamespace(profile_code="default"),
        visibility_timeout_sec=180,
        scan_limit=10,
        )
    )

    assert task_id == "high-task"
    assert task_queue is queue
    assert drain_wait is False
    assert profile_filter_wait is False
    assert queue.promoted == "high-task"
