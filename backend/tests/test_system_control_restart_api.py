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


def test_runner_drain_enable_writes_sentinel(monkeypatch, tmp_path):
    webhook = StubRestartWebhook(configured=True)
    client, system_control = _build_client(monkeypatch, webhook)
    sentinel_path = tmp_path / "drain_runner.json"
    monkeypatch.setattr(system_control, "_RUNNER_DRAIN_SENTINEL_PATH", sentinel_path)

    response = client.post(
        "/api/v1/system-settings/runner-drain",
        json={"enabled": True, "ttl_seconds": 900},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["enabled"] is True
    assert data["method"] == "runner_drain_sentinel"
    assert data["sentinel"]["ttl_seconds"] == 900
    assert sentinel_path.exists()


def test_runner_drain_disable_clears_sentinel(monkeypatch, tmp_path):
    webhook = StubRestartWebhook(configured=True)
    client, system_control = _build_client(monkeypatch, webhook)
    sentinel_path = tmp_path / "drain_runner.json"
    sentinel_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(system_control, "_RUNNER_DRAIN_SENTINEL_PATH", sentinel_path)

    response = client.post(
        "/api/v1/system-settings/runner-drain",
        json={"enabled": False},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["enabled"] is False
    assert data["method"] == "runner_drain_sentinel"
    assert sentinel_path.exists() is False


def test_queue_metrics_includes_active_runner_heartbeats(monkeypatch):
    webhook = StubRestartWebhook(configured=True)
    client, system_control = _build_client(monkeypatch, webhook)
    monkeypatch.setattr(
        system_control,
        "_get_runner_queue_metrics_payload",
        AsyncMock(
            return_value={
                "status": "active",
                "global": {"pending": 1, "processing": 0, "delayed": 0, "deadletter": 0},
                "packs": {"browser_local": {"pending": 1, "processing": 0, "delayed": 0, "deadletter": 0}},
            }
        ),
    )
    monkeypatch.setattr(
        system_control,
        "_get_runner_heartbeat_projection",
        AsyncMock(
            return_value=[
                {
                    "runner_id": "runner-browser-1",
                    "profile_code": "browser_local",
                    "hostname": "host-a",
                    "inflight": 2,
                    "heartbeat_at": "2026-03-27T10:00:00+00:00",
                }
            ]
        ),
    )
    monkeypatch.setattr(
        system_control,
        "_get_scene_generation_dispatch_health",
        AsyncMock(return_value={"enabled": False, "status": "disabled"}),
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
    assert data["scene_generation_dispatch"]["enabled"] is False
    assert data["scene_generation_dispatch"]["status"] == "disabled"


def test_queue_metrics_includes_scene_generation_dispatch_summary(monkeypatch):
    webhook = StubRestartWebhook(configured=True)
    client, system_control = _build_client(monkeypatch, webhook)
    monkeypatch.setattr(
        system_control,
        "_get_runner_queue_metrics_payload",
        AsyncMock(
            return_value={
                "status": "active",
                "global": {
                    "pending": 0,
                    "processing": 0,
                    "delayed": 0,
                    "deadletter": 0,
                },
                "packs": {},
            }
        ),
    )
    monkeypatch.setattr(
        system_control,
        "_get_runner_heartbeat_projection",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        system_control,
        "_get_scene_generation_dispatch_health",
        AsyncMock(
            return_value={
                "enabled": True,
                "status": "warning",
                "running": True,
                "provider_cooldowns_active": 1,
                "pending_total": 5,
                "ready_total": 3,
                "runnable_total": 2,
                "provider_cooldown_blocked_total": 1,
                "deferred_total": 2,
                "provider_cooldowns": [
                    {
                        "provider_code": "world_labs",
                        "cooldown_until": "2026-03-30T12:00:00+00:00",
                        "remaining_seconds": 45,
                    }
                ],
                "runnable_samples": [{"job_id": "sgj_ready"}],
                "provider_cooldown_blocked_samples": [{"job_id": "sgj_blocked"}],
                "deferred_samples": [{"job_id": "sgj_deferred"}],
                "attention_reasons": [
                    {
                        "code": "provider_cooldown_blocking_jobs",
                        "severity": "warning",
                        "message": "1 scene generation jobs are blocked by provider cooldown.",
                    }
                ],
                "recommended_actions": [
                    "Check scene generation provider credentials/configuration and clear cooldown after the provider is ready."
                ],
                "thresholds": {
                    "runnable_warn_threshold": 5,
                    "deferred_warn_threshold": 10,
                    "cooldown_blocked_warn_threshold": 1,
                },
                "timestamp": "2026-03-30T11:59:15+00:00",
            }
        ),
    )

    response = client.get("/api/v1/system-settings/health/queue/metrics")

    assert response.status_code == 200
    data = response.json()
    assert data["scene_generation_dispatch"] == {
        "enabled": True,
        "status": "warning",
        "running": True,
        "provider_cooldowns_active": 1,
        "pending_total": 5,
        "ready_total": 3,
        "runnable_total": 2,
        "provider_cooldown_blocked_total": 1,
        "deferred_total": 2,
        "provider_cooldowns": [
            {
                "provider_code": "world_labs",
                "cooldown_until": "2026-03-30T12:00:00+00:00",
                "remaining_seconds": 45,
            }
        ],
        "runnable_samples": [{"job_id": "sgj_ready"}],
        "provider_cooldown_blocked_samples": [{"job_id": "sgj_blocked"}],
        "deferred_samples": [{"job_id": "sgj_deferred"}],
        "attention_reasons": [
            {
                "code": "provider_cooldown_blocking_jobs",
                "severity": "warning",
                "message": "1 scene generation jobs are blocked by provider cooldown.",
            }
        ],
        "recommended_actions": [
            "Check scene generation provider credentials/configuration and clear cooldown after the provider is ready."
        ],
        "thresholds": {
            "runnable_warn_threshold": 5,
            "deferred_warn_threshold": 10,
            "cooldown_blocked_warn_threshold": 1,
        },
        "timestamp": "2026-03-30T11:59:15+00:00",
    }


def test_scene_generation_dispatch_summary_marks_error_when_not_running_with_pending_jobs(
    monkeypatch,
):
    webhook = StubRestartWebhook(configured=True)
    _client, system_control = _build_client(monkeypatch, webhook)

    summary = system_control._summarize_scene_generation_dispatch_status(
        {
            "running": False,
            "provider_cooldowns_active": 0,
            "pending_jobs": {
                "total_pending": 3,
                "samples": [],
            },
            "ready_pending": {
                "total_pending": 2,
                "samples": [],
            },
            "runnable_pending": {
                "total_pending": 2,
                "samples": [],
            },
            "provider_cooldown_blocked_pending": {
                "total_pending": 0,
                "samples": [],
            },
            "deferred_pending": {
                "total_pending": 1,
                "samples": [],
            },
            "provider_cooldowns": [],
            "timestamp": "2026-03-30T12:00:00+00:00",
        }
    )

    assert summary["status"] == "error"
    assert summary["attention_reasons"] == [
        {
            "code": "dispatch_not_running_with_pending_jobs",
            "severity": "error",
            "message": "Scene generation dispatch is not running while pending jobs exist.",
        }
    ]
    assert summary["recommended_actions"] == [
        "Restart local-core backend or verify performance_direction background services started successfully."
    ]


def test_scene_generation_dispatch_summary_marks_warning_when_schema_missing(
    monkeypatch,
):
    webhook = StubRestartWebhook(configured=True)
    _client, system_control = _build_client(monkeypatch, webhook)

    summary = system_control._summarize_scene_generation_dispatch_status(
        {
            "running": False,
            "schema_ready": False,
            "schema_status": "missing_table",
            "schema_table_name": "scene_generation_jobs",
            "provider_cooldowns_active": 0,
            "pending_jobs": {
                "total_pending": 0,
                "samples": [],
            },
            "ready_pending": {
                "total_pending": 0,
                "samples": [],
            },
            "runnable_pending": {
                "total_pending": 0,
                "samples": [],
            },
            "provider_cooldown_blocked_pending": {
                "total_pending": 0,
                "samples": [],
            },
            "deferred_pending": {
                "total_pending": 0,
                "samples": [],
            },
            "provider_cooldowns": [],
            "timestamp": "2026-03-30T12:00:00+00:00",
        }
    )

    assert summary["status"] == "warning"
    assert summary["schema_ready"] is False
    assert summary["attention_reasons"] == [
        {
            "code": "dispatch_schema_missing",
            "severity": "warning",
            "message": "Scene generation dispatch schema is unavailable (scene_generation_jobs).",
        }
    ]
    assert summary["recommended_actions"] == [
        "Run performance_direction scene generation migrations or disable the pack until the schema is installed."
    ]
