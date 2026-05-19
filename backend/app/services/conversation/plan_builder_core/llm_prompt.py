"""Prompt construction helpers for LLM plan generation."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Set, Tuple

logger = logging.getLogger(__name__)


def build_schema_description(pack_descriptions: str) -> str:
    """Build the structured extraction schema prompt."""
    return f"""Analyze the user message AND the conversation history to generate an execution plan by matching them with the available capability packs.

**Guidelines:**

1. **Scenario A: Capability Discovery**
   - If the user asks what you can do or what tools are available, return tasks for packs that specialize in listing or describing capabilities.
   - Do not execute action-oriented tasks, just inform the user.

2. **Scenario B: Action Execution**
   - Identify ALL relevant packs that can fulfill the request based on their descriptions.
   - If multiple packs are relevant to a single request, return tasks for ALL of them.
   - Match capabilities based on what the pack DOES (its purpose and impact), not just keyword matching.

3. **Orchestration & Workflow Selection:**
   - Prefer playbooks that represent a complete, high-level workflow (e.g., "complete_workflow", "page_assembly") over individual, granular playbooks when the user request is broad.
   - Use specialized, focused playbooks only when the user explicitly requests a single, specific operation or is working on a specific part of an existing item.

4. **Task Structure:**
   - Every task MUST include a valid `pack_id` from the available packs list below.
   - Return a JSON object with a "tasks" key containing an ARRAY of task objects.
   - NEVER return a null or empty `pack_id`.

Available packs:
{pack_descriptions}

Execution plan structure:
{{
  "tasks": [
    {{
      "pack_id": "Valid pack identifier from the list below (REQUIRED)",
      "task_type": "Specific action type (e.g., 'generate_content', 'analyze_data', 'extract_intents')",
      "params": {{
        "source": "message/file",
        "description": "Short summary of the specific task"
      }},
      "reason": "Clear justification based on the user's intent and the pack's purpose",
      "confidence": 0.0-1.0
    }}
  ]
}}

**Important Principles:**
- Semantic Matching: Deeply understand the user's intended GOAL.
- Completeness: Ensure every mentioned requirement is addressed by a corresponding pack.
- Diversity: If a request can be fulfilled in multiple ways (e.g., exporting to different formats), offer all relevant options.
- Context Awareness: Leverage recent Assistant suggestions and conversation history to refine pack selection."""


def build_context_with_history(
    *,
    project_context_str: str,
    workspace_context: str,
    cloud_rag_context: str,
    message: str,
    files: List[str],
    available_packs: List[str],
    intent_hint: str,
    context_note_str: str,
) -> str:
    """Build the user/context payload sent to structured extraction."""
    return f"""{project_context_str}{workspace_context}{cloud_rag_context}

---

User message: {message}
Files provided: {len(files)} file(s)
Available packs: {', '.join(available_packs)}{intent_hint}

