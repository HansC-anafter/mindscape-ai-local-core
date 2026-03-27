from pathlib import Path
import asyncio
import importlib.util
from types import SimpleNamespace
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, FastAPI


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
    module = _load_workspace_governance_module()
    item_store = StubMemoryItemStore(item, items=items)
    version_store = StubMemoryVersionStore(versions)
    evidence_store = StubMemoryEvidenceLinkStore(evidence_links)
    edge_store = StubMemoryEdgeStore(edges)
    personal_knowledge_store = StubPersonalKnowledgeStore(knowledge_entries)
    goal_ledger_store = StubGoalLedgerStore(goal_entries)
    promotion_service = StubPromotionService()
    meeting_session_store = StubMeetingSessionStore(meeting_sessions)
    monkeypatch.setattr(module, "_get_memory_item_store", lambda: item_store)
    monkeypatch.setattr(module, "_get_memory_version_store", lambda: version_store)
    monkeypatch.setattr(module, "_get_memory_evidence_link_store", lambda: evidence_store)
    monkeypatch.setattr(module, "_get_memory_edge_store", lambda: edge_store)
    monkeypatch.setattr(
        module, "_get_personal_knowledge_store", lambda: personal_knowledge_store
    )
    monkeypatch.setattr(module, "_get_goal_ledger_store", lambda: goal_ledger_store)
    monkeypatch.setattr(module, "_get_memory_promotion_service", lambda: promotion_service)
    monkeypatch.setattr(module, "_get_meeting_session_store", lambda: meeting_session_store)

    app = FastAPI()
    workspace_router = APIRouter(prefix="/api/v1/workspaces")
    workspace_router.include_router(module.router)
    app.include_router(workspace_router)
    return ASGIAsyncTestClient(app), promotion_service, item_store, meeting_session_store


