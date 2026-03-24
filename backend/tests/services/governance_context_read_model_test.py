from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from backend.app.models.memory_contract import MemoryItem
from backend.app.models.personal_governance.goal_ledger import GoalLedgerEntry
from backend.app.models.personal_governance.personal_knowledge import (
    KnowledgeStatus,
    PersonalKnowledge,
)
from backend.app.services.governance.governance_context_read_model import (
    GovernanceContextReadModel,
)


def _utc_now():
    return datetime.now(timezone.utc)


@dataclass
class _FakeCoreMemory:
    brand_identity: dict = field(default_factory=lambda: {"name": "Mindscape"})
    voice_and_tone: dict = field(default_factory=lambda: {"tone": "calm"})
    style_constraints: list = field(default_factory=lambda: ["precise"])
    important_milestones: list = field(default_factory=list)
    learnings: list = field(default_factory=lambda: ["prefer direct tradeoffs"])


@dataclass
class _FakeDecision:
    decision: str
    rationale: str


@dataclass
class _FakeProjectMemory:
    project_id: str = "proj-1"
    decision_history: list = field(
        default_factory=lambda: [_FakeDecision("Ship phase 1", "Need closed-loop memory first")]
    )
    key_conversations: list = field(default_factory=lambda: ["Scope query router after writeback"])
    artifact_index: list = field(default_factory=list)


@dataclass
class _FakeMemberMemory:
    user_id: str = "profile-1"
    skills: list = field(default_factory=lambda: ["research", "editing"])
    preferences: dict = field(default_factory=lambda: {"tone": "precise"})
    learnings: list = field(default_factory=lambda: ["surface tradeoffs early"])


class _FakeWorkspaceCoreMemoryService:
    async def get_core_memory(self, workspace_id):
        assert workspace_id == "ws-1"
        return _FakeCoreMemory()


class _FakeProjectMemoryService:
    async def get_project_memory(self, project_id, workspace_id):
        assert project_id == "proj-1"
        assert workspace_id == "ws-1"
        return _FakeProjectMemory()


class _FakeMemberProfileMemoryService:
    async def get_member_memory(self, profile_id, workspace_id):
        assert profile_id == "profile-1"
        assert workspace_id == "ws-1"
        return _FakeMemberMemory()


class _FakePersonalKnowledgeStore:
    def list_by_owner(self, owner_profile_id, limit=20):
        assert owner_profile_id == "profile-1"
        return [
            PersonalKnowledge(
                id="pk-verified",
                owner_profile_id=owner_profile_id,
                knowledge_type="principle",
                content="Bias toward inspectable reasoning.",
                status=KnowledgeStatus.VERIFIED.value,
                confidence=0.92,
            ),
            PersonalKnowledge(
                id="pk-candidate",
                owner_profile_id=owner_profile_id,
                knowledge_type="preference",
                content="May prefer shorter summaries.",
                status=KnowledgeStatus.CANDIDATE.value,
                confidence=0.61,
            ),
            PersonalKnowledge(
                id="pk-stale",
                owner_profile_id=owner_profile_id,
                knowledge_type="pattern",
                content="Older stale pattern should not be injected.",
                status=KnowledgeStatus.STALE.value,
                confidence=0.5,
            ),
            PersonalKnowledge(
                id="pk-deprecated",
                owner_profile_id=owner_profile_id,
                knowledge_type="principle",
                content="Deprecated guidance should stay out of the packet.",
                status=KnowledgeStatus.DEPRECATED.value,
                confidence=0.3,
            ),
        ]


class _FakeGoalLedgerStore:
    def list_by_owner(self, owner_profile_id, limit=12):
        assert owner_profile_id == "profile-1"
        return [
            GoalLedgerEntry(
                id="goal-1",
                owner_profile_id=owner_profile_id,
                title="Finish memory engine phase 1",
                description="Complete canonical packet and writeback loop",
                status="active",
                horizon="quarter",
            ),
            GoalLedgerEntry(
                id="goal-pending",
                owner_profile_id=owner_profile_id,
                title="Revisit merge semantics",
                description="Pending confirmation",
                status="pending_confirmation",
                horizon="quarter",
            ),
            GoalLedgerEntry(
                id="goal-stale",
                owner_profile_id=owner_profile_id,
                title="Old stale goal",
                description="Should not re-enter pending packet",
                status="stale",
                horizon="quarter",
            ),
            GoalLedgerEntry(
                id="goal-achieved",
                owner_profile_id=owner_profile_id,
                title="Already done",
                description="Should not show as pending",
                status="achieved",
                horizon="quarter",
            ),
        ]


