import asyncio
import importlib
from types import SimpleNamespace

import httpx
from fastapi import APIRouter, FastAPI, HTTPException


def _load_workspace_governance_module():
    return importlib.import_module("backend.app.routes.core.workspace_governance")


def _load_memory_routes_module():
    return importlib.import_module(
        "backend.app.routes.core.workspace_governance_core.memory_routes"
    )


class ASGIAsyncTestClient:
    def __init__(self, app):
        self.app = app
        self.base_url = "http://testserver"

    def request(self, method, url, **kwargs):
        async def _request():
            transport = httpx.ASGITransport(app=self.app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url=self.base_url,
            ) as client:
                return await client.request(method, url, **kwargs)

        return asyncio.run(_request())

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)


class StubPromotionService:
    def __init__(self):
        self.calls = []

    def verify_candidate(self, memory_item_id, *, reason="", idempotency_key=None):
        self.calls.append(
            (
                "verify",
                memory_item_id,
                {"reason": reason, "idempotency_key": idempotency_key},
            )
        )
        return {
            "run": SimpleNamespace(id="run-verify"),
            "memory_item": SimpleNamespace(
                id=memory_item_id,
                lifecycle_status="active",
                verification_status="verified",
            ),
            "noop": False,
        }

    def supersede_memory(
        self,
        memory_item_id,
        *,
        successor_memory_item_id=None,
        successor_title=None,
        successor_claim=None,
        successor_summary=None,
        reason="",
        idempotency_key=None,
    ):
        self.calls.append(
            (
                "supersede",
                memory_item_id,
                {
                    "successor_memory_item_id": successor_memory_item_id,
                    "successor_title": successor_title,
                    "successor_claim": successor_claim,
                    "successor_summary": successor_summary,
                    "reason": reason,
                    "idempotency_key": idempotency_key,
                },
            )
        )
        return {
            "run": SimpleNamespace(id="run-supersede"),
            "memory_item": SimpleNamespace(
                id=memory_item_id,
                lifecycle_status="superseded",
                verification_status="verified",
            ),
            "successor_memory_item": SimpleNamespace(id="mem-2"),
            "noop": False,
        }


def _build_client(monkeypatch, *, item):
    module = _load_workspace_governance_module()
    memory_routes = _load_memory_routes_module()
    promotion_service = StubPromotionService()

    async def _load_workspace_memory_item(workspace_id, memory_item_id):
        if item is None:
            raise HTTPException(status_code=404, detail="Memory item not found")
        if item.id != memory_item_id:
            raise HTTPException(status_code=404, detail="Memory item not found")
        if item.context_type != "workspace" or item.context_id != workspace_id:
            raise HTTPException(
                status_code=404,
                detail="Memory item not found in workspace",
            )
        return item

    monkeypatch.setattr(
        memory_routes,
        "_load_workspace_memory_item",
        _load_workspace_memory_item,
    )
    monkeypatch.setattr(
        memory_routes,
        "_get_memory_promotion_service",
        lambda: promotion_service,
    )

    app = FastAPI()
    workspace_router = APIRouter(prefix="/api/v1/workspaces")
    workspace_router.include_router(module.router)
    app.include_router(workspace_router)
    return ASGIAsyncTestClient(app), promotion_service


def test_workspace_memory_transition_verify_uses_public_facade(monkeypatch):
    item = SimpleNamespace(
        id="mem-1",
        context_type="workspace",
        context_id="ws-1",
    )
    client, promotion_service = _build_client(monkeypatch, item=item)

    response = client.post(
        "/api/v1/workspaces/ws-1/governance/memory/mem-1/transition",
        json={
            "action": "verify",
            "reason": "user confirmed",
            "idempotency_key": "idem-verify",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "workspace_id": "ws-1",
        "memory_item_id": "mem-1",
        "transition": "verify",
        "noop": False,
        "lifecycle_status": "active",
        "verification_status": "verified",
        "run_id": "run-verify",
        "successor_memory_item_id": None,
    }
    assert promotion_service.calls == [
        (
            "verify",
            "mem-1",
            {"reason": "user confirmed", "idempotency_key": "idem-verify"},
        )
    ]


def test_workspace_memory_transition_supersede_passes_successor_fields(monkeypatch):
    item = SimpleNamespace(
        id="mem-1",
        context_type="workspace",
        context_id="ws-1",
    )
    client, promotion_service = _build_client(monkeypatch, item=item)

    response = client.post(
        "/api/v1/workspaces/ws-1/governance/memory/mem-1/transition",
        json={
            "action": "supersede",
            "successor_title": "New",
            "successor_claim": "New claim",
            "successor_summary": "New summary",
            "reason": "stronger evidence",
            "idempotency_key": "idem-supersede",
        },
    )

    assert response.status_code == 200
    assert response.json()["successor_memory_item_id"] == "mem-2"
    assert promotion_service.calls == [
        (
            "supersede",
            "mem-1",
            {
                "successor_memory_item_id": None,
                "successor_title": "New",
                "successor_claim": "New claim",
                "successor_summary": "New summary",
                "reason": "stronger evidence",
                "idempotency_key": "idem-supersede",
            },
        )
    ]


def test_workspace_memory_transition_rejects_cross_workspace_memory(monkeypatch):
    item = SimpleNamespace(
        id="mem-1",
        context_type="workspace",
        context_id="ws-other",
    )
    client, promotion_service = _build_client(monkeypatch, item=item)

    response = client.post(
        "/api/v1/workspaces/ws-1/governance/memory/mem-1/transition",
        json={"action": "verify"},
    )

    assert response.status_code == 404
    assert promotion_service.calls == []
