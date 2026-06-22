from fastapi.testclient import TestClient

from backend.app.routes.core import host_resources

from .host_resources_api_test_support import build_app


def test_runners_endpoint_returns_claim_controls(monkeypatch):
    async def _list_active_runner_resource_heartbeats(_redis_queue):
        return [
            {
                "runner_id": "runner-a",
                "profile_code": "browser_local",
                "queue_shards": ["browser_local"],
                "capacity": {"max_inflight": 3, "inflight": 1, "available_slots": 2},
            }
        ]

    async def _attach_runner_claim_controls(_redis_queue, heartbeats):
        return [
            {
                **heartbeats[0],
                "claim_control": {"mode": "active", "claim_enabled": True},
            }
        ]

    monkeypatch.setattr(
        host_resources,
        "list_active_runner_resource_heartbeats",
        _list_active_runner_resource_heartbeats,
    )
    monkeypatch.setattr(
        host_resources,
        "attach_runner_claim_controls",
        _attach_runner_claim_controls,
    )

    response = TestClient(build_app()).get("/api/v1/host-resources/runners")

    assert response.status_code == 200
    assert response.json()["count"] == 1
    runner = response.json()["runners"][0]
    assert runner["runner_id"] == "runner-a"
    assert runner["claim_control"]["mode"] == "active"


def test_runner_claim_mode_endpoint_updates_single_runner(monkeypatch):
    received = {}

    class _Control:
        def to_dict(self):
            return {
                "runner_id": "runner-a",
                "mode": "drain",
                "claim_enabled": False,
            }

    def _set_runner_claim_mode_sync(runner_id, mode, **kwargs):
        received["runner_id"] = runner_id
        received["mode"] = mode
        received.update(kwargs)
        return _Control()

    monkeypatch.setattr(
        host_resources,
        "set_runner_claim_mode_sync",
        _set_runner_claim_mode_sync,
    )

    response = TestClient(build_app()).put(
        "/api/v1/host-resources/runners/runner-a/claim-mode",
        json={"mode": "drain", "reason": "test", "ttl_seconds": 120},
    )

    assert response.status_code == 200
    assert response.json()["claim_control"]["mode"] == "drain"
    assert received["runner_id"] == "runner-a"
    assert received["mode"] == "drain"
    assert received["reason"] == "test"
    assert received["ttl_seconds"] == 120


def test_runner_spillover_status_endpoint_uses_control_service(monkeypatch):
    async def _runner_spillover_status():
        return {
            "accepted": True,
            "action": "status",
            "result": {"status": {"running": False}},
        }

    monkeypatch.setattr(
        host_resources,
        "runner_spillover_status",
        _runner_spillover_status,
    )

    response = TestClient(build_app()).get("/api/v1/host-resources/runner-spillover")

    assert response.status_code == 200
    assert response.json()["accepted"] is True
    assert response.json()["action"] == "status"
    assert response.json()["result"]["status"]["running"] is False


def test_runner_spillover_action_endpoint_uses_control_service(monkeypatch):
    received = {}

    async def _runner_spillover_action(payload):
        received.update(payload)
        return {
            "accepted": True,
            "action": payload["action"],
            "profile_code": payload["profile_code"],
        }

    monkeypatch.setattr(
        host_resources,
        "runner_spillover_action",
        _runner_spillover_action,
    )

    response = TestClient(build_app()).post(
        "/api/v1/host-resources/runner-spillover",
        json={
            "action": "start",
            "profile_code": "browser_local",
            "max_inflight": 1,
        },
    )

    assert response.status_code == 200
    assert response.json()["accepted"] is True
    assert response.json()["profile_code"] == "browser_local"
    assert received == {
        "action": "start",
        "profile_code": "browser_local",
        "max_inflight": 1,
    }