Message analysis hints:
{context_note_str if context_note_str else "- Standard user request"}"""


def apply_progressive_degradation(
    *,
    context_builder: Any,
    context_with_history: str,
    schema_description: str,
    pack_descriptions: str,
    cloud_rag_context: str,
    project_context_str: str,
    workspace_context: str,
    message: str,
    files: List[str],
    available_packs: List[str],
    intent_hint: str,
    context_note_str: str,
    detected_pack_ids: Set[str],
    filtered_packs: List[Dict[str, Any]],
    pack_collector: Any,
    cloud_rag_snippet_limit: int,
    cloud_rag_char_limit: int,
    max_tokens_for_planning: int,
) -> Tuple[str, str]:
    """Apply the existing token-budget degradation sequence."""
    estimated_context_tokens = context_builder.estimate_token_count(
        context_with_history,
        model_name=None,
    )
    estimated_schema_tokens = context_builder.estimate_token_count(
        schema_description,
        model_name=None,
    )
    estimated_pack_tokens = context_builder.estimate_token_count(
        pack_descriptions,
        model_name=None,
    )
    estimated_cloud_tokens = (
        context_builder.estimate_token_count(cloud_rag_context, model_name=None)
        if cloud_rag_context
        else 0
    )
    total_estimated_tokens = (
        estimated_context_tokens
        + estimated_schema_tokens
        + estimated_pack_tokens
        + estimated_cloud_tokens
    )

    if total_estimated_tokens <= max_tokens_for_planning:
        return context_with_history, pack_descriptions

    logger.warning(
        "Total context too long (%s tokens > %s), applying v2 multi-stage progressive degradation",
        total_estimated_tokens,
        max_tokens_for_planning,
    )

    pack_descriptions, estimated_pack_tokens, total_estimated_tokens = (
        _reduce_pack_descriptions(
            context_builder=context_builder,
            pack_descriptions=pack_descriptions,
            estimated_context_tokens=estimated_context_tokens,
            estimated_schema_tokens=estimated_schema_tokens,
            estimated_cloud_tokens=estimated_cloud_tokens,
            detected_pack_ids=detected_pack_ids,
            filtered_packs=filtered_packs,
            pack_collector=pack_collector,
            available_packs=available_packs,
        )
    )

    cloud_rag_context, estimated_cloud_tokens, total_estimated_tokens = (
        _reduce_cloud_context(
            context_builder=context_builder,
            cloud_rag_context=cloud_rag_context,
            estimated_context_tokens=estimated_context_tokens,
            estimated_schema_tokens=estimated_schema_tokens,
            estimated_pack_tokens=estimated_pack_tokens,
            total_estimated_tokens=total_estimated_tokens,
            cloud_rag_snippet_limit=cloud_rag_snippet_limit,
            cloud_rag_char_limit=cloud_rag_char_limit,
            max_tokens_for_planning=max_tokens_for_planning,
        )
    )

    context_with_history = build_context_with_history(
        project_context_str=project_context_str,
        workspace_context=workspace_context,
        cloud_rag_context=cloud_rag_context,
        message=message,
        files=files,
        available_packs=available_packs,
        intent_hint=intent_hint,
        context_note_str=context_note_str,
    )

    estimated_context_tokens = context_builder.estimate_token_count(
        context_with_history,
        model_name=None,
    )
    total_estimated_tokens = estimated_context_tokens + estimated_schema_tokens

    if total_estimated_tokens > max_tokens_for_planning:
        logger.warning(
            "Context still exceeds limit after v2 progressive degradation (%s tokens > %s). "
            "Proceeding - extract function or LLM provider should handle gracefully. "
            "Components: workspace=%s, schema=%s, pack=%s, cloud=%s",
            total_estimated_tokens,
            max_tokens_for_planning,
            estimated_context_tokens,
            estimated_schema_tokens,
            estimated_pack_tokens,
            estimated_cloud_tokens,
        )
    else:
        logger.info(
            "Context fits after v2 progressive degradation: total=%s tokens",
            total_estimated_tokens,
        )

    return context_with_history, pack_descriptions


def _reduce_pack_descriptions(
    *,
    context_builder: Any,
    pack_descriptions: str,
    estimated_context_tokens: int,
    estimated_schema_tokens: int,
    estimated_cloud_tokens: int,
    detected_pack_ids: Set[str],
    filtered_packs: List[Dict[str, Any]],
    pack_collector: Any,
    available_packs: List[str],
) -> Tuple[str, int, int]:
    if not (
        detected_pack_ids
        and len(detected_pack_ids) < len(available_packs)
        and len(detected_pack_ids) > 0
    ):
        logger.info(
            "Stage 2: No keyword-suggested packs or all packs suggested, keeping all "
            "pack descriptions (detected_pack_ids=%s, available_packs=%s)",
            len(detected_pack_ids) if detected_pack_ids else 0,
            len(available_packs),
        )
        estimated_pack_tokens = context_builder.estimate_token_count(
            pack_descriptions,
            model_name=None,
        )
        total_estimated_tokens = (
            estimated_context_tokens
            + estimated_schema_tokens
            + estimated_pack_tokens
            + estimated_cloud_tokens
        )
        return pack_descriptions, estimated_pack_tokens, total_estimated_tokens

    logger.info(
        "Stage 2: Reducing pack descriptions (keeping %s keyword-suggested packs with full descriptions)",
        len(detected_pack_ids),
    )
    suggested_packs = [
        pack for pack in filtered_packs if pack.get("pack_id") in detected_pack_ids
    ]
    other_packs = [
        pack for pack in filtered_packs if pack.get("pack_id") not in detected_pack_ids
    ]
    suggested_descriptions = pack_collector.build_pack_description_list(
        suggested_packs
    )
    other_pack_ids = "\n".join(
        [f"- {pack.get('pack_id')}: (omitted description)" for pack in other_packs]
    )
    reduced_pack_descriptions = f"""{suggested_descriptions}

