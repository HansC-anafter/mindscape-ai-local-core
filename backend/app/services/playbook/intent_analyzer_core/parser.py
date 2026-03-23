import json
import logging
import re
from typing import Any, List

from .schemas import ToolRelevanceResult, ToolSlotAnalysisResult

logger = logging.getLogger(__name__)


def format_candidate_tools(candidate_tools: List[ToolRelevanceResult]) -> str:
    """Format candidate tools for the precision-stage prompt."""
    lines = []
    for index, result in enumerate(candidate_tools, 1):
        lines.append(f"{index}. {result.tool_slot}")
        lines.append(f"   Previous relevance: {result.relevance_score:.2f}")
        if result.reasoning:
            lines.append(f"   Previous reasoning: {result.reasoning[:100]}")
        lines.append("")
    return "\n".join(lines)


def format_tool_list(tools: List[Any]) -> str:
    """Format tool list for LLM prompts with priority, policy, and tags."""
    lines = []
    sorted_tools = sorted(tools, key=lambda tool: tool.priority, reverse=True)

    for index, tool in enumerate(sorted_tools, 1):
        tool_desc = tool.description or tool.mapped_tool_description or tool.slot
        policy_info = ""
        if tool.policy:
            policy_info = f" (risk: {tool.policy.risk_level}, env: {tool.policy.env})"

        tags_info = ""
        if tool.tags:
            tags_info = f" [tags: {', '.join(tool.tags)}]"

        lines.append(f"{index}. {tool.slot} (priority: {tool.priority})")
        lines.append(f"   Description: {tool_desc}{policy_info}{tags_info}")
        if tool.mapped_tool_id:
            lines.append(f"   Mapped to: {tool.mapped_tool_id}")
        lines.append("")

    return "\n".join(lines)


def parse_llm_response(response: str) -> ToolSlotAnalysisResult:
    """Parse the JSON payload returned by the LLM relevance scorer."""
    try:
        json_match = re.search(
            r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}",
            response,
            re.DOTALL,
        )
        if not json_match:
            logger.warning("No JSON found in LLM response")
            return ToolSlotAnalysisResult(relevant_tools=[])

        data = json.loads(json_match.group(0))
        relevant_tools = [
            ToolRelevanceResult(
                tool_slot=tool_data.get("tool_slot", ""),
                relevance_score=float(tool_data.get("relevance_score", 0.0)),
                reasoning=tool_data.get("reasoning"),
                confidence=float(tool_data.get("confidence", 0.0)),
            )
            for tool_data in data.get("relevant_tools", [])
        ]

        if len(relevant_tools) > 3:
            logger.warning(
                "LLM returned %s tools, truncating to 3 per design requirement",
                len(relevant_tools),
            )
            relevant_tools = relevant_tools[:3]
        elif not relevant_tools:
            logger.warning("LLM returned no tools, this should not happen")

        needs_confirmation = data.get("needs_confirmation", False) or data.get(
            "needs_user_confirmation",
            False,
        )

        overall_confidence = data.get("confidence", 0.0)
        if isinstance(overall_confidence, (int, float)):
            confidence = float(overall_confidence)
        elif relevant_tools:
            confidences = [tool.confidence for tool in relevant_tools if tool.confidence > 0]
            confidence = sum(confidences) / len(confidences) if confidences else 0.0
        else:
            confidence = 0.0

        return ToolSlotAnalysisResult(
            relevant_tools=relevant_tools,
            overall_reasoning=data.get("overall_reasoning"),
            needs_confirmation=needs_confirmation,
            confidence=confidence,
        )
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse LLM JSON response: %s", exc)
        logger.debug("Response: %s", response)
        return ToolSlotAnalysisResult(relevant_tools=[])
    except Exception as exc:
        logger.error("Failed to parse LLM response: %s", exc, exc_info=True)
        return ToolSlotAnalysisResult(relevant_tools=[])
