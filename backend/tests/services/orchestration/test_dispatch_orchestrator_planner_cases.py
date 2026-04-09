from dataclasses import dataclass, field
from typing import List, Optional

from backend.app.services.orchestration.dispatch_orchestrator_core.planner import (
    build_ir_provenance,
    derive_research_context,
    extract_playbook_code,
    looks_like_ig_work,
    normalize_action_item_inputs,
    normalize_phase_inputs,
)


@dataclass
class FakePhaseIR:
    id: str
    name: str
    description: str = ""
    preferred_engine: Optional[str] = None
    target_workspace_id: Optional[str] = None
    tool_name: Optional[str] = None
    input_params: Optional[dict] = None
    depends_on: Optional[List[str]] = None
    rationale: Optional[str] = None
    priority: Optional[int] = None


@dataclass
class FakeSession:
    id: str = "session-1"
    workspace_id: str = "ws-default"
    lens_id: Optional[str] = None
    agenda: List[str] = field(default_factory=list)
    success_criteria: List[str] = field(default_factory=list)


def test_normalize_phase_inputs_hydrates_article_draft_from_dependencies():
    phases = [
        FakePhaseIR(
            id="fetch",
            name="Fetch",
            tool_name="frontier_research.fetch_academic",
            input_params={"query": "autonomic nervous system", "max_results": 3},
        ),
        FakePhaseIR(
            id="draft",
            name="Generate IG Post Drafts",
            preferred_engine="playbook:article_draft",
            depends_on=["fetch"],
            input_params={"post_count": 3},
        ),
    ]
    action_items = [{"title": "Fetch"}, {"title": "Generate IG Post Drafts"}]

    normalize_phase_inputs(
        phases=phases,
        action_items=action_items,
        session=FakeSession(workspace_id="ws-yoga"),
    )

    assert phases[1].input_params["topic"] == "autonomic nervous system"
    assert phases[1].input_params["workspace_id"] == "ws-yoga"
    assert phases[1].input_params["target_format"] == "ig_caption"
    assert action_items[1]["input_params"]["language"] == "zh-TW"


def test_derive_research_context_falls_back_to_session_agenda():
    phase = FakePhaseIR(
        id="process",
        name="Process",
        tool_name="frontier_research.process_papers_pipeline",
        input_params={},
    )

    query, max_results = derive_research_context(
        phase=phase,
        phase_map={phase.id: phase},
        session=FakeSession(agenda=["neuroplasticity in trauma recovery"]),
    )

    assert query == "neuroplasticity in trauma recovery"
    assert max_results is None


def test_build_ir_provenance_uses_action_item_dependency_fallback():
    phase = FakePhaseIR(
        id="phase-1",
        name="Generate scene preview",
        tool_name="video_renderer.render_local_preview",
        rationale="Need a visual draft",
        priority=2,
    )

    provenance = build_ir_provenance(
        phase=phase,
        action_item={"blocked_by": ["scene-0"], "priority": 9},
        engine="tool:video_renderer.render_local_preview",
        session=FakeSession(id="meeting-1"),
    )

    assert provenance["dependencies"] == ["scene-0"]
    assert provenance["meeting_session_id"] == "meeting-1"
    assert provenance["priority"] == 2


def test_extract_playbook_code_and_ig_detection_helpers():
    assert extract_playbook_code("playbook:generic") == "generic"
    assert extract_playbook_code("tool:video_renderer.render_local_preview") is None
    assert looks_like_ig_work("Generate Instagram caption drafts") is True
    assert looks_like_ig_work("Generate long-form research memo") is False


def test_normalize_phase_inputs_hydrates_longtask_playbook_chain():
    phases = [
        FakePhaseIR(
            id="mi",
            name="MI Brand Identity",
            preferred_engine="playbook:cis_mind_identity",
            input_params={},
        ),
        FakePhaseIR(
            id="bi",
            name="BI Behavior Identity",
            preferred_engine="playbook:cis_behavior_identity",
            depends_on=["mi"],
            input_params={},
        ),
        FakePhaseIR(
            id="week1",
            name="Week1 Feed Factory",
            preferred_engine="playbook:week1_feed_factory",
            depends_on=["bi"],
            input_params={},
        ),
        FakePhaseIR(
            id="ig",
            name="IG Post Generation",
            preferred_engine="playbook:ig_post_generation",
            depends_on=["week1"],
            input_params={"post_count": 5},
        ),
    ]
    action_items = [{"title": phase.name} for phase in phases]

    normalize_phase_inputs(
        phases=phases,
        action_items=action_items,
        session=FakeSession(
            workspace_id="ws-longtask",
            lens_id="lens-123",
            agenda=["90 集劇本：轉生成為瓜子", "角色設定與分鏡設計"],
            success_criteria=["輸出角色設定", "輸出第一週內容排程"],
        ),
    )

    assert phases[0].input_params["workspace_id"] == "ws-longtask"
    assert phases[0].input_params["document_type"] == "brief"
    assert "轉生成為瓜子" in phases[0].input_params["document_content"]

    assert phases[1].input_params["workspace_id"] == "ws-longtask"
    assert "角色設定" in phases[1].input_params["brand_context"]

    assert phases[2].input_params["lens_id"] == "lens-123"
    assert phases[2].input_params["topic_materials"]["lens_id"] == "lens-123"
    assert "轉生成為瓜子" in phases[2].input_params["topic_materials"]["brief"]

    assert phases[3].input_params["workspace_id"] == "ws-longtask"
    assert phases[3].input_params["post_count"] == 5
    assert "第一週內容排程" in phases[3].input_params["source_content"]
    assert action_items[3]["input_params"]["source_content"] == phases[3].input_params["source_content"]


def test_normalize_action_item_inputs_hydrates_longtask_policy_gate_payload():
    action_items = [
        {
            "intent_id": "mi",
            "title": "MI Brand Identity",
            "playbook_code": "cis_mind_identity",
            "input_params": {},
        },
        {
            "intent_id": "week1",
            "title": "Week1 Feed Factory",
            "playbook_code": "week1_feed_factory",
            "blocked_by": ["mi"],
            "input_params": {},
        },
        {
            "intent_id": "ig",
            "title": "IG Post Generation",
            "playbook_code": "ig_post_generation",
            "blocked_by": ["week1"],
            "input_params": {},
        },
    ]

    normalize_action_item_inputs(
        action_items=action_items,
        session=FakeSession(
            workspace_id="ws-longtask",
            lens_id="lens-123",
            agenda=["90 集劇本：轉生成為瓜子", "角色設定與分鏡設計"],
            success_criteria=["輸出角色設定", "輸出第一週內容排程"],
        ),
    )

    assert action_items[0]["input_params"]["document_type"] == "brief"
    assert "轉生成為瓜子" in action_items[0]["input_params"]["document_content"]
    assert action_items[1]["input_params"]["lens_id"] == "lens-123"
    assert action_items[1]["input_params"]["topic_materials"]["lens_id"] == "lens-123"
    assert "第一週內容排程" in action_items[2]["input_params"]["source_content"]
