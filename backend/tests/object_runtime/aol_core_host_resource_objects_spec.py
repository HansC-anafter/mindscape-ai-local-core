from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from backend.app.services.host_resources import manager
from backend.app.services.object_runtime import core_host_resource_objects as objects


def test_core_host_resource_facade_keeps_backend_callable_names():
    expected_callables = [
        "list_core_object_catalog_entries",
        "sync_host_resource_lane_index",
        "sync_resource_budget_policy_index",
        "sync_workspace_resource_allocation_index",
        "sync_route_reservation_index",
        "resolve_host_resource_lane_summary",
        "resolve_resource_budget_policy_summary",
        "resolve_workspace_resource_allocation_summary",
        "resolve_route_reservation_summary",
        "resolve_host_resource_lane_actions",
        "plan_preview_route_intent",
        "execute_preview_route_intent",
    ]

    for name in expected_callables:
        assert callable(getattr(objects, name))


def test_sync_host_resource_lane_index_returns_stable_aol_records(monkeypatch):
    monkeypatch.setattr(
        manager,
        "list_host_resource_lanes",
        lambda: [
            {
                "lane_id": "comfyui_runtime:flux2_klein_true_v2_q6_local",
                "label": "ComfyUI FLUX.2 Klein local lane",
                "kind": "comfyui",
                "state": "ready",
                "resource_flavor": "mps",
                "requirements": {
                    "memory_mb": 16384,
                    "exclusive_groups": ["mps_generation", "comfyui_runtime"],
                },
            }
        ],
    )

    payload = objects.sync_host_resource_lane_index(workspace_id="ws_demo")

    assert payload["source"] == "local_core.host_resource_lane"
    assert len(payload["records"]) == 1
    record = payload["records"][0]
    assert record.ref.uri == (
        "mindscape://local_core/host_resource_lane/"
        "comfyui_runtime:flux2_klein_true_v2_q6_local"
    )
    assert record.ref.workspace_id == "ws_demo"
    assert record.title == "ComfyUI FLUX.2 Klein local lane"
    assert "preview_route_intent" in record.affordance_verbs
    assert record.metadata["requirements"]["memory_mb"] == 16384
    assert "worker_target" not in record.search_text


def test_sync_resource_budget_policy_index_is_static_and_bounded():
    payload = objects.sync_resource_budget_policy_index(
        workspace_id="ws_demo",
        object_ids=["comfyui_visual_iteration_strict"],
    )

    assert [record.ref.object_id for record in payload["records"]] == [
        "comfyui_visual_iteration_strict"
    ]
    policy = payload["records"][0].metadata["policy"]
    assert policy["requires_route_reservation"] is True
    assert policy["max_iterations"] == 2


def test_preview_route_intent_plan_is_non_mutating():
    plan = objects.plan_preview_route_intent(
        workspace_id="ws_demo",
        role_assignments=[
            {
                "role": "target",
                "ref": {
                    "owner_pack": "local_core",
                    "object_kind": "host_resource_lane",
                    "object_id": "runner:vision_local",
                },
            }
        ],
        request_context={},
    )

    assert plan["route_request"]["target_lane"] == "runner:vision_local"
    assert plan["route_request"]["workspace_id"] == "ws_demo"
    assert plan["request_context"]["resource_mutation"] == "none"


def test_core_host_resource_helpers_do_not_open_resource_owner_paths():
    helper_root = (
        REPO_ROOT
        / "backend"
        / "app"
        / "services"
        / "object_runtime"
        / "core_host_resources"
    )
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(helper_root.glob("*.py"))
    )

    for forbidden in [
        "MAX(captured_at)",
        "latest_batch",
        "setInterval",
        "EventSource",
        "new WebSocket",
        "poll(",
        "PgBouncer",
        "pgbouncer",
        "worker start",
        "docker compose",
        "enqueue",
        "create_route_reservation",
    ]:
        assert forbidden not in source