Other available packs (omitted for brevity):
{other_pack_ids}"""
    estimated_pack_tokens = context_builder.estimate_token_count(
        reduced_pack_descriptions,
        model_name=None,
    )
    total_estimated_tokens = (
        estimated_context_tokens
        + estimated_schema_tokens
        + estimated_pack_tokens
        + estimated_cloud_tokens
    )
    logger.info(
        "After Stage 2: pack=%s tokens, total=%s tokens",
        estimated_pack_tokens,
        total_estimated_tokens,
    )
    return reduced_pack_descriptions, estimated_pack_tokens, total_estimated_tokens


def _reduce_cloud_context(
    *,
    context_builder: Any,
    cloud_rag_context: str,
    estimated_context_tokens: int,
    estimated_schema_tokens: int,
    estimated_pack_tokens: int,
    total_estimated_tokens: int,
    cloud_rag_snippet_limit: int,
    cloud_rag_char_limit: int,
    max_tokens_for_planning: int,
) -> Tuple[str, int, int]:
    estimated_cloud_tokens = (
        context_builder.estimate_token_count(cloud_rag_context, model_name=None)
        if cloud_rag_context
        else 0
    )
    if total_estimated_tokens <= max_tokens_for_planning or not cloud_rag_context:
        return cloud_rag_context, estimated_cloud_tokens, total_estimated_tokens
    if cloud_rag_snippet_limit <= 3:
        return cloud_rag_context, estimated_cloud_tokens, total_estimated_tokens

    logger.info(
        "Stage 3: Reducing cloud RAG context (5 to 3 snippets, 200 to 100 chars)"
    )
    cloud_rag_snippet_limit = 3
    cloud_rag_char_limit = 100
    _ = cloud_rag_snippet_limit, cloud_rag_char_limit
    reduced_cloud_rag_context = (
        cloud_rag_context[: len(cloud_rag_context) // 2]
        + "\n(Cloud context truncated for token budget)"
    )
    estimated_cloud_tokens = context_builder.estimate_token_count(
        reduced_cloud_rag_context,
        model_name=None,
    )
    total_estimated_tokens = (
        estimated_context_tokens
        + estimated_schema_tokens
        + estimated_pack_tokens
        + estimated_cloud_tokens
    )
    logger.info(
        "After Stage 3: cloud=%s tokens, total=%s tokens",
        estimated_cloud_tokens,
        total_estimated_tokens,
    )
    return reduced_cloud_rag_context, estimated_cloud_tokens, total_estimated_tokens


def build_example_output() -> Dict[str, Any]:
    """Return the structured extraction example payload."""
    return {
        "tasks": [
            {
                "pack_id": "content_drafting",
                "task_type": "generate_draft",
                "params": {"source": "message"},
                "reason": "Message describes 'course design team' that helps design complete course flow with opening, theory, practice, Q&A - matches content_drafting pack's purpose",
                "confidence": 0.9,
            },
            {
                "pack_id": "storyboard",
                "task_type": "generate_storyboard",
                "params": {"source": "message"},
                "reason": "Message describes 'teaching script & Storyboard team' for creating teaching scripts, shot lists, and video content - directly matches storyboard pack",
                "confidence": 0.85,
            },
            {
                "pack_id": "daily_planning",
                "task_type": "generate_tasks",
                "params": {"source": "message"},
                "reason": "Message describes 'course project management / event PM team' for breaking down projects into tasks, timelines, and checklists - matches daily_planning pack",
                "confidence": 0.8,
            },
            {
                "pack_id": "habit_learning",
                "task_type": "generate_plan",
                "params": {"source": "message"},
                "reason": "Message describes 'habit and execution coaching team' for long-term habit building and continuous execution coaching - matches habit_learning pack",
                "confidence": 0.75,
            },
        ]
    }
