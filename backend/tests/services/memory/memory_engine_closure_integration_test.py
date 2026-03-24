from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from backend.app.models.personal_governance.goal_ledger import GoalLedgerEntry
from backend.app.models.personal_governance.personal_knowledge import (
    KnowledgeStatus,
    PersonalKnowledge,
)
from backend.app.routes.core.workspace_governance import router as workspace_governance_router
from backend.app.services.governance.governance_context_read_model import (
    GovernanceContextReadModel,
)
from backend.app.services.memory.writeback.meeting_memory_writeback_orchestrator import (
    MeetingMemoryWritebackOrchestrator,
)
from backend.app.services.stores.postgres.goal_ledger_store import GoalLedgerStore
from backend.app.services.stores.postgres.memory_item_store import MemoryItemStore
from backend.app.services.stores.postgres.personal_knowledge_store import (
    PersonalKnowledgeStore,
)


def _utc_now():
    return datetime.now(timezone.utc)


def _integration_ready() -> bool:
    return bool(os.getenv("DATABASE_URL") or os.getenv("DATABASE_URL_CORE"))


@dataclass
class _FakeSession:
    id: str
    workspace_id: str
    project_id: str | None
    started_at: datetime = field(default_factory=_utc_now)
    ended_at: datetime = field(default_factory=_utc_now)
    action_items: list = field(
        default_factory=lambda: [
            {
                "title": "Ship memory engine phase 1",
                "description": "Close writeback and governance loop",
            }
        ]
    )
    decisions: list = field(default_factory=lambda: ["prefer_closed_loop"])
    minutes_md: str = (
        "We aligned on closing the memory loop first, keeping promotion deterministic, "
        "and using governance context to decide what stays visible in future sessions."
    )


class _DeterministicLegacyGovernanceAdapter:
    def __init__(self):
        self.pk_store = PersonalKnowledgeStore()
        self.gl_store = GoalLedgerStore()

    def dispatch_digest_projection(
        self,
        digest,
        meta_session_id,
        *,
        source_memory_item_id,
        source_writeback_run_id,
        projection_stage="legacy_governance_v1",
    ):
        canonical_projection = {
            "source_memory_item_id": source_memory_item_id,
            "source_writeback_run_id": source_writeback_run_id,
            "projection_stage": projection_stage,
            "source_digest_id": digest.id,
        }
        knowledge = PersonalKnowledge(
            owner_profile_id=digest.owner_profile_id,
            knowledge_type="principle",
            content="Prefer direct architectural tradeoffs.",
            status=KnowledgeStatus.CANDIDATE.value,
            confidence=0.91,
            source_evidence=[{"digest_id": digest.id, "source_type": digest.source_type}],
            source_workspace_ids=list(digest.workspace_refs or []),
            metadata={"canonical_projection": canonical_projection},
        )
        self.pk_store.create(knowledge)

        goal = GoalLedgerEntry(
            owner_profile_id=digest.owner_profile_id,
            title="Finish memory engine phase 1",
            description="Close canonical writeback, promotion, and packet routing.",
            status="pending_confirmation",
            horizon="quarter",
            source_digest_ids=[digest.id],
            metadata={"canonical_projection": canonical_projection},
        )
        self.gl_store.create(goal)


class _NoopMetadataProjectionAdapter:
    def dispatch_digest_projection(
        self,
        digest,
        *,
        source_memory_item_id,
        source_writeback_run_id,
        projection_stage="legacy_metadata_memory_v1",
    ):
        return None


class _FakeWorkspaceCoreMemoryService:
    async def get_core_memory(self, workspace_id):
        return SimpleNamespace(
            brand_identity={"name": "Mindscape"},
            voice_and_tone={"tone": "precise"},
            style_constraints=["inspectable", "direct"],
            important_milestones=[],
            learnings=["Keep the memory spine deterministic."],
        )


class _NullProjectMemoryService:
    async def get_project_memory(self, project_id, workspace_id):
        return None


class _NullMemberProfileMemoryService:
    async def get_member_memory(self, profile_id, workspace_id):
        return None


