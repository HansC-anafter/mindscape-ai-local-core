import pytest

from backend.app.services.host_resources.route_identity_projection import (
    serialize_route_identity_projection,
)
from backend.app.services.host_resources.queue_preview import (
    build_route_reservation_candidate_previews,
)


@pytest.mark.asyncio
async def test_route_reservation_candidate_preview_selects_matching_pending_task():
    class _Client:
        def __init__(self):
            self.projections = {}

        async def lrange(self, key, start, end):
            return ["low-task", "high-task"]

        async def mget(self, keys):
            return [self.projections.get(key) for key in keys]

    class _Queue:
        pack_id = "default"
        q_pending = "pending"

        def __init__(self):
            self.client = _Client()

        async def _get_client(self):
            return self.client

    queue = _Queue()
    for task_id, route_request in {
        "low-task": {
            "target_lane": "runner:default_local",
            "resource_groups": ["default_local"],
        },
        "high-task": {
            "target_lane": "comfyui_runtime:flux2_klein_true_v2_q6_local",
            "resource_groups": ["apple_metal_heavy", "comfyui_generation"],
            "priority_class": "interactive_high",
        },
    }.items():
        queue.client.projections[
            f"mindscape:host_resources:route_identity:{task_id}"
        ] = serialize_route_identity_projection(
            task_id,
            {
                "task_id": task_id,
                "workspace_id": "ws-1",
                "pack_id": "comfyui_runtime",
                "task_type": "render",
                "route_identity": {
                    **route_request,
                    "lane_id": route_request.get("target_lane"),
                },
            },
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
        queue_stores=[queue],
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
        queue_stores=[_Queue()],
    )

    assert previews["res-1"]["state"] == "inactive"
    assert previews["res-1"]["tasks_scanned"] == 0
