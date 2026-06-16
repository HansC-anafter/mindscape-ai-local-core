from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.dependencies.auth import AuthContext, get_current_user
from backend.app.routes.runtime_dispatch import router
from backend.app.services.resource_governance import context as governance_context
from backend.app.services.runtime_dispatch import metadata


def test_target_metadata_is_derived_from_host_resource_lanes(monkeypatch):
    monkeypatch.setattr(
        metadata,
        "list_host_resource_lanes",
        lambda: [
            {
                "lane_id": "runner:qwen9b",
                "workspace_id": None,
                "label": "Qwen 9B",
                "capability_scope": "ig",
                "kind": "vision_analyze",
                "queue_shard": "vision_mlx_dev",
                "runner_profile": "vision_mlx_dev",
                "resource_class": "compute",
                "priority_class": "interactive_high",
                "resource_flavor": "local.mlx.vision",
                "state": "available",
                "max_concurrency": 1,
                "desired_worker_count": 1,
                "model_profile": {"runtime_engine": "mlx"},
                "requirements": {"memory_mb": 6144},
            },
            {
                "lane_id": "runner:other",
                "workspace_id": "other-workspace",
                "label": "Other",
                "queue_shard": "other",
                "state": "available",
            },
        ],
    )
    monkeypatch.setattr(
        metadata,
        "get_latest_queue_utilization_snapshot",
        lambda: {
            "source": "postgres_snapshot",
            "capacity_by_queue_shard": {
                "vision_mlx_dev": {
                    "active_runner_count": 1,
                    "claimable_runner_count": 1,
                    "available_slots_total": 1,
                    "max_inflight_total": 1,
                },
            },
            "queue_depths": {"vision_mlx_dev": {"pending": 0, "processing": 0}},
            "utilization_ratio_by_queue_shard": {"vision_mlx_dev": 0},
            "degraded": False,
            "errors": [],
        },
    )

    payload = metadata.list_runtime_dispatch_targets("ws-a")

    assert payload["count"] == 1
    target = payload["targets"][0]
    assert target["lane_id"] == "runner:qwen9b"
    assert target["queue_shard"] == "vision_mlx_dev"
    assert target["runner_profile"] == "vision_mlx_dev"
    assert target["resource_class"] == "compute"
    assert target["assignable"] is True
    assert target["capacity_summary"]["claimable_runner_count"] == 1


def test_targets_endpoint_enforces_workspace_access(monkeypatch):
    monkeypatch.setattr(governance_context, "get_default_user_id", lambda: "default_user")
    monkeypatch.setattr(metadata, "list_host_resource_lanes", lambda: [])
    monkeypatch.setattr(
        metadata,
        "get_latest_queue_utilization_snapshot",
        lambda: {"source": "postgres_snapshot", "degraded": False, "errors": []},
    )
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: AuthContext(
        user_id="limited-user",
        tenant_id="local",
        workspace_ids=["ws-a"],
    )

    response = TestClient(app).get(
        "/api/v1/runtime-dispatch/targets?workspace_id=ws-b"
    )

    assert response.status_code == 403
    assert response.json()["detail"]["reason"] == "workspace_resource_access_denied"
