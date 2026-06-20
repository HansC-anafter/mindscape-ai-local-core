"""
Execution Plan Generator

Generates structured ExecutionPlan (Chain-of-Thought) from user requests.
This is the canonical execution-mode planning facade.
"""

import logging
from typing import Any, Callable, Dict, List, Optional

from backend.app.models.workspace import ExecutionPlan
from backend.app.services.execution_plan_context import (
    EXECUTION_PLAN_PROMPT,
    _coerce_chat_text,
    _resolve_governed_chat_inputs,
    _utc_now,
    append_execution_plan_trace,
    append_plan_exception,
    append_plan_prompt_evidence,
    append_plan_response,
    build_context_section,
    build_project_context,
    format_playbooks_prompt,
)
from backend.app.services.execution_plan_models import (
    _convert_steps_to_tasks,
    _create_execution_plan,
    _create_minimal_plan,
)
from backend.app.services.execution_plan_validation import (
    _parse_plan_json,
    _validate_and_reevaluate_plan,
)
from backend.app.services.llm.workspace_routed_chat import (
    chat_completion_with_workspace_route,
)

logger = logging.getLogger(__name__)


async def generate_execution_plan(
    user_request: str,
    workspace_id: str,
    message_id: str,
    execution_mode: str = "execution",
    expected_artifacts: Optional[List[str]] = None,
    available_playbooks: Optional[List[Dict[str, Any]]] = None,
    effective_playbooks: Optional[List[Dict[str, Any]]] = None,
    llm_provider: Any = None,
    model_name: Optional[str] = None,
    progress_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    project_id: Optional[str] = None,
    project_assignment_decision: Optional[Dict[str, Any]] = None,
    tenant_id: Optional[str] = None,
    user_id: Optional[str] = None,
    planning_context: Optional[str] = None,
    thread_id: Optional[str] = None,
    uploaded_files_context: Optional[str] = None,
) -> Optional[ExecutionPlan]:
    """
    Generate a structured ExecutionPlan from a user request using the governed LLM route.

    Args:
        user_request: User's message/request
        workspace_id: Workspace ID
        message_id: Message/event ID
        execution_mode: qa/execution/hybrid
        expected_artifacts: Expected artifact types for this workspace
        available_playbooks: List of available playbooks
        effective_playbooks: Pre-resolved effective playbooks from PlaybookScopeResolver
        llm_provider: LLM provider or provider manager instance
        model_name: Model to use
        progress_callback: Optional callback for re-evaluation status
        project_id: Optional project ID for project context
        project_assignment_decision: Optional project assignment decision metadata
        tenant_id: Tenant ID
        user_id: Current user ID
        planning_context: Optional thread-first planning context
        thread_id: Optional thread ID for thread-scoped context
        uploaded_files_context: Optional uploaded-file context

    Returns:
        ExecutionPlan or None if generation is skipped
    """
    if execution_mode == "qa":
        logger.info("[ExecutionPlanGenerator] Skipping plan generation for QA mode")
        return None

    if not model_name:
        error_msg = "Cannot generate execution plan: model_name is required"
        logger.error(error_msg)
        raise ValueError(error_msg)

    if not llm_provider:
        error_msg = "Cannot generate execution plan: llm_provider is required"
        logger.error(error_msg)
        raise ValueError(error_msg)

    playbooks_to_use = (
        effective_playbooks if effective_playbooks is not None else available_playbooks
    )
    profile_id = user_id or "default-user"

    append_execution_plan_trace(
        workspace_id=workspace_id,
        user_request=user_request,
        playbooks_to_use=playbooks_to_use,
        effective_playbooks=effective_playbooks,
        available_playbooks=available_playbooks,
    )

    playbooks_str, _playbook_codes_list = format_playbooks_prompt(playbooks_to_use)
    project_context_str = await build_project_context(
        project_id=project_id,
        project_assignment_decision=project_assignment_decision,
        workspace_id=workspace_id,
    )
    context_section = build_context_section(planning_context)

    try:
        try:
            prompt = EXECUTION_PLAN_PROMPT.format(
                project_context=project_context_str,
                context_section=context_section,
                user_request=user_request,
                uploaded_files_context=uploaded_files_context or "",
                execution_mode=execution_mode,
                expected_artifacts=expected_artifacts or ["various"],
                available_playbooks=playbooks_str,
            )
        except KeyError as exc:
            logger.error(
                f"[ExecutionPlanGenerator] Template formatting failed due to missing key: {exc}"
            )
            raise

        from backend.app.shared.llm_utils import build_prompt

        messages = build_prompt(
            system_prompt="You are an Execution Planning Agent that outputs JSON. Respond in zh-TW for any reasoning fields.",
            user_prompt=prompt,
        )
        append_plan_prompt_evidence(
            workspace_id=workspace_id,
            playbooks_to_use=playbooks_to_use,
            prompt=prompt,
        )

        provider, llm_provider_manager = _resolve_governed_chat_inputs(llm_provider)
        response = await chat_completion_with_workspace_route(
            messages=messages,
            workspace_id=workspace_id,
            profile_id=profile_id,
            provider=provider,
            llm_provider_manager=llm_provider_manager,
            model=model_name,
            purpose="execution_plan_generation",
            stage_name="plan_generation",
            risk_level="read",
            temperature=0.3,
            max_tokens=4000,
        )
        response_text = _coerce_chat_text(response)
        append_plan_response(response_text)

        logger.info(
            f"[ExecutionPlanGenerator] Received LLM response, length: {len(response_text)} chars"
        )
        logger.debug(
            f"[ExecutionPlanGenerator] Response preview (first 500 chars): {response_text[:500]}"
        )

        plan_data = _parse_plan_json(response_text)
        if not plan_data:
            error_msg = "Failed to parse execution plan from LLM response"
            logger.error(error_msg)
            raise ValueError(error_msg)

        plan_data = await _validate_and_reevaluate_plan(
            plan_data=plan_data,
            available_playbooks=playbooks_to_use,
            user_request=user_request,
            execution_mode=execution_mode,
            expected_artifacts=expected_artifacts,
            llm_provider=llm_provider,
            model_name=model_name,
            workspace_id=workspace_id,
            profile_id=profile_id,
            progress_callback=progress_callback,
            chat_completion_fn=chat_completion_with_workspace_route,
            resolve_governed_chat_inputs_fn=_resolve_governed_chat_inputs,
            coerce_chat_text_fn=_coerce_chat_text,
        )

        execution_plan = _create_execution_plan(
            plan_data=plan_data,
            workspace_id=workspace_id,
            message_id=message_id,
            execution_mode=execution_mode,
            available_playbooks=playbooks_to_use,
        )

        if project_id:
            execution_plan.project_id = project_id
        if project_assignment_decision:
            execution_plan.project_assignment_decision = project_assignment_decision

        return execution_plan

    except Exception as exc:
        logger.error(
            f"[ExecutionPlanGenerator] Failed to generate plan: {exc}", exc_info=True
        )
        append_plan_exception(exc)
        raise


