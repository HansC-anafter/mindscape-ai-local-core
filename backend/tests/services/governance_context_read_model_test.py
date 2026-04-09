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
from backend.app.services import capability_registry
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


@pytest.mark.asyncio
async def test_governance_context_read_model_includes_world_memory_sidecars(
    monkeypatch,
):
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

    def _fake_export_context(self, **kwargs):
        assert kwargs["workspace_id"] == "ws-1"
        return {
            "world_memory_packet": {
                "workspace_id": "ws-1",
                "snapshot_id": "snap-1",
                "source": "synthetic",
                "scene_id": "scene.demo",
                "current_zone": "main_floor",
            },
            "world_card_projection": {
                "title": "World Card",
                "summary_lines": ["Scene: scene.demo", "Zone: main_floor"],
                "constraints": [],
                "suggested_focus": [],
                "metadata": {"source": "synthetic"},
            },
            "world_card_text": "World Card\n- Scene: scene.demo\n- Zone: main_floor",
        }

    monkeypatch.setattr(
        "backend.app.system_capabilities.world_memory_core.services.context_export_facade.ContextExportFacade.export_context",
        _fake_export_context,
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

    assert packet["world_memory_packet"]["scene_id"] == "scene.demo"
    assert packet["world_card_projection"]["summary_lines"][1] == "Zone: main_floor"
    assert "Zone: main_floor" in packet["world_card_text"]


@pytest.mark.asyncio
async def test_governance_context_read_model_builds_geo_context_via_installed_capability(
    monkeypatch,
):
    workspace = SimpleNamespace(
        id="ws-1",
        owner_user_id="profile-1",
        primary_project_id="proj-1",
        mode="research",
        execution_mode="hybrid",
        runtime_profile=SimpleNamespace(metadata={"memory_scope": "extended"}),
        sandbox_config={"tool_policies": {"network": "restricted"}},
        metadata={
            "mind_lens": {"label": "Research editor"},
            "google_geo_seed": {
                "geocode_result": {
                    "lat": 25.033,
                    "lng": 121.565,
                    "formatted_address": "Taipei 101",
                    "place_id": "place-101",
                },
                "place_context": {
                    "place_id": "place-101",
                    "name": "Taipei 101",
                    "formatted_address": "Taipei City",
                    "types": ["point_of_interest"],
                },
                "route_context": {
                    "mode": "walking",
                    "distance_meters": 800,
                    "duration_seconds": 600,
                    "origin_label": "hotel",
                    "destination_label": "taipei101",
                },
            },
        },
    )

    class _FakeRegistry:
        def get_capability(self, capability_code):
            if capability_code == "google_geo_layer":
                return {"manifest": {"code": capability_code}}
            return None

        def get_tool(self, tool_name):
            if tool_name == "google_geo_layer.ggl_bind_dual_world_context":
                return {"name": tool_name}
            return None

    async def _fake_call_tool_async(capability, tool, **kwargs):
        if capability == "google_geo_layer":
            assert tool == "ggl_bind_dual_world_context"
            assert kwargs["geocode_result"]["place_id"] == "place-101"
            return {
                "geo_anchor": {
                    "provider": "google_maps_platform",
                    "lat": 25.033,
                    "lng": 121.565,
                    "place_id": "place-101",
                    "formatted_address": "Taipei 101",
                },
                "venue_context": {
                    "provider": "google_maps_platform",
                    "place_id": "place-101",
                    "name": "Taipei 101",
                    "formatted_address": "Taipei City",
                    "types": ["point_of_interest"],
                },
                "route_context": {
                    "provider": "google_maps_platform",
                    "mode": "walking",
                    "distance_meters": 800,
                    "duration_seconds": 600,
                },
                "streetview_context": None,
            }

    def _fake_export_context(self, **kwargs):
        assert kwargs["geo_context"]["venue_context"]["name"] == "Taipei 101"
        return {
            "world_memory_packet": {
                "workspace_id": "ws-1",
                "snapshot_id": "snap-geo",
                "source": "synthetic",
                "scene_id": "scene.demo",
                "current_zone": "main_floor",
                "geo_anchor": kwargs["geo_context"]["geo_anchor"],
                "venue_context": kwargs["geo_context"]["venue_context"],
                "route_context": kwargs["geo_context"]["route_context"],
            },
            "world_card_projection": {
                "title": "World Card",
                "summary_lines": [
                    "Scene: scene.demo",
                    "Venue: Taipei 101",
                    "Route: walking 800m / 600s",
                ],
                "constraints": [],
                "suggested_focus": [],
                "metadata": {"source": "synthetic"},
            },
            "world_card_text": "World Card\n- Venue: Taipei 101",
        }

    monkeypatch.setattr(capability_registry, "get_registry", lambda: _FakeRegistry())
    monkeypatch.setattr(capability_registry, "call_tool_async", _fake_call_tool_async)
    monkeypatch.setattr(
        "backend.app.system_capabilities.world_memory_core.services.context_export_facade.ContextExportFacade.export_context",
        _fake_export_context,
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

    assert packet["world_memory_packet"]["geo_anchor"]["place_id"] == "place-101"
    assert packet["world_card_projection"]["summary_lines"][1] == "Venue: Taipei 101"
    assert "Taipei 101" in packet["world_card_text"]


@pytest.mark.asyncio
async def test_governance_context_read_model_forwards_provider_neutral_motion_context(
    monkeypatch,
):
    workspace = SimpleNamespace(
        id="ws-1",
        owner_user_id="profile-1",
        primary_project_id="proj-1",
        mode="research",
        execution_mode="hybrid",
        runtime_profile=SimpleNamespace(metadata={"memory_scope": "extended"}),
        sandbox_config={"tool_policies": {"network": "restricted"}},
        metadata={
            "mind_lens": {"label": "Research editor"},
            "motion_context": {
                "motion_id": "motion_demo",
                "provider": "comfyui_kimodo",
                "status": "completed",
                "duration_sec": 4.0,
                "fps": 30,
                "skeleton_family": "soma",
                "skeleton_version": "77j_v1",
                "coordinate_space": "y_up",
                "artifact_refs": [
                    {
                        "artifact_kind": "preview",
                        "format": "mp4",
                        "storage_key": "motion/demo/preview.mp4",
                    }
                ],
                "motion_constraints": {"timing_policy": {"fps": 30}},
            },
        },
    )

    def _fake_export_context(self, **kwargs):
        assert kwargs["motion_context"]["motion_id"] == "motion_demo"
        assert kwargs["motion_context"]["artifact_refs"][0]["artifact_kind"] == "preview"
        return {
            "world_memory_packet": {
                "workspace_id": "ws-1",
                "snapshot_id": "snap-motion",
                "source": "synthetic",
                "scene_id": "scene.demo",
                "current_zone": "main_floor",
                "active_motion": kwargs["motion_context"]["active_motion"]
                if "active_motion" in kwargs["motion_context"]
                else {
                    "motion_id": kwargs["motion_context"]["motion_id"],
                    "provider": kwargs["motion_context"]["provider"],
                },
                "motion_artifact_refs": kwargs["motion_context"]["artifact_refs"],
                "motion_constraints": kwargs["motion_context"]["motion_constraints"],
            },
            "world_card_projection": {
                "title": "World Card",
                "summary_lines": ["Scene: scene.demo", "Active motion: motion_demo"],
                "constraints": ["motion_timing_policy={'fps': 30}"],
                "suggested_focus": [],
                "metadata": {"source": "synthetic"},
            },
            "world_card_text": "World Card\n- Active motion: motion_demo",
        }

    monkeypatch.setattr(
        "backend.app.system_capabilities.world_memory_core.services.context_export_facade.ContextExportFacade.export_context",
        _fake_export_context,
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

    assert packet["world_memory_packet"]["active_motion"]["motion_id"] == "motion_demo"
    assert (
        packet["world_memory_packet"]["motion_artifact_refs"][0]["artifact_kind"]
        == "preview"
    )
    assert "Active motion: motion_demo" in packet["world_card_text"]


@pytest.mark.asyncio
async def test_governance_context_read_model_degrades_when_world_memory_export_raises(
    monkeypatch,
):
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

    def _boom(self, **kwargs):
        raise RuntimeError("export failed")

    monkeypatch.setattr(
        "backend.app.system_capabilities.world_memory_core.services.context_export_facade.ContextExportFacade.export_context",
        _boom,
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

    assert "world_memory_packet" not in packet
    assert "world_card_projection" not in packet
    assert "world_card_text" not in packet
