from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.app.services.playbook import intent_analyzer as intent_module
from backend.app.services.playbook.intent_analyzer import (
    IntentAnalysisResult,
    IntentAnalyzer,
    ToolSlotIntentAnalyzer,
    get_intent_analyzer,
    get_tool_slot_intent_analyzer,
)
from backend.app.services.playbook.intent_analyzer_core import (
    ToolRelevanceResult,
    ToolSlotAnalysisResult,
)
from backend.app.services.playbook.intent_analyzer_core.escalation import (
    should_escalate_for_intent,
)
from backend.app.services.playbook.intent_analyzer_core.prompting import (
    build_tool_relevance_prompt,
)
from backend.app.services.playbook.intent_analyzer_core.ranking import (
    sort_and_filter_tools,
)


def _tool(slot: str, priority: int):
    return SimpleNamespace(
        slot=slot,
        priority=priority,
        description=f"Description for {slot}",
        mapped_tool_description=None,
        mapped_tool_id=None,
        policy=None,
        tags=[],
        relevance_score=None,
    )


def test_legacy_public_facade_names_remain_importable() -> None:
    analyzer = ToolSlotIntentAnalyzer(profile_id="profile-1")

    assert IntentAnalyzer is ToolSlotIntentAnalyzer
    assert IntentAnalysisResult is ToolSlotAnalysisResult
    assert isinstance(analyzer, ToolSlotIntentAnalyzer)
    assert isinstance(get_tool_slot_intent_analyzer(), ToolSlotIntentAnalyzer)

    with pytest.warns(DeprecationWarning):
        assert isinstance(get_intent_analyzer(), ToolSlotIntentAnalyzer)


def test_ranking_preserves_priority_sort_and_fallback_fill() -> None:
    tools = [
        _tool("tool.low", 1),
        _tool("tool.alpha", 20),
        _tool("tool.beta", 5),
        _tool("tool.gamma", 10),
    ]
    results = [
        ToolRelevanceResult("tool.beta", 0.95),
        ToolRelevanceResult("tool.gamma", 0.85),
        ToolRelevanceResult("tool.low", 0.1),
    ]

    ranked = sort_and_filter_tools(
        relevance_results=results,
        min_relevance=0.3,
        max_tools=5,
        available_tools=tools,
    )

    assert [tool.slot for tool in ranked] == ["tool.gamma", "tool.beta", "tool.alpha"]
    assert ranked[0].relevance_score == 0.85
    assert ranked[1].relevance_score == 0.95


def test_rule_escalation_decisions_are_preserved() -> None:
    many_candidates = ToolSlotAnalysisResult(
        relevant_tools=[
            ToolRelevanceResult(f"tool.{index}", 0.9) for index in range(16)
        ],
        confidence=0.9,
    )
    low_confidence = ToolSlotAnalysisResult(
        relevant_tools=[ToolRelevanceResult("tool.alpha", 0.4)],
        confidence=0.4,
    )
    clear_read = ToolSlotAnalysisResult(
        relevant_tools=[ToolRelevanceResult("tool.alpha", 0.9)],
        confidence=0.9,
    )

    assert should_escalate_for_intent(
        recall_result=many_candidates,
        risk_level="read",
        user_message="inspect the current workspace style",
        use_utility=False,
    )[0]
    assert should_escalate_for_intent(
        recall_result=clear_read,
        risk_level="write",
        user_message="update the selected workspace copy",
        use_utility=False,
    )[0]
    assert should_escalate_for_intent(
        recall_result=low_confidence,
        risk_level="read",
        user_message="inspect the current workspace style",
        use_utility=False,
    )[0]
    assert should_escalate_for_intent(
        recall_result=clear_read,
        risk_level="read",
        user_message="what now",
        use_utility=False,
    )[0]
    assert not should_escalate_for_intent(
        recall_result=clear_read,
        risk_level="read",
        user_message="inspect the current workspace style",
        use_utility=False,
    )[0]


def test_prompt_helper_preserves_recall_and_precision_shapes() -> None:
    recall_prompt = build_tool_relevance_prompt(
        user_message="read the current footer styles",
        available_tools=[_tool("tool.alpha", 10)],
        conversation_history=[{"role": "user", "content": "please read the footer"}],
        emphasis="recall",
        max_tools=25,
    )
    precision_prompt = build_tool_relevance_prompt(
        user_message="read the current footer styles",
        available_tools=[_tool("tool.alpha", 10)],
        candidate_tools=[ToolRelevanceResult("tool.alpha", 0.8, "matches")],
        emphasis="precision",
        max_tools=10,
    )

    assert "Selection Strategy (RECALL FOCUS)" in recall_prompt.prompt
    assert "Stage: Analysis/Reading phase" in recall_prompt.prompt
    assert "Analyze all 1 available tools" in recall_prompt.prompt
    assert "Selection Strategy (PRECISION FOCUS)" in precision_prompt.prompt
    assert "Focus on these 1 pre-filtered candidates" in precision_prompt.prompt
    assert "Previous relevance: 0.80" in precision_prompt.prompt


@pytest.mark.asyncio
async def test_fast_recall_threads_risk_level_to_model_and_llm(monkeypatch) -> None:
    analyzer = ToolSlotIntentAnalyzer(profile_id="profile-1")
    observed = {}

    def _fake_resolve(**kwargs):
        observed["resolve_risk_level"] = kwargs["risk_level"]
        return SimpleNamespace(), "model-for-risk"

    async def _fake_llm(**kwargs):
        observed["llm_risk_level"] = kwargs["risk_level"]
        return ToolSlotAnalysisResult(
            relevant_tools=[ToolRelevanceResult("tool.alpha", 0.8)]
        )

    monkeypatch.setattr(intent_module, "resolve_intent_stage_model", _fake_resolve)
    monkeypatch.setattr(analyzer, "_llm_analyze_relevance_with_model", _fake_llm)

    result = await analyzer._fast_recall(
        user_message="publish the final result",
        available_tools=[_tool("tool.alpha", 10)],
        risk_level="publish",
    )

    assert observed == {
        "resolve_risk_level": "publish",
        "llm_risk_level": "publish",
    }
    assert result.confidence == 0.8


def test_helper_modules_do_not_define_duplicate_resource_surfaces() -> None:
    root = Path("backend/app/services/playbook/intent_analyzer_core")
    helper_files = [
        root / "escalation.py",
        root / "model_routing.py",
        root / "prompting.py",
        root / "ranking.py",
        root / "trace.py",
    ]
    forbidden_markers = [
        "class ToolSlotIntentAnalyzer",
        "def get_tool_slot_intent_analyzer",
        "core_llm_call",
        "get_trace_recorder",
        "APIRouter",
        "@router",
        "create_engine",
        "sessionmaker",
        "PgBouncer",
        "asyncio.create_task",
        "setInterval",
    ]

    for helper_file in helper_files:
        source = helper_file.read_text(encoding="utf-8")
        for marker in forbidden_markers:
            assert marker not in source, f"{marker} found in {helper_file}"
