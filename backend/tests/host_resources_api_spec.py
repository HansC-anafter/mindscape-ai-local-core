from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.routes.core import host_resources


def test_route_reservations_endpoint_forwards_state_limit_and_durable_flags(monkeypatch):
    received = {}

    def _list_route_reservations(**kwargs):
        received.update(kwargs)
        return [
            {
                "reservation_id": "res-active",
                "state": "reserved_waiting",
            }
        ]

    monkeypatch.setattr(
        host_resources,
        "list_route_reservations",
        _list_route_reservations,
    )
    app = FastAPI()
    app.include_router(host_resources.router)

    response = TestClient(app).get(
        "/api/v1/host-resources/route-reservations"
        "?state=active&include_durable=false&limit=5"
    )

    assert response.status_code == 200
    assert response.json() == {
        "reservations": [
            {
                "reservation_id": "res-active",
                "state": "reserved_waiting",
            }
        ]
    }
    assert received == {
        "include_durable": False,
        "state": "active",
        "limit": 5,
    }


def test_summary_endpoint_returns_compact_contract(monkeypatch):
    received = {}

    async def _get_host_resource_snapshot(**kwargs):
        received.update(kwargs)
        return {
            "captured_at": "2026-05-16T00:00:00Z",
            "degraded": False,
            "host": {
                "memory_pressure": {
                    "free_percent": 20,
                },
            },
            "capacity": {
                "memory_mb": 4096,
                "reserved_memory_mb": 1024,
            },
            "consumers": [
                {
                    "consumer_id": "ollama:process:1",
                    "label": "Ollama",
                    "memory_mb": 1024,
                    "memory_source": "rss",
                }
            ],
            "lanes": [
                {"lane_id": "lane:busy", "label": "Busy Lane", "state": "busy"},
                {"lane_id": "lane:paused", "label": "Paused Lane", "state": "paused"},
            ],
        }

    monkeypatch.setattr(host_resources, "get_host_resource_snapshot", _get_host_resource_snapshot)
    monkeypatch.setattr(
        host_resources,
        "list_active_route_reservations",
        lambda: [
            {
                "reservation_id": "res-1",
                "state": "reserved_waiting",
                "route_request": {
                    "target_lane": "comfyui_runtime:flux2",
                    "drain_policy": "drain_after_current",
                },
            }
        ],
    )
    app = FastAPI()
    app.include_router(host_resources.router)

    response = TestClient(app).get("/api/v1/host-resources/summary?refresh=true")

    assert response.status_code == 200
    assert response.json() == {
        "captured_at": "2026-05-16T00:00:00Z",
        "degraded": False,
        "pressure_state": "watch",
        "free_percent": 20,
        "headroom_mb": 4096,
        "reserved_mb": 1024,
        "lanes": {
            "busy": 1,
            "blocked": 1,
            "total": 2,
        },
        "heavy_consumers": [
            {
                "consumer_id": "ollama:process:1",
                "label": "Ollama",
                "memory_mb": 1024,
                "memory_source": "rss",
            }
        ],
        "primary_blockers": [
            {
                "lane_id": "lane:paused",
                "label": "Paused Lane",
                "state": "paused",
                "reason": None,
            }
        ],
        "route_controls": {
            "active": 1,
            "draining": 1,
            "targets": ["comfyui_runtime:flux2"],
        },
        "control_plane_pressure": {
            "state": "ok",
            "memory_mb": 0,
            "process_count": 0,
            "primary_blockers": [],
            "recommended_actions": [],
        },
        "alerts": [
            {
                "alert_id": "memory_pressure_watch",
                "severity": "warning",
                "message": "Host memory headroom is low",
                "action_href": "/settings?tab=runtime&section=host-resources",
            },
            {
                "alert_id": "host_resource_lanes_blocked",
                "severity": "warning",
                "message": "1 host resource lane(s) blocked",
                "action_href": "/settings?tab=runtime&section=host-resources",
            },
            {
                "alert_id": "route_drain_active",
                "severity": "info",
                "message": "1 route reservation(s) draining",
                "action_href": "/settings?tab=runtime&section=host-resources",
            },
        ],
        "dashboard_href": "/settings?tab=runtime&section=host-resources",
    }
    assert received == {"refresh": True}


def test_summary_endpoint_can_use_cached_snapshot_without_refresh(monkeypatch):
    called = {"snapshot": False}

    async def _get_host_resource_snapshot(**kwargs):
        called["snapshot"] = True
        return {}

    monkeypatch.setattr(host_resources, "get_host_resource_snapshot", _get_host_resource_snapshot)
    monkeypatch.setattr(
        host_resources,
        "get_cached_snapshot_or_degraded",
        lambda: {
            "captured_at": "2026-05-16T00:00:00Z",
            "degraded": False,
            "host": {"memory_pressure": {"free_percent": 40}},
            "capacity": {"memory_mb": 8192, "reserved_memory_mb": 0},
            "consumers": [],
            "lanes": [],
        },
    )
    monkeypatch.setattr(host_resources, "list_active_route_reservations", lambda: [])
    app = FastAPI()
    app.include_router(host_resources.router)

    response = TestClient(app).get("/api/v1/host-resources/summary?allow_stale=true")

    assert response.status_code == 200
    assert response.json()["pressure_state"] == "ok"
    assert called["snapshot"] is False


