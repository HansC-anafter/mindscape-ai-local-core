from capabilities.ig.services.reference_analysis_lanes import (
    LANE_LOCK_INPUT,
    _build_assignment_context,
    _resolve_assignment_concurrency_key,
)
from capabilities.ig.services.reference_analysis_task_locator import _row_to_task


def test_lane_assignment_scopes_concurrency_to_workspace_queue():
    task = {
        "task_id": "task-35b-1",
        "reference_id": "ref-35b-1",
        "workspace_id": "workspace-35b",
        "analysis_profile": "visual_anatomy",
        "execution_context": {
            "inputs": {
                "reference_id": "ref-35b-1",
                "workload_execution_intent": {
                    "meta": {"workspace_allocation_id": "allocation-35b"}
                },
            },
            "concurrency": {"max_parallel": 1, "lock_scope": "playbook"},
            "route_request": {},
        },
    }
    lane = {
        "runner_profile": "vision_mlx_high",
        "resource_class": "compute",
        "priority_class": "default",
        "resource_flavor": "local.mlx.vision",
    }

    context = _build_assignment_context(
        task=task,
        lane=lane,
        lane_id="runner:vision_mlx_high",
        queue_shard="vision_mlx_high",
    )

    assert context["workspace_id"] == "workspace-35b"
    assert context["queue_shard"] == "vision_mlx_high"
    assert context["concurrency"] == {
        "max_parallel": 1,
        "lock_scope": "playbook_input",
        "lock_key_input": LANE_LOCK_INPUT,
        "default_lock_key_value": "workspace-35b:vision_mlx_high",
    }
    assert context["inputs"][LANE_LOCK_INPUT] == "workspace-35b:vision_mlx_high"
    assert context["route_request"]["target_lane"] == "runner:vision_mlx_high"
    assert context["route_request"]["workspace_allocation_id"] == "allocation-35b"
    assert _resolve_assignment_concurrency_key(context) == (
        "concurrency:playbook_input:ig_analyze_pinned_reference:"
        "workspace-35b:vision_mlx_high"
    )


def test_reference_analysis_task_locator_maps_workspace_id():
    class Store:
        def deserialize_json(self, value, default=None):
            return value if isinstance(value, dict) else default

    task = _row_to_task(
        Store(),
        {
            "task_id": "task-1",
            "execution_id": "execution-1",
            "parent_execution_id": None,
            "workspace_id": "workspace-1",
            "status": "pending",
            "frontier_state": "ready",
            "queue_shard": "vision_local",
            "reference_id": "ref-1",
            "analysis_profile": "visual_anatomy",
            "execution_context": {},
            "params": {},
            "created_at": None,
        },
    )

    assert task["workspace_id"] == "workspace-1"
