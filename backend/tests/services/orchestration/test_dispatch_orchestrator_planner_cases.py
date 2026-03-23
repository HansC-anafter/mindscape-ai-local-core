from dataclasses import dataclass, field
from typing import List, Optional

from backend.app.services.orchestration.dispatch_orchestrator_core.planner import (
    build_ir_provenance,
    derive_research_context,
    extract_playbook_code,
    looks_like_ig_work,
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
    agenda: List[str] = field(default_factory=list)


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
