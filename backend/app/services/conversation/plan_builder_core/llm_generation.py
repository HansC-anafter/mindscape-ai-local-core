"""LLM plan generation orchestration for PlanBuilder."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ....models.workspace import SideEffectLevel, TaskPlan
from backend.app.shared.llm_provider_helper import get_llm_provider_from_settings
from .llm_context import (
    build_cloud_rag_context,
    build_message_analysis_notes,
    build_project_context,
    build_workspace_context,
    collect_pack_context,
)
from .llm_prompt import (
    apply_progressive_degradation,
    build_context_with_history,
    build_example_output,
    build_schema_description,
)
from .llm_trace import (
    end_plan_generation_trace_failure,
    end_plan_generation_trace_success,
    start_plan_generation_trace,
    utc_now,
)

logger = logging.getLogger(__name__)


async def generate_llm_plan(
    builder: Any,
    *,
    message: str,
    files: List[str],
    workspace_id: str,
    profile_id: str,
    available_packs: List[str],
    project_id: Optional[str] = None,
    project_assignment_decision: Optional[Dict[str, Any]] = None,
    thread_id: Optional[str] = None,
) -> List[TaskPlan]:
    """Generate an execution plan through the configured LLM provider."""
    try:
        from backend.app.capabilities.core_llm.services.structured import extract
        from backend.app.services.conversation.context_builder import ContextBuilder
        from backend.app.services.stores.postgres.timeline_items_store import (
            PostgresTimelineItemsStore,
        )

        llm_provider = _resolve_llm_provider(builder, profile_id)
        if llm_provider is None:
            return []

        max_tokens_for_planning = 10000
        model_name = builder._select_model_for_plan(
            risk_level="read",
            profile_id=profile_id,
        )
        if not model_name or model_name.strip() == "":
            raise ValueError(
                "LLM model is empty. Configure chat_model in model-routing-registry."
            )

        context_builder = ContextBuilder(
            store=builder.store,
            timeline_items_store=PostgresTimelineItemsStore(),
            model_name=model_name,
        )
        workspace, workspace_context = await build_workspace_context(
            builder,
            context_builder,
            message=message,
            workspace_id=workspace_id,
            profile_id=profile_id,
            thread_id=thread_id,
            max_tokens_for_planning=max_tokens_for_planning,
        )
        project_context_str = await build_project_context(
            builder,
            project_id=project_id,
            workspace_id=workspace_id,
            project_assignment_decision=project_assignment_decision,
        )
        (
            cloud_rag_context,
            cloud_rag_snippet_limit,
            cloud_rag_char_limit,
        ) = await build_cloud_rag_context(
            builder,
            workspace=workspace,
            workspace_id=workspace_id,
            message=message,
            profile_id=profile_id,
        )
        (
            pack_collector,
            filtered_packs,
            pack_descriptions,
            detected_pack_ids,
            intent_hint,
        ) = collect_pack_context(
            builder,
            workspace_id=workspace_id,
            message=message,
            available_packs=available_packs,
        )

        context_note_str = build_message_analysis_notes(message)
        schema_description = build_schema_description(pack_descriptions)
        context_with_history = build_context_with_history(
            project_context_str="",
            workspace_context=workspace_context,
            cloud_rag_context=cloud_rag_context,
            message=message,
            files=files,
            available_packs=available_packs,
            intent_hint=intent_hint,
            context_note_str=context_note_str,
        )
        context_with_history, pack_descriptions = apply_progressive_degradation(
            context_builder=context_builder,
            context_with_history=context_with_history,
            schema_description=schema_description,
            pack_descriptions=pack_descriptions,
            cloud_rag_context=cloud_rag_context,
            project_context_str=project_context_str,
            workspace_context=workspace_context,
            message=message,
            files=files,
            available_packs=available_packs,
            intent_hint=intent_hint,
            context_note_str=context_note_str,
            detected_pack_ids=detected_pack_ids,
            filtered_packs=filtered_packs,
            pack_collector=pack_collector,
            cloud_rag_snippet_limit=cloud_rag_snippet_limit,
            cloud_rag_char_limit=cloud_rag_char_limit,
            max_tokens_for_planning=max_tokens_for_planning,
        )

        trace_id, trace_node_id = start_plan_generation_trace(
            workspace_id=workspace_id,
            profile_id=profile_id,
            message=message,
            model_name=model_name,
            available_packs=available_packs,
            capability_profile=builder.capability_profile,
        )
        llm_start_time = utc_now()

        try:
            result = await extract(
                text=context_with_history,
                schema_description=schema_description,
                example_output=build_example_output(),
                llm_provider=llm_provider,
            )
            end_plan_generation_trace_success(
                trace_id=trace_id,
                trace_node_id=trace_node_id,
                llm_start_time=llm_start_time,
                context_with_history=context_with_history,
                result=result,
            )
        except Exception as exc:
            end_plan_generation_trace_failure(
                trace_id=trace_id,
                trace_node_id=trace_node_id,
                llm_start_time=llm_start_time,
                error=exc,
            )
            raise

        return _build_task_plans_from_result(
            builder,
            result=result,
            available_packs=available_packs,
        )
    except Exception as exc:
        logger.warning(
            "Failed to generate LLM plan: %s, falling back to rule-based planning",
            exc,
        )
        return []


def _resolve_llm_provider(builder: Any, profile_id: str) -> Optional[Any]:
    config = builder.config_store.get_or_create_config(profile_id)
    cache_key = profile_id or "default-user"
    if cache_key not in builder._llm_manager_cache:
        from backend.app.shared.llm_provider_helper import create_llm_provider_manager

        builder._llm_manager_cache[cache_key] = create_llm_provider_manager(
            openai_key=config.agent_backend.openai_api_key,
            anthropic_key=config.agent_backend.anthropic_api_key,
            vertex_api_key=config.agent_backend.vertex_api_key,
            vertex_project_id=config.agent_backend.vertex_project_id,
            vertex_location=config.agent_backend.vertex_location,
        )

    from backend.app.services.model_routing_policy_service import (
        ModelRoutingPolicyService,
    )

    resolved_route = ModelRoutingPolicyService().resolve_chat_default()
    _ = resolved_route.model_name

    try:
        return get_llm_provider_from_settings(builder._llm_manager_cache[cache_key])
    except ValueError as exc:
        logger.warning(
            "LLM provider not available: %s, falling back to rule-based planning",
            exc,
        )
        return None


def _build_task_plans_from_result(
    builder: Any,
    *,
    result: Dict[str, Any],
    available_packs: List[str],
) -> List[TaskPlan]:
    extracted_data = result.get("extracted_data", {})
    logger.info("Full extracted_data: %s", extracted_data)

    tasks_data = extracted_data.get("tasks", [])
    if not tasks_data and isinstance(extracted_data, dict):
        if "pack_id" in extracted_data:
            logger.warning(
                "LLM returned single task object instead of tasks array, wrapping it. "
                "This should not happen - LLM should return {'tasks': [...]} format"
            )
            tasks_data = [extracted_data]
        else:
            logger.warning(
                "tasks key not found in extracted_data, keys: %s",
                list(extracted_data.keys()),
            )

    if tasks_data and len(tasks_data) == 1:
        logger.warning(
            "LLM returned only 1 task. For requests like 'export file', multiple "
            "tasks (content_drafting, storyboard, core_export) should be returned. "
            "Current task: %s",
            tasks_data[0].get("pack_id"),
        )

    logger.info("Extracted %s tasks from LLM response: %s", len(tasks_data), tasks_data)
    logger.info("Available packs: %s", available_packs)

    task_plans = []
    for task_data in tasks_data:
        task_plan = _build_task_plan(builder, task_data, available_packs)
        if task_plan:
            task_plans.append(task_plan)

    logger.info("LLM generated %s task plans", len(task_plans))
    return task_plans


def _build_task_plan(
    builder: Any,
    task_data: Dict[str, Any],
    available_packs: List[str],
) -> Optional[TaskPlan]:
    pack_id = task_data.get("pack_id")
    if not pack_id or pack_id not in available_packs:
        logger.warning("LLM suggested unavailable pack %s, skipping", pack_id)
        return None

    if not builder.is_pack_available(pack_id):
        logger.warning("Pack %s is not available, skipping", pack_id)
        return None
    if not builder.check_pack_tools_configured(pack_id):
        logger.warning("Pack %s tools are not configured, skipping", pack_id)
        return None

    level = builder.determine_side_effect_level(pack_id)
    confidence = task_data.get("confidence", 0.8)
    if not isinstance(confidence, (int, float)) or confidence < 0 or confidence > 1:
        logger.warning(
            "Invalid confidence value %s for pack %s, using default 0.8",
            confidence,
            pack_id,
        )
        confidence = 0.8

    llm_analysis = {
        "confidence": float(confidence),
        "reason": task_data.get("reason", ""),
        "content_tags": [],
        "analysis_summary": task_data.get("reason", "")[:200],
    }

    logger.info(
        "Task %s: confidence=%.2f, reason=%s",
        pack_id,
        confidence,
        task_data.get("reason", "")[:50],
    )

    params = task_data.get("params", {})
    params["llm_analysis"] = llm_analysis

    return TaskPlan(
        pack_id=pack_id,
        task_type=task_data.get("task_type", "execute"),
        params=params,
        side_effect_level=level.value,
        auto_execute=(level == SideEffectLevel.READONLY),
        requires_cta=(level != SideEffectLevel.READONLY),
    )
