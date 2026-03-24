from pathlib import Path
import importlib.util
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _load_workspace_governance_module():
    module_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "routes"
        / "core"
        / "workspace_governance.py"
    )
    spec = importlib.util.spec_from_file_location(
        "workspace_governance_test_module", module_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
            ("verify", memory_item_id, {"reason": reason, "idempotency_key": idempotency_key})
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
):
    module = _load_workspace_governance_module()
    item_store = StubMemoryItemStore(item, items=items)
    version_store = StubMemoryVersionStore(versions)
    evidence_store = StubMemoryEvidenceLinkStore(evidence_links)
    edge_store = StubMemoryEdgeStore(edges)
    personal_knowledge_store = StubPersonalKnowledgeStore(knowledge_entries)
    goal_ledger_store = StubGoalLedgerStore(goal_entries)
    promotion_service = StubPromotionService()
    monkeypatch.setattr(module, "_get_memory_item_store", lambda: item_store)
    monkeypatch.setattr(module, "_get_memory_version_store", lambda: version_store)
    monkeypatch.setattr(module, "_get_memory_evidence_link_store", lambda: evidence_store)
    monkeypatch.setattr(module, "_get_memory_edge_store", lambda: edge_store)
    monkeypatch.setattr(
        module, "_get_personal_knowledge_store", lambda: personal_knowledge_store
    )
    monkeypatch.setattr(module, "_get_goal_ledger_store", lambda: goal_ledger_store)
    monkeypatch.setattr(module, "_get_memory_promotion_service", lambda: promotion_service)

    app = FastAPI()
    app.include_router(module.router)
    return TestClient(app), promotion_service, item_store