class _FakeMemoryItemStore:
    def list_for_context(self, **kwargs):
        assert kwargs["context_type"] == "workspace"
        assert kwargs["context_id"] == "ws-1"
        return [
            MemoryItem(
                id="mem-1",
                title="Meeting episode 1",
                summary="Chose canonical memory substrate before query routing.",
                claim="Chose canonical memory substrate before query routing.",
                salience=0.95,
                context_type="workspace",
                context_id="ws-1",
                subject_type="meeting_session",
                subject_id="sess-1",
            ),
            MemoryItem(
                id="mem-2",
                title="Meeting episode 2",
                summary="Deferred merge lifecycle until later rollout.",
                claim="Deferred merge lifecycle until later rollout.",
                salience=0.72,
                context_type="workspace",
                context_id="ws-1",
                subject_type="meeting_session",
                subject_id="sess-2",
            ),
            MemoryItem(
                id="mem-stale",
                title="Meeting episode stale",
                summary="A stale episode should not be included in the active packet.",
                claim="A stale episode should not be included in the active packet.",
                salience=0.99,
                context_type="workspace",
                context_id="ws-1",
                subject_type="meeting_session",
                subject_id="sess-3",
                lifecycle_status="stale",
            ),
        ]


@pytest.mark.asyncio
async def test_governance_context_read_model_compiles_selected_packet():
    workspace = SimpleNamespace(
        id="ws-1",
        owner_user_id="profile-1",
        primary_project_id="proj-1",
        mode="research",
        execution_mode="hybrid",
        runtime_profile=SimpleNamespace(metadata={"memory_scope": "extended"}),
        sandbox_config={"tool_policies": {"network": "restricted"}},
        metadata={"mind_lens": {"label": "Research editor"}},
    )

    read_model = GovernanceContextReadModel(
        store=SimpleNamespace(),
        workspace_core_memory_service=_FakeWorkspaceCoreMemoryService(),
        project_memory_service=_FakeProjectMemoryService(),
        member_profile_memory_service=_FakeMemberProfileMemoryService(),
        personal_knowledge_store=_FakePersonalKnowledgeStore(),
        goal_ledger_store=_FakeGoalLedgerStore(),
        memory_item_store=_FakeMemoryItemStore(),
    )

    packet = await read_model.build_for_workspace(workspace)

    assert packet is not None
    assert packet["governance_context"]["mode"] == "research"
    assert packet["governance_context"]["policy"]["memory_scope"] == "extended"
    assert packet["memory_packet"]["selection"]["episodic_limit"] == 7
    assert len(packet["memory_packet"]["layers"]["knowledge"]["verified"]) == 1
    assert len(packet["memory_packet"]["layers"]["knowledge"]["candidates"]) == 1
    assert len(packet["memory_packet"]["layers"]["goals"]["active"]) == 1
    assert len(packet["memory_packet"]["layers"]["goals"]["pending"]) == 1
    assert len(packet["memory_packet"]["layers"]["episodic"]) == 2
    assert packet["memory_packet"]["layers"]["project"]["project_id"] == "proj-1"

    formatted = read_model.format_memory_packet_for_context(packet)
    assert "Guiding knowledge:" in formatted
    assert "Active goals:" in formatted
    assert "Pending goals:" in formatted
    assert "Recent episodes:" in formatted
    assert "Older stale pattern should not be injected." not in formatted
    assert "Deprecated guidance should stay out of the packet." not in formatted
    assert "Old stale goal" not in formatted
    assert "Already done" not in formatted
    assert "stale episode should not be included" not in formatted.lower()