def test_workspace_memory_transition_verify_uses_workspace_scoped_memory(monkeypatch):
    item = SimpleNamespace(
        id="mem-1",
        context_type="workspace",
        context_id="ws-1",
    )
    client, promotion_service, _item_store, _meeting_session_store = _build_client(monkeypatch, item=item)

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
    client, _promotion_service, _item_store, _meeting_session_store = _build_client(monkeypatch, item=item)

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
    client, promotion_service, _item_store, _meeting_session_store = _build_client(monkeypatch, item=item)

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
    client, _promotion_service, item_store, _meeting_session_store = _build_client(
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


def test_workspace_memory_detail_returns_versions_evidence_and_projections(
    monkeypatch, tmp_path
):
    artifact_dir = tmp_path / "artifacts" / "exec-001"
    artifact_dir.mkdir(parents=True)
    result_json_path = artifact_dir / "result.json"
    summary_md_path = artifact_dir / "summary.md"
    attachment_path = artifact_dir / "attachments" / "artifact.txt"
    attachment_path.parent.mkdir(parents=True)
    result_json_path.write_text('{"status":"ok"}', encoding="utf-8")
    summary_md_path.write_text("# Summary", encoding="utf-8")
    attachment_path.write_text("artifact body", encoding="utf-8")

    trace_dir = tmp_path / ".mindscape" / "traces"
    trace_dir.mkdir(parents=True)
    trace_file_path = trace_dir / "trace-exec-001.json"
    trace_file_path.write_text('{"execution_id":"trace-exec-001"}', encoding="utf-8")

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
    decision_evidence = SimpleNamespace(
        id="evi-2",
        memory_item_id="mem-1",
        evidence_type="meeting_decision",
        evidence_id="decision-1",
        link_role="supports",
        excerpt="Adopt the revised delivery standard.",
        confidence=0.95,
        metadata={"category": "action"},
        created_at="2026-03-25T00:00:02Z",
    )
    artifact_evidence = SimpleNamespace(
        id="evi-3",
        memory_item_id="mem-1",
        evidence_type="artifact_result",
        evidence_id="artifact-1",
        link_role="supports",
        excerpt="Updated artifact reflects the revised delivery standard.",
        confidence=0.96,
        metadata={
            "artifact_type": "draft",
            "landing_artifact_dir": str(artifact_dir),
            "landing_result_json_path": str(result_json_path),
            "landing_summary_md_path": str(summary_md_path),
            "landing_attachments_count": 1,
            "landing_attachments": [str(attachment_path)],
            "landing_landed_at": "2026-03-25T00:00:03Z",
        },
        created_at="2026-03-25T00:00:03Z",
    )
    trace_evidence = SimpleNamespace(
        id="evi-4",
        memory_item_id="mem-1",
        evidence_type="execution_trace",
        evidence_id="trace-exec-001",
        link_role="supports",
        excerpt="Produced a concise landing-page outline and updated the draft files.",
        confidence=0.88,
        metadata={
            "trace_source": "trace_file",
            "trace_file_path": str(trace_file_path),
            "sandbox_path": str(tmp_path),
            "tool_call_count": 2,
            "file_change_count": 2,
            "files_created_count": 1,
            "files_modified_count": 1,
            "success": True,
            "duration_seconds": 12.5,
            "task_description": "Generate a concise landing-page outline.",
            "output_summary": "Produced a concise landing-page outline and updated the draft files.",
        },
        created_at="2026-03-25T00:00:03Z",
    )
    receipt_evidence = SimpleNamespace(
        id="evi-5",
        memory_item_id="mem-1",
        evidence_type="writeback_receipt",
        evidence_id="receipt-1",
        link_role="derived_from",
        excerpt="Projection receipt",
        confidence=1.0,
        metadata={"target_table": "personal_knowledge"},
        created_at="2026-03-25T00:00:04Z",
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
    client, _promotion_service, _item_store, _meeting_session_store = _build_client(
        monkeypatch,
        item=item,
        versions=[version],
        evidence_links=[
            evidence,
            decision_evidence,
            artifact_evidence,
            trace_evidence,
            receipt_evidence,
        ],
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
    assert data["evidence_coverage"] == {
        "deliberation": 2,
        "execution": 2,
        "governance": 1,
        "support": 3,
        "derived": 2,
    }
    assert data["evidence"][2]["artifact_landing"] == {
        "artifact_dir": str(artifact_dir),
        "result_json_path": str(result_json_path),
        "summary_md_path": str(summary_md_path),
        "attachments_count": 1,
        "attachments": [str(attachment_path)],
        "landed_at": "2026-03-25T00:00:03Z",
        "artifact_dir_exists": True,
        "result_json_exists": True,
        "summary_md_exists": True,
    }
    assert data["evidence"][3]["execution_trace_drilldown"] == {
        "trace_source": "trace_file",
        "trace_file_path": str(trace_file_path),
        "trace_file_exists": True,
        "sandbox_path": str(tmp_path),
        "tool_call_count": 2,
        "file_change_count": 2,
        "files_created_count": 1,
        "files_modified_count": 1,
        "success": True,
        "duration_seconds": 12.5,
        "task_description": "Generate a concise landing-page outline.",
        "output_summary": "Produced a concise landing-page outline and updated the draft files.",
    }
    assert data["transition_cues"][0]["id"] == "stale-usage"
    assert any(cue["id"] == "supersede-usage" for cue in data["transition_cues"])
    assert data["successor_draft_suggestion"] == {
        "title": "Candidate memory Revision",
        "claim": "Updated artifact reflects the revised delivery standard.",
        "summary": "Successor drafted from artifact result. Coverage: 2 deliberation, 2 execution, 1 governance. Anchor evidence: artifact-1.",
        "primary_evidence_id": "artifact-1",
        "primary_evidence_type": "artifact_result",
    }
    assert (
        data["transition_reason_suggestions"]["verify"]
        == "Verified after reviewing Artifact Result artifact-1 with 2 deliberation signals and 3 downstream execution or governance signals."
    )
    assert (
        data["transition_reason_suggestions"]["stale"]
        == "Marked stale because the active workspace context moved beyond this claim and no replacement was finalized from Artifact Result artifact-1."
    )
    assert (
        data["transition_reason_suggestions"]["supersede"]
        == "Superseded after Artifact Result artifact-1 established a newer operating claim for Candidate memory."
    )


def test_workspace_memory_health_aggregates_recent_workflow_evidence(monkeypatch):
    base_time = datetime(2026, 3, 26, 8, 0, tzinfo=timezone.utc)
    sessions = [
        SimpleNamespace(
            id="sess-3",
            workspace_id="ws-1",
            project_id="proj-1",
            thread_id="thread-1",
            meeting_type="decision",
            started_at=base_time,
            ended_at=None,
            metadata={
                "workflow_evidence_diagnostics": {
                    "profile": "decision",
                    "scope": "thread",
                    "selected_line_count": 8,
                    "total_line_budget": 8,
                    "total_candidate_count": 12,
                    "total_dropped_count": 4,
                    "rendered_section_count": 4,
                    "budget_utilization_ratio": 1.0,
                }
            },
        ),
        SimpleNamespace(
            id="sess-2",
            workspace_id="ws-1",
            project_id="proj-1",
            thread_id="thread-1",
            meeting_type="review",
            started_at=base_time.replace(hour=7),
            ended_at=None,
            metadata={
                "workflow_evidence_diagnostics": {
                    "profile": "review",
                    "scope": "thread",
                    "selected_line_count": 2,
                    "total_line_budget": 8,
                    "total_candidate_count": 5,
                    "total_dropped_count": 0,
                    "rendered_section_count": 2,
                    "budget_utilization_ratio": 0.25,
                }
            },
        ),
        SimpleNamespace(
            id="sess-1",
            workspace_id="ws-1",
            project_id="proj-1",
            thread_id="thread-1",
            meeting_type="reflection",
            started_at=base_time.replace(hour=6),
            ended_at=None,
            metadata={
                "workflow_evidence_diagnostics": {
                    "profile": "reflection",
                    "scope": "project",
                    "selected_line_count": 0,
                    "total_line_budget": 8,
                    "total_candidate_count": 0,
                    "total_dropped_count": 0,
                    "rendered_section_count": 0,
                    "budget_utilization_ratio": 0.0,
                }
            },
        ),
    ]
    client, _promotion_service, _item_store, meeting_session_store = _build_client(
        monkeypatch,
        item=None,
        meeting_sessions=sessions,
    )

    response = client.get(
        "/api/v1/workspaces/ws-1/governance/memory-health",
        params={"thread_id": "thread-1", "limit": 3},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["workspace_id"] == "ws-1"
    assert data["thread_id"] == "thread-1"
    assert data["sampled_sessions"] == 3
    assert data["tight_count"] == 1
    assert data["underused_count"] == 1
    assert data["empty_count"] == 1
    assert data["balanced_count"] == 0
    assert data["latest"]["session_id"] == "sess-3"
    assert data["latest"]["classification"] == "tight"
    assert data["average_utilization_ratio"] == 0.417
    assert data["average_selected_line_count"] == 3.33
    assert data["average_total_dropped_count"] == 1.33
    assert [session["session_id"] for session in data["sessions"]] == [
        "sess-3",
        "sess-2",
        "sess-1",
    ]
    assert meeting_session_store.calls == [
        {
            "workspace_id": "ws-1",
            "project_id": None,
            "limit": 9,
            "offset": 0,
        }
    ]
