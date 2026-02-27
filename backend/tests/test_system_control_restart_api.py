from pathlib import Path
import importlib.util

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


def _build_client(monkeypatch, webhook: StubRestartWebhook) -> TestClient:
    system_control = _load_system_control_module()
    monkeypatch.setattr(
        system_control,
        "get_restart_webhook_service",
        lambda: webhook,
    )
    app = FastAPI()
    app.include_router(system_control.router, prefix="/api/v1/system-settings")
    return TestClient(app)


def test_restart_valid_service_runner(monkeypatch):
    webhook = StubRestartWebhook(
        configured=True,
        responses={"runner": {"sent": True, "service": "runner"}},
    )
    client = _build_client(monkeypatch, webhook)

    response = client.post(
        "/api/v1/system-settings/restart",
        json={"service": "runner"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["method"] == "device_node"
    assert data["targets"] == ["runner"]
    assert len(webhook.calls) == 1
    assert webhook.calls[0]["service"] == "runner"


def test_restart_invalid_service_rejected(monkeypatch):
    webhook = StubRestartWebhook(configured=True)
    client = _build_client(monkeypatch, webhook)

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
            "runner": {
                "sent": False,
                "reason": "device_node_unreachable",
                "service": "runner",
            }
        },
    )
    client = _build_client(monkeypatch, webhook)

    response = client.post(
        "/api/v1/system-settings/restart",
        json={"service": "runner"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert data["method"] == "manual"
    assert data["targets"] == ["runner"]
    assert data["instruction"] == "docker compose restart runner"