def test_admission_preview_endpoint_returns_gone_with_route_intent_replacement():
    app = FastAPI()
    app.include_router(host_resources.router)

    response = TestClient(app).get("/api/v1/host-resources/admission-preview?lane_id=lane:a")

    assert response.status_code == 410
    assert response.json()["detail"] == {
        "replacement": "/api/v1/host-resources/route-intents/preview",
        "reason": "admission_preview_replaced_by_route_intent_preview",
    }


def test_queue_utilization_endpoint_returns_latest_snapshot(monkeypatch):
    monkeypatch.setattr(
        host_resources,
        "get_latest_queue_utilization_snapshot",
        lambda: {
            "source": "postgres_snapshot",
            "queue_depths": {"browser_local": {"pending": 5}},
            "capacity_by_queue_shard": {
                "browser_local": {"max_inflight_total": 3}
            },
            "visible_lanes": {"browser_local": []},
            "visible_lane_count": {"browser_local": 0},
            "utilization_ratio_by_queue_shard": {"browser_local": 0},
            "degraded": False,
            "errors": [],
        },
    )
    app = FastAPI()
    app.include_router(host_resources.router)

    response = TestClient(app).get("/api/v1/host-resources/queue-utilization")

    assert response.status_code == 200
    assert response.json()["source"] == "postgres_snapshot"
    assert response.json()["queue_depths"]["browser_local"]["pending"] == 5


def test_adapter_catalog_endpoint_returns_first_batch_contract():
    app = FastAPI()
    app.include_router(host_resources.router)

    response = TestClient(app).get("/api/v1/host-resources/adapter-catalog")

    assert response.status_code == 200
    adapters = {adapter["adapter_id"]: adapter for adapter in response.json()["adapters"]}
    assert adapters["apple_mlx_vlm"]["model_binding_policy"] == "required"
    assert adapters["apple_mlx_vlm"]["default_model_binding_profile"] == "vision"
    assert adapters["mcp_desktop_control"]["worker_capable"] is False
    assert adapters["a2a_protocol_connector"]["model_binding_policy"] == "forbidden"


def test_queue_utilization_endpoint_live_uses_bounded_reader(monkeypatch):
    async def _build_live_queue_utilization():
        return {
            "source": "live_redis_bounded",
            "queue_depths": {"browser_local": {"pending": 5}},
            "capacity_by_queue_shard": {
                "browser_local": {"max_inflight_total": 3}
            },
            "visible_lanes": {"browser_local": []},
            "visible_lane_count": {"browser_local": 0},
            "utilization_ratio_by_queue_shard": {"browser_local": 0},
            "degraded": False,
            "errors": [],
        }

    monkeypatch.setattr(
        host_resources,
        "build_live_queue_utilization",
        _build_live_queue_utilization,
    )
    app = FastAPI()
    app.include_router(host_resources.router)

    response = TestClient(app).get(
        "/api/v1/host-resources/queue-utilization?live=true"
    )

    assert response.status_code == 200
    assert response.json()["source"] == "live_redis_bounded"


def test_route_intent_preview_endpoint_forwards_payload(monkeypatch):
    received = {}

    async def _build_route_intent_preview(payload, *, auth_context=None):
        received.update(payload)
        received["auth_user_id"] = getattr(auth_context, "user_id", None)
        return {
            "route_intent": payload,
            "route_intent_preview": {
                "decision": "preview_ready",
                "reservation_payload": {
                    "route_request": payload,
                },
            },
        }

    monkeypatch.setattr(
        host_resources,
        "build_route_intent_preview",
        _build_route_intent_preview,
    )
    app = FastAPI()
    app.include_router(host_resources.router)

    response = TestClient(app).post(
        "/api/v1/host-resources/route-intents/preview",
        json={"target_lane": "comfyui_runtime:flux2"},
    )

    assert response.status_code == 200
    assert response.json()["route_intent"] == {"target_lane": "comfyui_runtime:flux2"}
    assert received == {
        "target_lane": "comfyui_runtime:flux2",
        "auth_user_id": "default_user",
    }


def test_route_reservation_events_endpoint_returns_events(monkeypatch):
    monkeypatch.setattr(
        host_resources,
        "list_route_reservation_events",
        lambda reservation_id=None, limit=50: [
            {
                "event_id": "evt-1",
                "reservation_id": reservation_id,
                "event_type": "reservation_created",
                "limit": limit,
            }
        ],
    )
    app = FastAPI()
    app.include_router(host_resources.router)

    response = TestClient(app).get(
        "/api/v1/host-resources/route-reservations/events"
        "?reservation_id=res-1&limit=7"
    )

    assert response.status_code == 200
    assert response.json() == {
        "events": [
            {
                "event_id": "evt-1",
                "reservation_id": "res-1",
                "event_type": "reservation_created",
                "limit": 7,
            }
        ]
    }


