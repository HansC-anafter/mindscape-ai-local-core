import asyncio
import importlib
from types import SimpleNamespace

import httpx
from fastapi import APIRouter, FastAPI


def _load_workspace_governance_modules():
    return (
        importlib.import_module("backend.app.routes.core.workspace_governance"),
        importlib.import_module("backend.app.routes.core.workspace_governance_core.memory_routes"),
        importlib.import_module("backend.app.routes.core.workspace_governance_core.stores"),
    )


class StubMemoryItemStore:
    def __init__(self, item, *, items=None):
        self.item = item
        self.items = list(items or [])
        self.list_calls = []

    def get(self, memory_item_id):
        if self.item and self.item.id == memory_item_id:
            return self.item
        return None

    def list_for_context(
        self,
        *,
        context_type,
        context_id,
        layer=None,
        kind=None,
        lifecycle_statuses=None,
        verification_statuses=None,
        limit=20,
    ):
        self.list_calls.append(
            {
                "context_type": context_type,
                "context_id": context_id,
                "layer": layer,
                "kind": kind,
                "lifecycle_statuses": lifecycle_statuses,
                "verification_statuses": verification_statuses,
                "limit": limit,
            }
        )
        results = list(self.items)
        if kind:
            results = [item for item in results if item.kind == kind]
        if layer:
            results = [item for item in results if item.layer == layer]
        if lifecycle_statuses:
            results = [
                item for item in results if item.lifecycle_status in lifecycle_statuses
            ]
        if verification_statuses:
            results = [
                item
                for item in results
                if item.verification_status in verification_statuses
            ]
        return results[:limit]


class StubMemoryVersionStore:
    def __init__(self, versions=None):
        self.versions = list(versions or [])

    def list_by_memory_item(self, memory_item_id):
        return [
            version
            for version in self.versions
            if version.memory_item_id == memory_item_id
        ]


class StubMemoryEvidenceLinkStore:
    def __init__(self, links=None):
        self.links = list(links or [])

    def list_by_memory_item(self, memory_item_id):
        return [link for link in self.links if link.memory_item_id == memory_item_id]


class StubMemoryEdgeStore:
    def __init__(self, edges=None):
        self.edges = list(edges or [])

    def list_from_memory(self, memory_item_id):
        return [edge for edge in self.edges if edge.from_memory_id == memory_item_id]


class StubPersonalKnowledgeStore:
    def __init__(self, entries=None):
        self.entries = list(entries or [])

    def list_by_canonical_memory_item(self, source_memory_item_id):
        return [
            entry
            for entry in self.entries
            if (entry.metadata or {}).get("canonical_projection", {}).get(
                "source_memory_item_id"
            )
            == source_memory_item_id
        ]


class StubGoalLedgerStore:
    def __init__(self, entries=None):
        self.entries = list(entries or [])

    def list_by_canonical_memory_item(self, source_memory_item_id):
        return [
            entry
            for entry in self.entries
            if (entry.metadata or {}).get("canonical_projection", {}).get(
                "source_memory_item_id"
            )
            == source_memory_item_id
        ]


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
            "run": SimpleNamespace(id="run-1"),
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
            "run": SimpleNamespace(id="run-2"),
            "memory_item": SimpleNamespace(
                id=memory_item_id,
                lifecycle_status="superseded",
                verification_status="verified",
            ),
            "successor_memory_item": SimpleNamespace(id="mem-2"),
            "noop": False,
        }


class StubMeetingSessionStore:
    def __init__(self, sessions=None):
        self.sessions = list(sessions or [])
        self.calls = []

    def list_by_workspace(self, workspace_id, project_id=None, limit=50, offset=0):
        self.calls.append(
            {
                "workspace_id": workspace_id,
                "project_id": project_id,
                "limit": limit,
                "offset": offset,
            }
        )
        sessions = [
            session
            for session in self.sessions
            if session.workspace_id == workspace_id
            and (project_id is None or session.project_id == project_id)
        ]
        return sessions[offset : offset + limit]


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

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)


def _build_client(
    monkeypatch,
    *,
    item,
    items=None,
    versions=None,
    evidence_links=None,
    edges=None,
    knowledge_entries=None,
    goal_entries=None,
    meeting_sessions=None,
):
    module, memory_routes, stores = _load_workspace_governance_modules()
    item_store = StubMemoryItemStore(item, items=items)
    version_store = StubMemoryVersionStore(versions)
    evidence_store = StubMemoryEvidenceLinkStore(evidence_links)
    edge_store = StubMemoryEdgeStore(edges)
    personal_knowledge_store = StubPersonalKnowledgeStore(knowledge_entries)
    goal_ledger_store = StubGoalLedgerStore(goal_entries)
    promotion_service = StubPromotionService()
    meeting_session_store = StubMeetingSessionStore(meeting_sessions)
    provider_targets = (module, memory_routes, stores)
    for target in provider_targets:
        monkeypatch.setattr(target, "_get_memory_item_store", lambda: item_store)
        monkeypatch.setattr(target, "_get_memory_version_store", lambda: version_store)
        monkeypatch.setattr(
            target,
            "_get_memory_evidence_link_store",
            lambda: evidence_store,
        )
        monkeypatch.setattr(target, "_get_memory_edge_store", lambda: edge_store)
        monkeypatch.setattr(
            target,
            "_get_personal_knowledge_store",
            lambda: personal_knowledge_store,
        )
        monkeypatch.setattr(target, "_get_goal_ledger_store", lambda: goal_ledger_store)
        monkeypatch.setattr(
            target,
            "_get_memory_promotion_service",
            lambda: promotion_service,
        )
        monkeypatch.setattr(
            target,
            "_get_meeting_session_store",
            lambda: meeting_session_store,
        )

    app = FastAPI()
    workspace_router = APIRouter(prefix="/api/v1/workspaces")
    workspace_router.include_router(module.router)
    app.include_router(workspace_router)
    return ASGIAsyncTestClient(app), promotion_service, item_store, meeting_session_store
