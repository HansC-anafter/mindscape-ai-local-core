from pathlib import Path
import importlib.util
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _load_system_control_module():
    module_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "routes"
        / "core"
        / "system_settings"
        / "system_control.py"
    )
    spec = importlib.util.spec_from_file_location("system_control_test_module", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class StubRestartWebhook:
    def __init__(self, configured=True, responses=None):
        self.configured = configured
        self.responses = responses or {}
        self.calls = []

    def is_configured(self) -> bool:
        return self.configured

    async def notify_restart_required(
        self,
        capability_code: str,
        validation_passed: bool,
        version: str = "1.0.0",
        extra_data=None,
        service: str = "backend",
    ):
        self.calls.append(
            {
                "capability_code": capability_code,
                "validation_passed": validation_passed,
                "version": version,
                "service": service,
            }
        )
        return self.responses.get(service, {"sent": True, "service": service})


def _build_client(monkeypatch, webhook: StubRestartWebhook):
    system_control = _load_system_control_module()
    monkeypatch.setattr(
        system_control,
        "get_restart_webhook_service",
        lambda: webhook,
    )
    monkeypatch.setattr(system_control, "_is_localhost", lambda _request: True)
    app = FastAPI()
    app.include_router(system_control.router, prefix="/api/v1/system-settings")
    return TestClient(app), system_control


def test_restart_valid_service_runner(monkeypatch):
    webhook = StubRestartWebhook(
        configured=True,
        responses={
            "runner-default": {"sent": True, "service": "runner-default"},
            "runner-browser": {"sent": True, "service": "runner-browser"},
            "runner-vision": {"sent": True, "service": "runner-vision"},
        },
    )
    client, _system_control = _build_client(monkeypatch, webhook)

    response = client.post(
        "/api/v1/system-settings/restart",
        json={"service": "runner"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["method"] == "device_node"
    assert data["targets"] == [
        "runner-default",
        "runner-browser",
        "runner-vision",
    ]
    assert len(webhook.calls) == 3
    assert [call["service"] for call in webhook.calls] == data["targets"]


def test_restart_invalid_service_rejected(monkeypatch):
    webhook = StubRestartWebhook(configured=True)
    client, _system_control = _build_client(monkeypatch, webhook)

    response = client.post(
        "/api/v1/system-settings/restart",
        json={"service": "invalid"},
    )

    assert response.status_code == 400
    assert "Invalid service" in response.json()["detail"]
    assert webhook.calls == []


def test_restart_device_node_offline_fallback(monkeypatch):
    webhook = StubRestartWebhook(
        configured=True,
        responses={
            "runner-default": {
                "sent": False,
                "reason": "device_node_unreachable",
                "service": "runner-default",
            },
            "runner-browser": {
                "sent": False,
                "reason": "device_node_unreachable",
                "service": "runner-browser",
            },
            "runner-vision": {
                "sent": False,
                "reason": "device_node_unreachable",
                "service": "runner-vision",
            },
        },
    )
    client, system_control = _build_client(monkeypatch, webhook)
    sentinel_path = Path("/tmp/test_restart_runner_sentinel.json")
    monkeypatch.setattr(system_control, "_RUNNER_SENTINEL_PATH", sentinel_path)

    response = client.post(
        "/api/v1/system-settings/restart",
        json={"service": "runner"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["method"] == "runner_sentinel"
    assert data["targets"] == [
        "runner-default",
        "runner-browser",
        "runner-vision",
    ]
    assert sentinel_path.exists()


def test_restart_specific_runner_pool_offline_falls_back_to_manual(monkeypatch):
    webhook = StubRestartWebhook(
        configured=True,
        responses={
            "runner-browser": {
                "sent": False,
                "reason": "device_node_unreachable",
                "service": "runner-browser",
            }
        },
    )
    client, _system_control = _build_client(monkeypatch, webhook)

    response = client.post(
        "/api/v1/system-settings/restart",
        json={"service": "runner-browser"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert data["method"] == "manual"
    assert data["targets"] == ["runner-browser"]
    assert data["instruction"] == "docker compose restart runner-browser"


def test_queue_metrics_includes_active_runner_heartbeats(monkeypatch):
    webhook = StubRestartWebhook(configured=True)
    client, _system_control = _build_client(monkeypatch, webhook)

    from backend.app.services.stores.redis.runner_queue_store import RedisRunnerQueueStore
    from backend.app.services.stores.tasks_store import TasksStore

    monkeypatch.setattr(
        RedisRunnerQueueStore,
        "get_all_queue_metrics",
        AsyncMock(
            return_value={
                "status": "active",
                "global": {"pending": 1, "processing": 0, "delayed": 0, "deadletter": 0},
                "packs": {"browser_local": {"pending": 1, "processing": 0, "delayed": 0, "deadletter": 0}},
            }
        ),
    )
    monkeypatch.setattr(
        TasksStore,
        "list_runner_heartbeats",
        lambda self, **_kwargs: [
            {
                "runner_id": "runner-browser-1",
                "profile_code": "browser_local",
                "hostname": "host-a",
                "inflight": 2,
                "heartbeat_at": "2026-03-27T10:00:00+00:00",
            }
        ],
    )

    response = client.get("/api/v1/system-settings/health/queue/metrics")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "active"
    assert data["packs"]["browser_local"]["pending"] == 1
    assert data["runners"] == [
        {
            "runner_id": "runner-browser-1",
            "profile_code": "browser_local",
            "hostname": "host-a",
            "inflight": 2,
            "heartbeat_at": "2026-03-27T10:00:00+00:00",
        }
    ]