def _cleanup_memory_closure_entities(
    *,
    workspace_id: str,
    owner_profile_id: str,
    session_id: str,
):
    item_store = MemoryItemStore()
    with item_store.transaction() as conn:
        conn.execute(
            text(
                """
                DELETE FROM memory_writeback_runs
                WHERE source_id = :session_id
                   OR source_id IN (
                       SELECT id FROM memory_items
                       WHERE context_type = 'workspace' AND context_id = :workspace_id
                   )
                """
            ),
            {
                "workspace_id": workspace_id,
                "session_id": session_id,
            },
        )
        conn.execute(
            text("DELETE FROM memory_edges WHERE from_memory_id IN (SELECT id FROM memory_items WHERE context_id = :workspace_id) OR to_memory_id IN (SELECT id FROM memory_items WHERE context_id = :workspace_id)"),
            {"workspace_id": workspace_id},
        )
        conn.execute(
            text("DELETE FROM memory_evidence_links WHERE memory_item_id IN (SELECT id FROM memory_items WHERE context_id = :workspace_id)"),
            {"workspace_id": workspace_id},
        )
        conn.execute(
            text("DELETE FROM memory_versions WHERE memory_item_id IN (SELECT id FROM memory_items WHERE context_id = :workspace_id)"),
            {"workspace_id": workspace_id},
        )
        conn.execute(
            text("DELETE FROM memory_items WHERE context_type = 'workspace' AND context_id = :workspace_id"),
            {"workspace_id": workspace_id},
        )
        conn.execute(
            text("DELETE FROM session_digests WHERE source_type = 'meeting' AND source_id = :session_id"),
            {"session_id": session_id},
        )
        conn.execute(
            text("DELETE FROM personal_knowledge WHERE owner_profile_id = :owner_profile_id"),
            {"owner_profile_id": owner_profile_id},
        )
        conn.execute(
            text("DELETE FROM goal_ledger WHERE owner_profile_id = :owner_profile_id"),
            {"owner_profile_id": owner_profile_id},
        )


@pytest.mark.integration
@pytest.mark.skipif(not _integration_ready(), reason="PostgreSQL integration environment is not configured")
def test_meeting_writeback_verify_changes_governance_packet():
    suffix = uuid4().hex[:8]
    workspace_id = f"ws-memory-closure-{suffix}"
    profile_id = f"profile-memory-closure-{suffix}"
    session_id = f"sess-memory-closure-{suffix}"

    orchestrator = MeetingMemoryWritebackOrchestrator(
        legacy_projection_adapter=_DeterministicLegacyGovernanceAdapter(),
        metadata_projection_adapter=_NoopMetadataProjectionAdapter(),
    )
    session = _FakeSession(
        id=session_id,
        workspace_id=workspace_id,
        project_id=None,
    )
    workspace = SimpleNamespace(
        id=workspace_id,
        owner_user_id=profile_id,
        primary_project_id=None,
        mode="planning",
        execution_mode="hybrid",
        runtime_profile=SimpleNamespace(metadata={"memory_scope": "extended"}),
        sandbox_config={},
        metadata={"mind_lens": {"label": "Memory integration lens"}},
    )

    app = FastAPI()
    app.include_router(workspace_governance_router)
    client = TestClient(app)

    read_model = GovernanceContextReadModel(
        store=SimpleNamespace(),
        workspace_core_memory_service=_FakeWorkspaceCoreMemoryService(),
        project_memory_service=_NullProjectMemoryService(),
        member_profile_memory_service=_NullMemberProfileMemoryService(),
        personal_knowledge_store=PersonalKnowledgeStore(),
        goal_ledger_store=GoalLedgerStore(),
        memory_item_store=MemoryItemStore(),
    )

    try:
        writeback_result = orchestrator.run_for_closed_session(
            session=session,
            workspace=workspace,
            profile_id=profile_id,
        )
        memory_item = writeback_result["memory_item"]
        assert memory_item.context_id == workspace_id

        before_packet = asyncio.run(read_model.build_for_workspace(workspace))
        assert before_packet is not None
        assert before_packet["memory_packet"]["layers"]["knowledge"]["verified"] == []
        assert len(before_packet["memory_packet"]["layers"]["knowledge"]["candidates"]) == 1
        assert before_packet["memory_packet"]["layers"]["goals"]["active"] == []
        assert len(before_packet["memory_packet"]["layers"]["goals"]["pending"]) == 1
        assert len(before_packet["memory_packet"]["layers"]["episodic"]) == 1

        response = client.post(
            f"/api/v1/workspaces/{workspace_id}/governance/memory/{memory_item.id}/transition",
            json={"action": "verify", "reason": "integration confirmation"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["memory_item_id"] == memory_item.id
        assert data["transition"] == "verify"
        assert data["lifecycle_status"] == "active"
        assert data["verification_status"] == "verified"

        after_packet = asyncio.run(read_model.build_for_workspace(workspace))
        assert after_packet is not None
        assert len(after_packet["memory_packet"]["layers"]["knowledge"]["verified"]) == 1
        assert after_packet["memory_packet"]["layers"]["knowledge"]["candidates"] == []
        assert len(after_packet["memory_packet"]["layers"]["goals"]["active"]) == 1
        assert after_packet["memory_packet"]["layers"]["goals"]["pending"] == []
        assert len(after_packet["memory_packet"]["layers"]["episodic"]) == 1

        pk_store = PersonalKnowledgeStore()
        gl_store = GoalLedgerStore()
        knowledge_entries = pk_store.list_by_canonical_memory_item(memory_item.id)
        goal_entries = gl_store.list_by_canonical_memory_item(memory_item.id)
        assert len(knowledge_entries) == 1
        assert knowledge_entries[0].status == KnowledgeStatus.VERIFIED.value
        assert len(goal_entries) == 1
        assert goal_entries[0].status == "active"
    finally:
        _cleanup_memory_closure_entities(
            workspace_id=workspace_id,
            owner_profile_id=profile_id,
            session_id=session_id,
        )
