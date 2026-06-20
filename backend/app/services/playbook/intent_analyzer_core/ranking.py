from typing import Any, List, Optional

from .schemas import ToolRelevanceResult


def sort_and_filter_tools(
    *,
    relevance_results: List[ToolRelevanceResult],
    min_relevance: float,
    max_tools: int,
    available_tools: List[Any],
    logger: Optional[Any] = None,
) -> List[Any]:
    """Sort relevant tool slots and fill small result sets by priority."""
    filtered_results = [
        result for result in relevance_results if result.relevance_score >= min_relevance
    ]
    tool_slot_map = {tool.slot: tool for tool in available_tools}

    filtered_tools_with_scores = []
    for result in filtered_results:
        if result.tool_slot in tool_slot_map:
            tool = tool_slot_map[result.tool_slot]
            tool.relevance_score = result.relevance_score
            filtered_tools_with_scores.append(tool)

    filtered_tools_with_scores.sort(
        key=lambda tool: (tool.priority, tool.relevance_score or 0.0),
        reverse=True,
    )
    filtered_tools = filtered_tools_with_scores[:max_tools]

    if len(filtered_tools) < 3 and len(available_tools) > len(filtered_tools):
        used_slots = {tool.slot for tool in filtered_tools}
        remaining_tools = [
            tool for tool in available_tools if tool.slot not in used_slots
        ]
        remaining_tools.sort(key=lambda tool: tool.priority, reverse=True)
        fallback_count = min(3 - len(filtered_tools), len(remaining_tools))
        filtered_tools.extend(remaining_tools[:fallback_count])
        if logger:
            logger.debug("Added %s fallback tools (priority-sorted)", fallback_count)

    return filtered_tools