async def record_execution_plan_event(
    plan: ExecutionPlan, profile_id: str, project_id: Optional[str] = None
) -> None:
    """
    Record ExecutionPlan as EXECUTION_PLAN MindEvent.

    This creates the trace for debugging, replay, and optimization.

    Args:
        plan: ExecutionPlan to record
        profile_id: User profile ID
        project_id: Optional project ID
    """
    try:
        from backend.app.models.mindscape import EventActor, EventType, MindEvent
        from backend.app.services.mindscape_store import MindscapeStore

        store = MindscapeStore()

        event = MindEvent(
            id=plan.id,
            timestamp=plan.created_at,
            actor=EventActor.ASSISTANT,
            channel="local_workspace",
            profile_id=profile_id,
            project_id=project_id,
            workspace_id=plan.workspace_id,
            event_type=EventType.EXECUTION_PLAN,
            payload=plan.to_event_payload(),
            entity_ids=[],
            metadata={
                "execution_mode": plan.execution_mode,
                "step_count": len(plan.steps),
                "confidence": plan.confidence,
            },
        )

        store.create_event(event, generate_embedding=True)
        logger.info(
            f"[ExecutionPlanGenerator] Recorded EXECUTION_PLAN event: {plan.id}"
        )

    except Exception as exc:
        logger.warning(f"[ExecutionPlanGenerator] Failed to record plan event: {exc}")