def test_workspace_memory_transition_verify_uses_workspace_scoped_memory(monkeypatch):
    item = SimpleNamespace(
        id="mem-1",
        context_type="workspace",
        context_id="ws-1",
    )
    client, promotion_service, _item_store = _build_client(monkeypatch, item=item)

    response = client.post(
        "/api/v1/workspaces/ws-1/governance/memory/mem-1/transition",
        json={"action": "verify", "reason": "confirmed by user"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["memory_item_id"] == "mem-1"
    assert data["transition"] == "verify"
    assert data["lifecycle_status"] == "active"
    assert data["verification_status"] == "verified"
    assert data["run_id"] == "run-1"
    assert promotion_service.calls == [
        ("verify", "mem-1", {"reason": "confirmed by user", "idempotency_key": None})
    ]


def test_workspace_memory_transition_rejects_cross_workspace_memory(monkeypatch):
    item = SimpleNamespace(
        id="mem-1",
        context_type="workspace",
        context_id="ws-other",
    )
    client, _promotion_service, _item_store = _build_client(monkeypatch, item=item)

    response = client.post(
        "/api/v1/workspaces/ws-1/governance/memory/mem-1/transition",
        json={"action": "verify"},
    )

    assert response.status_code == 404
    assert "workspace" in response.json()["detail"]


def test_workspace_memory_transition_supersede_passes_successor_fields(monkeypatch):
    item = SimpleNamespace(
        id="mem-1",
        context_type="workspace",
        context_id="ws-1",
    )
    client, promotion_service, _item_store = _build_client(monkeypatch, item=item)

    response = client.post(
        "/api/v1/workspaces/ws-1/governance/memory/mem-1/transition",
        json={
            "action": "supersede",
            "reason": "newer evidence",
            "successor_title": "Updated claim",
            "successor_claim": "Updated claim body",
            "successor_summary": "Updated summary",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["transition"] == "supersede"
    assert data["lifecycle_status"] == "superseded"
    assert data["successor_memory_item_id"] == "mem-2"
    assert promotion_service.calls == [
        (
            "supersede",
            "mem-1",
            {
                "successor_memory_item_id": None,
                "successor_title": "Updated claim",
                "successor_claim": "Updated claim body",
                "successor_summary": "Updated summary",
                "reason": "newer evidence",
                "idempotency_key": None,
            },
        )
    ]


def test_workspace_memory_list_returns_filtered_canonical_items(monkeypatch):
    candidate = SimpleNamespace(
        id="mem-1",
        kind="session_episode",
        layer="episodic",
        title="Candidate memory",
        claim="Initial claim",
        summary="Initial summary",
        lifecycle_status="candidate",
        verification_status="observed",
        salience=0.7,
        confidence=0.8,
        subject_type="meeting_session",
        subject_id="sess-1",
        supersedes_memory_id=None,
        observed_at="2026-03-25T00:00:00Z",
        last_confirmed_at=None,
        created_at="2026-03-25T00:00:00Z",
        updated_at="2026-03-25T00:00:00Z",
    )
    active = SimpleNamespace(
        id="mem-2",
        kind="principle",
        layer="core",
        title="Verified principle",
        claim="Prefer explicit tradeoffs",
        summary="Use direct architectural tradeoffs",
        lifecycle_status="active",
        verification_status="verified",
        salience=0.9,
        confidence=0.95,
        subject_type="workspace_rule",
        subject_id="rule-1",
        supersedes_memory_id=None,
        observed_at="2026-03-25T01:00:00Z",
        last_confirmed_at="2026-03-25T01:30:00Z",
        created_at="2026-03-25T01:00:00Z",
        updated_at="2026-03-25T01:30:00Z",
    )
    client, _promotion_service, item_store = _build_client(
        monkeypatch,
        item=None,
        items=[candidate, active],
    )

    response = client.get(
        "/api/v1/workspaces/ws-1/governance/memory",
        params=[
            ("lifecycle_status", "active"),
            ("verification_status", "verified"),
            ("limit", "10"),
        ],
    )

    assert response.status_code == 200
    data = response.json()
    assert data["workspace_id"] == "ws-1"
    assert data["total"] == 1
    assert data["items"][0]["id"] == "mem-2"
    assert data["items"][0]["lifecycle_status"] == "active"
    assert data["items"][0]["verification_status"] == "verified"
    assert item_store.list_calls == [
        {
            "context_type": "workspace",
            "context_id": "ws-1",
            "layer": None,
            "kind": None,
            "lifecycle_statuses": ["active"],
            "verification_statuses": ["verified"],
            "limit": 10,
        }
    ]


def test_workspace_memory_detail_returns_versions_evidence_and_projections(monkeypatch):
    item = SimpleNamespace(
        id="mem-1",
        context_type="workspace",
        context_id="ws-1",
        kind="session_episode",
        layer="episodic",
        title="Candidate memory",
        claim="Initial claim",
        summary="Initial summary",
        lifecycle_status="active",
        verification_status="verified",
        salience=0.7,
        confidence=0.8,
        subject_type="meeting_session",
        subject_id="sess-1",
        supersedes_memory_id="mem-0",
        observed_at="2026-03-25T00:00:00Z",
        last_confirmed_at="2026-03-25T00:30:00Z",
        created_at="2026-03-25T00:00:00Z",
        updated_at="2026-03-25T00:30:00Z",
    )
    version = SimpleNamespace(
        id="ver-1",
        memory_item_id="mem-1",
        version_no=1,
        update_mode="append",
        claim_snapshot="Initial claim",
        summary_snapshot="Initial summary",
        metadata_snapshot={"digest_id": "dig-1"},
        created_at="2026-03-25T00:00:00Z",
        created_from_run_id="run-1",
    )
    evidence = SimpleNamespace(
        id="evi-1",
        memory_item_id="mem-1",
        evidence_type="session_digest",
        evidence_id="dig-1",
        link_role="derived_from",
        excerpt="Digest excerpt",
        confidence=0.9,
        metadata={"source_id": "sess-1"},
        created_at="2026-03-25T00:00:01Z",
    )
    edge = SimpleNamespace(
        id="edge-1",
        from_memory_id="mem-1",
        to_memory_id="mem-2",
        edge_type="supersedes",
        weight=None,
        valid_from="2026-03-25T01:00:00Z",
        valid_to=None,
        evidence_strength=1.0,
        metadata={"reason": "newer evidence"},
        created_at="2026-03-25T01:00:00Z",
    )
    knowledge = SimpleNamespace(
        id="pk-1",
        knowledge_type="principle",
        content="Prefer explicit tradeoffs",
        status="verified",
        confidence=0.92,
        created_at="2026-03-25T00:01:00Z",
        last_verified_at="2026-03-25T00:30:00Z",
        metadata={"canonical_projection": {"source_memory_item_id": "mem-1"}},
    )
    goal = SimpleNamespace(
        id="goal-1",
        title="Finish phase 1",
        description="Close the loop",
        status="active",
        horizon="quarter",
        created_at="2026-03-25T00:02:00Z",
        confirmed_at="2026-03-25T00:30:00Z",
        metadata={"canonical_projection": {"source_memory_item_id": "mem-1"}},
    )
    client, _promotion_service, _item_store = _build_client(
        monkeypatch,
        item=item,
        versions=[version],
        evidence_links=[evidence],
        edges=[edge],
        knowledge_entries=[knowledge],
        goal_entries=[goal],
    )

    response = client.get("/api/v1/workspaces/ws-1/governance/memory/mem-1")

    assert response.status_code == 200
    data = response.json()
    assert data["workspace_id"] == "ws-1"
    assert data["memory_item"]["id"] == "mem-1"
    assert data["memory_item"]["supersedes_memory_id"] == "mem-0"
    assert data["versions"][0]["id"] == "ver-1"
    assert data["versions"][0]["metadata_snapshot"]["digest_id"] == "dig-1"
    assert data["evidence"][0]["id"] == "evi-1"
    assert data["evidence"][0]["link_role"] == "derived_from"
    assert data["outgoing_edges"][0]["id"] == "edge-1"
    assert data["outgoing_edges"][0]["edge_type"] == "supersedes"
    assert data["personal_knowledge_projections"][0]["id"] == "pk-1"
    assert data["goal_projections"][0]["id"] == "goal-1"
