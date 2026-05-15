from types import SimpleNamespace

import pytest

from backend.app.models.workspace import TaskStatus
from backend.app.services.host_resources.queue_preview import (
    build_route_reservation_candidate_previews,
)


@pytest.mark.asyncio
async def test_route_reservation_candidate_preview_selects_matching_pending_task():
    class _Client:
        async def lrange(self, key, start, end):
            return ["low-task", "high-task"]

    class _Queue:
        pack_id = "default"
        q_pending = "pending"

        async def _get_client(self):
            return _Client()

    class _Tasks:
        def get_task(self, task_id):
            route_request = {
                "target_lane": "runner:default_local",
                "resource_groups": ["default_local"],
            }
            if task_id == "high-task":
                route_request = {
                    "target_lane": "comfyui_runtime:flux2_klein_true_v2_q6_local",
                    "resource_groups": ["apple_metal_heavy", "comfyui_generation"],
                    "priority_class": "interactive_high",
                }
            return SimpleNamespace(
                id=task_id,
                workspace_id="ws-1",
                pack_id="comfyui_runtime",
                task_type="render",
                status=TaskStatus.PENDING,
                blocked_reason=None,
                execution_context={"route_request": route_request},
            )

    previews = await build_route_reservation_candidate_previews(
        [
            {
                "reservation_id": "res-1",
                "state": "reserved_waiting",
                "route_request": {
                    "target_lane": "comfyui_runtime:flux2_klein_true_v2_q6_local",
                    "resource_groups": ["apple_metal_heavy", "comfyui_generation"],
                },
            }
        ],
        tasks_store=_Tasks(),
        queue_stores=[_Queue()],
        scan_limit=10,
    )

    preview = previews["res-1"]
    assert preview["tasks_scanned"] == 2
    assert preview["matching_count"] == 1
    assert preview["selected_candidate"]["task_id"] == "high-task"
    assert preview["selected_candidate"]["queue_position"] == 1


@pytest.mark.asyncio
async def test_route_reservation_candidate_preview_skips_cancelled_reservation():
    class _Queue:
        pack_id = "default"
        q_pending = "pending"

        async def _get_client(self):  # pragma: no cover - should not be called
            raise AssertionError("inactive reservations should not scan queues")

    previews = await build_route_reservation_candidate_previews(
        [{"reservation_id": "res-1", "state": "cancelled"}],
        tasks_store=SimpleNamespace(get_task=lambda task_id: None),
        queue_stores=[_Queue()],
    )

    assert previews["res-1"]["state"] == "inactive"
    assert previews["res-1"]["tasks_scanned"] == 0
