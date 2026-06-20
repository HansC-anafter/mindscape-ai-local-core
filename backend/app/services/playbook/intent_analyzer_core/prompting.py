from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .parser import format_candidate_tools, format_tool_list
from .schemas import ToolRelevanceResult


@dataclass
class ToolRelevancePrompt:
    prompt: str
    tool_list_for_analysis: List[Any]


def build_tool_relevance_prompt(
    *,
    user_message: str,
    available_tools: List[Any],
    conversation_history: Optional[List[Dict]] = None,
    emphasis: str = "balanced",
    max_tools: int = 10,
    candidate_tools: Optional[List[ToolRelevanceResult]] = None,
) -> ToolRelevancePrompt:
    """Build the governed LLM prompt for tool-slot relevance analysis."""
    tool_list_for_analysis = available_tools
    conversation_summary = _build_conversation_summary(conversation_history)

    if candidate_tools:
        tool_list_str = format_candidate_tools(candidate_tools)
        tool_count_hint = f"Focus on these {len(candidate_tools)} pre-filtered candidates"
    else:
        tool_list_str = format_tool_list(tool_list_for_analysis)
        tool_count_hint = f"Analyze all {len(tool_list_for_analysis)} available tools"

    selection_strategy = _selection_strategy(emphasis, max_tools)
    prompt = f"""You are a tool selection assistant. Analyze which tools are relevant to the user's intent.

User Message:
{user_message}

Conversation History Summary:
{conversation_summary if conversation_summary else "None"}

{tool_count_hint}:
{tool_list_str}

{selection_strategy}

Please analyze the user's intent and return:
- The most relevant tool slots (up to {max_tools} tools)
- Relevance scores (0.0-1.0) for each
- Reasoning for each tool
- Overall confidence in the analysis

**Scoring Criteria**:
- 1.0: Perfectly matches user needs
- 0.7-0.9: Highly relevant
- 0.4-0.6: Partially relevant
- 0.0-0.3: Not relevant

Return JSON format:
```json
{{
  "relevant_tools": [
    {{
      "tool_slot": "tool_slot_name",
      "relevance_score": 0.95,
      "reasoning": "Why this tool is relevant",
      "confidence": 0.9
    }}
  ],
  "overall_reasoning": "Overall analysis",
  "needs_confirmation": false,
  "confidence": 0.85
}}
```

**Important**: Return only JSON, no other text."""
    return ToolRelevancePrompt(
        prompt=prompt,
        tool_list_for_analysis=tool_list_for_analysis,
    )


def _build_conversation_summary(
    conversation_history: Optional[List[Dict]],
) -> str:
    if not conversation_history:
        return ""

    recent_messages = (
        conversation_history[-6:]
        if len(conversation_history) > 6
        else conversation_history
    )
    conversation_summary = "\n".join(
        f"{msg.get('role', 'user')}: {msg.get('content', '')[:200]}"
        for msg in recent_messages
    )

    conversation_text = " ".join(
        msg.get("content", "") for msg in recent_messages
    ).lower()
    if any(keyword in conversation_text for keyword in ["analyze", "read", "view", "check", "explore"]):
        sop_stage_context = (
            "Stage: Analysis/Reading phase - tools for reading/viewing content "
            "are more relevant."
        )
    elif any(keyword in conversation_text for keyword in ["create", "generate", "write", "draft", "compose"]):
        sop_stage_context = (
            "Stage: Creation/Generation phase - tools for creating/generating "
            "content are more relevant."
        )
    elif any(keyword in conversation_text for keyword in ["publish", "deploy", "update", "apply", "push"]):
        sop_stage_context = (
            "Stage: Publishing/Deployment phase - tools for publishing/updating "
            "are more relevant."
        )
    else:
        sop_stage_context = ""

    if sop_stage_context:
        return f"{sop_stage_context}\n\n{conversation_summary}"
    return conversation_summary


def _selection_strategy(emphasis: str, max_tools: int) -> str:
    if emphasis == "recall":
        return f"""
**Selection Strategy (RECALL FOCUS)**:
- Return up to {max_tools} tools that might be relevant
- Prioritize not missing any potentially useful tools
- Lower precision is acceptable, but don't miss anything
- Include tools even if confidence is moderate (0.4-0.6)
"""
    if emphasis == "precision":
        return f"""
**Selection Strategy (PRECISION FOCUS)**:
- Return only the {max_tools} most accurate and relevant tools
- Prioritize high confidence matches (0.7+)
- Exclude tools with low confidence or ambiguous relevance
- Focus on precision over recall
"""
    return f"""
**Selection Strategy (BALANCED)**:
- Return 1-{max_tools} most relevant tools
- Balance between recall and precision
- Prioritize high confidence matches
"""
