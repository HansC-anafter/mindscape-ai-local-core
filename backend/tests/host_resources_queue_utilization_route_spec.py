from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.routes.core import host_resources


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(host_resources.router)
    return TestClient(app)


def test_queue_utilization_route_forwards_summary_view(monkeypatch):
    received = {}

    async def _response(**kwargs):
        received.update(kwargs)
        return {"view": "summary"}

    monkeypatch.setattr(host_resources, "build_queue_utilization_response", _response)

    response = _client().get("/api/v1/host-resources/queue-utilization?view=summary")

    assert response.status_code == 200
    assert response.json() == {"view": "summary"}
    assert received == {
        "live": False,
        "view": "summary",
        "queue_shard": None,
    }


def test_queue_utilization_route_forwards_detail_queue(monkeypatch):
    received = {}

    async def _response(**kwargs):
        received.update(kwargs)
        return {"view": "detail", "queue_shard": "browser_local"}

    monkeypatch.setattr(host_resources, "build_queue_utilization_response", _response)

    response = _client().get(
        "/api/v1/host-resources/queue-utilization"
        "?view=detail&queue_shard=browser_local"
    )

    assert response.status_code == 200
    assert response.json() == {"view": "detail", "queue_shard": "browser_local"}
    assert received == {
        "live": False,
        "view": "detail",
        "queue_shard": "browser_local",
    }


def test_queue_utilization_route_maps_unknown_detail_queue_to_404(monkeypatch):
    async def _response(**_kwargs):
        raise ValueError("queue_shard_not_found")

    monkeypatch.setattr(host_resources, "build_queue_utilization_response", _response)

    response = _client().get(
        "/api/v1/host-resources/queue-utilization"
        "?view=detail&queue_shard=missing"
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "queue_shard_not_found"}