def test_create_lane_endpoint_returns_created_dynamic_lane(monkeypatch):
    received = {}

    def _create_dynamic_lane(payload):
        received.update(payload)
        return {"lane_id": payload["lane_id"], "queue_shard": payload["queue_shard"]}

    monkeypatch.setattr(host_resources, "create_dynamic_lane", _create_dynamic_lane)
    app = FastAPI()
    app.include_router(host_resources.router)

    response = TestClient(app).post(
        "/api/v1/host-resources/lanes",
        json={
            "lane_id": "runner:vision_mlx_high",
            "capability_scope": "ig",
            "label": "Vision MLX High",
            "kind": "vision_analyze",
            "queue_shard": "vision_mlx_high",
            "runner_profile": "vision_mlx_high",
            "resource_class": "compute",
        },
    )

    assert response.status_code == 200
    assert response.json()["lane"]["queue_shard"] == "vision_mlx_high"
    assert received["lane_id"] == "runner:vision_mlx_high"


def test_worker_target_endpoint_returns_blocked_result(monkeypatch):
    async def _set_lane_worker_target(lane_id, desired_worker_count, **kwargs):
        return {
            "accepted": False,
            "lane_id": lane_id,
            "desired_worker_count": desired_worker_count,
            "reason": "pgbouncer_client_waiting",
            "auth_user_id": getattr(kwargs.get("auth_context"), "user_id", None),
        }

    monkeypatch.setattr(
        host_resources,
        "set_lane_worker_target",
        _set_lane_worker_target,
    )
    app = FastAPI()
    app.include_router(host_resources.router)

    response = TestClient(app).post(
        "/api/v1/host-resources/lanes/runner:vision_mlx_high/worker-target",
        json={"desired_worker_count": 1},
    )

    assert response.status_code == 200
    assert response.json()["accepted"] is False
    assert response.json()["reason"] == "pgbouncer_client_waiting"
    assert response.json()["auth_user_id"] == "default_user"


def test_workspace_allocations_endpoint_returns_effective_matrix(monkeypatch):
    class _Store:
        def list_allocations(self, **kwargs):
            assert kwargs["workspace_id"] == "ws-1"
            return [
                {
                    "allocation_id": "alloc-1",
                    "workspace_id": "ws-1",
                    "queue_shard": "browser_local",
                    "task_family": "ig_browser_capture",
                    "max_parallel_task_claims": 3,
                }
            ]

    monkeypatch.setattr(
        host_resources,
        "HostResourceWorkspaceAllocationStore",
        lambda scope: _Store(),
    )
    monkeypatch.setattr(
        host_resources,
        "require_workspace_resource_access",
        lambda current_user, workspace_id: workspace_id,
    )
    monkeypatch.setattr(
        host_resources,
        "build_workspace_allocation_effective_matrix",
        lambda workspace_id: {
            "workspace_id": workspace_id,
            "effective_matrix": [
                {
                    "queue_shard": "browser_local",
                    "task_family": "ig_browser_capture",
                    "max_parallel_task_claims": 3,
                }
            ],
        },
    )
    app = FastAPI()
    app.include_router(host_resources.router)

    response = TestClient(app).get(
        "/api/v1/host-resources/workspace-allocations?workspace_id=ws-1"
    )

    assert response.status_code == 200
    assert response.json()["allocations"][0]["task_family"] == "ig_browser_capture"
    assert response.json()["effective"]["effective_matrix"][0]["max_parallel_task_claims"] == 3


def test_allocation_blueprint_apply_endpoint_materializes_workspace_quota(monkeypatch):
    received = {}

    def _apply_allocation_blueprint_to_workspace(**kwargs):
        received.update(kwargs)
        return {
            "blueprint": {"blueprint_id": kwargs["blueprint_id"]},
            "application": {"workspace_id": kwargs["workspace_id"]},
            "allocations": [
                {
                    "workspace_id": kwargs["workspace_id"],
                    "queue_shard": "browser_local",
                    "task_family": "ig_browser_capture",
                    "max_parallel_task_claims": 3,
                }
            ],
        }

    monkeypatch.setattr(
        host_resources,
        "require_workspace_resource_access",
        lambda current_user, workspace_id: workspace_id,
    )
    monkeypatch.setattr(
        host_resources,
        "apply_allocation_blueprint_to_workspace",
        _apply_allocation_blueprint_to_workspace,
    )
    monkeypatch.setattr(
        host_resources,
        "build_workspace_allocation_effective_matrix",
        lambda workspace_id: {
            "workspace_id": workspace_id,
            "effective_matrix": [{"queue_shard": "browser_local"}],
        },
    )
    app = FastAPI()
    app.include_router(host_resources.router)

    response = TestClient(app).post(
        "/api/v1/host-resources/allocation-blueprints/ig-content-production-default/apply",
        json={"workspace_id": "ws-1"},
    )

    assert response.status_code == 200
    assert response.json()["application"]["workspace_id"] == "ws-1"
    assert response.json()["effective"]["effective_matrix"][0]["queue_shard"] == "browser_local"
    assert received == {
        "workspace_id": "ws-1",
        "blueprint_id": "ig-content-production-default",
        "actor_id": "default_user",
    }
