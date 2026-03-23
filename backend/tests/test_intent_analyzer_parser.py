from types import SimpleNamespace

from backend.app.services.playbook.intent_analyzer_core import (
    ToolRelevanceResult,
    format_candidate_tools,
    format_tool_list,
    parse_llm_response,
)


def test_format_candidate_tools_includes_reasoning_and_scores():
    formatted = format_candidate_tools(
        [
            ToolRelevanceResult(
                tool_slot="workspace.read",
                relevance_score=0.92,
                reasoning="Read the current file before taking action.",
            )
        ]
    )

    assert "1. workspace.read" in formatted
    assert "Previous relevance: 0.92" in formatted
    assert "Previous reasoning:" in formatted


def test_format_tool_list_includes_policy_tags_and_mapping():
    tools = [
        SimpleNamespace(
            slot="tool.low",
            priority=1,
            description="Low priority",
            mapped_tool_description=None,
            policy=None,
            tags=[],
            mapped_tool_id=None,
        ),
        SimpleNamespace(
            slot="tool.high",
            priority=9,
            description=None,
            mapped_tool_description="Mapped description",
            policy=SimpleNamespace(risk_level="write", env="local"),
            tags=["fs", "write"],
            mapped_tool_id="filesystem_write_file",
        ),
    ]

    formatted = format_tool_list(tools)

    assert formatted.index("1. tool.high") < formatted.index("2. tool.low")
    assert "Mapped description (risk: write, env: local) [tags: fs, write]" in formatted
    assert "Mapped to: filesystem_write_file" in formatted


def test_parse_llm_response_truncates_to_three_tools():
    response = """
    {
      "relevant_tools": [
        {"tool_slot": "a", "relevance_score": 0.9, "confidence": 0.7},
        {"tool_slot": "b", "relevance_score": 0.8, "confidence": 0.6},
        {"tool_slot": "c", "relevance_score": 0.7, "confidence": 0.5},
        {"tool_slot": "d", "relevance_score": 0.6, "confidence": 0.4}
      ],
      "overall_reasoning": "Top tools selected",
      "needs_confirmation": true,
      "confidence": 0.88
    }
    """

    parsed = parse_llm_response(response)

    assert [tool.tool_slot for tool in parsed.relevant_tools] == ["a", "b", "c"]
    assert parsed.needs_confirmation is True
    assert parsed.confidence == 0.88


def test_parse_llm_response_returns_empty_when_json_missing():
    parsed = parse_llm_response("no json here")

    assert parsed.relevant_tools == []
    assert parsed.confidence == 0.0
