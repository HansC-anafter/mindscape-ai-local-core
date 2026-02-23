"""
Execution Plan Handler

Generates execution plans for execution/hybrid mode and emits SSE events
for each pipeline stage. Coordinates plan generation, playbook selection
notifications, and plan execution via execute_plan_and_send_events.
"""

import json
import logging
from typing import Any, AsyncGenerator, List, Optional

from backend.app.shared.i18n_loader import get_locale_from_context, load_i18n_string
from .execution_plan import generate_and_execute_plan, execute_plan_and_send_events

logger = logging.getLogger(__name__)


async def handle_execution_plan(
    user_event_id: str,
    request: Any,
    workspace: Any,
    workspace_id: str,
    profile_id: str,
    project_id: Optional[str],
    thread_id: Optional[str],
    execution_mode: str,
    model_name: str,
    available_playbooks: List[Any],
    profile: Any,
    orchestrator: Any,
    locale: str,
) -> AsyncGenerator[str, None]:
    """
    Generate and execute an execution plan, emitting SSE events.

    Handles: plan generation, no-action detection, playbook selection
    notification, plan execution, and error reporting.

    Args:
        user_event_id: User event ID for SSE run_id.
        request: WorkspaceChatRequest with .message, .files.
        workspace: Workspace object.
        workspace_id: Workspace ID.
        profile_id: Profile ID.
        project_id: Optional project ID.
        thread_id: Optional thread ID.
        execution_mode: Resolved execution mode.
        model_name: LLM model name.
        available_playbooks: List of available playbooks.
        profile: User profile object.
        orchestrator: ConversationOrchestrator instance.
        locale: Response locale.

    Yields:
        SSE event strings.
    """
    from ..utils.llm_provider import (
        get_llm_provider_manager,
        get_provider_name_from_model_config,
    )

    expected_artifacts = getattr(workspace, "expected_artifacts", None)

    try:
        provider_name, _ = get_provider_name_from_model_config(model_name)
        if not provider_name:
            return

        llm_provider_manager = get_llm_provider_manager(
            profile_id=profile_id, db_path=orchestrator.store.db_path
        )

        execution_plan = await generate_and_execute_plan(
            user_request=request.message,
            workspace_id=workspace_id,
            message_id=user_event_id,
            profile_id=profile_id,
            project_id=project_id,
            thread_id=thread_id,
            execution_mode=execution_mode,
            expected_artifacts=expected_artifacts,
            available_playbooks=available_playbooks,
            model_name=model_name,
            llm_provider_manager=llm_provider_manager,
            orchestrator=orchestrator,
            files=getattr(request, "files", []) or [],
        )

        if not execution_plan:
            # No plan generated
            async for event in _emit_no_playbook_found(
                user_event_id, execution_mode, profile, workspace
            ):
                yield event
            return

        # Check if plan has tasks
        if not execution_plan.tasks or len(execution_plan.tasks) == 0:
            async for event in _emit_no_action_needed(
                execution_plan, user_event_id, execution_mode, profile, workspace
            ):
                yield event
            return

        # Plan has tasks -- emit plan event
        plan_payload = execution_plan.to_event_payload()
        logger.info(
            "Generated ExecutionPlan with %d steps, %d tasks, plan_id=%s",
            len(execution_plan.steps),
            len(execution_plan.tasks),
            execution_plan.id,
        )
        yield f"data: {json.dumps({'type': 'execution_plan', 'plan': plan_payload})}\n\n"

        # Emit playbook selection stage
        if execution_mode in ("execution", "hybrid") and execution_plan.tasks:
            async for event in _emit_playbook_selection(
                execution_plan, user_event_id, profile, workspace
            ):
                yield event

        # Execute plan and stream events
        async for event in execute_plan_and_send_events(
            execution_plan=execution_plan,
            workspace_id=workspace_id,
            profile_id=profile_id,
            message_id=user_event_id,
            project_id=project_id,
            message=request.message,
            files=getattr(request, "files", []) or [],
            orchestrator=orchestrator,
        ):
            yield event

    except Exception as e:
        logger.warning("Failed to generate ExecutionPlan: %s", e, exc_info=True)
        if execution_mode in ("execution", "hybrid"):
            error_event = {
                "type": "pipeline_stage",
                "run_id": user_event_id,
                "stage": "execution_error",
                "message": load_i18n_string(
                    "workspace.pipeline_stage.execution_error",
                    locale=get_locale_from_context(
                        profile=profile, workspace=workspace
                    ),
                    default=f"Encountered a problem during execution: {str(e)}",
                ).format(error_message=str(e)),
                "streaming": True,
                "metadata": {
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
            }
            yield f"data: {json.dumps(error_event)}\n\n"


# ------------------------------------------------------------------
# Private SSE emitters
# ------------------------------------------------------------------


async def _emit_no_action_needed(
    execution_plan, user_event_id, execution_mode, profile, workspace
):
    """Emit no_action_needed pipeline stage event."""
    if execution_mode not in ("execution", "hybrid"):
        return

    locale = get_locale_from_context(profile=profile, workspace=workspace)
    plan_summary = execution_plan.plan_summary or execution_plan.user_request_summary

    if plan_summary:
        plan_preview = plan_summary[:40] + ("..." if len(plan_summary) > 40 else "")
        message = load_i18n_string(
            "workspace.pipeline_stage.no_action_needed_with_summary",
            locale=locale,
            default=f"This round focuses on clarifying '{plan_preview}', no Playbook needed for now.",
        ).format(plan_summary=plan_preview)
    else:
        message = load_i18n_string(
            "workspace.pipeline_stage.no_action_needed",
            locale=locale,
            default="This round focuses on clarifying ideas, no Playbook needed for now.",
        )

    event = {
        "type": "pipeline_stage",
        "run_id": execution_plan.id or user_event_id,
        "stage": "no_action_needed",
        "message": message,
        "streaming": True,
    }
    yield f"data: {json.dumps(event)}\n\n"


async def _emit_no_playbook_found(user_event_id, execution_mode, profile, workspace):
    """Emit no_playbook_found pipeline stage event."""
    if execution_mode not in ("execution", "hybrid"):
        return

    event = {
        "type": "pipeline_stage",
        "run_id": user_event_id,
        "stage": "no_playbook_found",
        "message": load_i18n_string(
            "workspace.pipeline_stage.no_playbook_found",
            locale=get_locale_from_context(profile=profile, workspace=workspace),
            default="No suitable Playbook found for this request, using general reasoning instead.",
        ),
        "streaming": True,
    }
    yield f"data: {json.dumps(event)}\n\n"


async def _emit_playbook_selection(execution_plan, user_event_id, profile, workspace):
    """Emit playbook_selection pipeline stage event."""
    playbook_code = None
    if hasattr(execution_plan, "playbook_code") and execution_plan.playbook_code:
        playbook_code = execution_plan.playbook_code
    elif execution_plan.tasks and execution_plan.tasks[0].pack_id:
        playbook_code = execution_plan.tasks[0].pack_id

    playbook_name = playbook_code or "Playbook"
    task_count = len(execution_plan.tasks)
    locale = get_locale_from_context(profile=profile, workspace=workspace)

    plan_summary = execution_plan.plan_summary or execution_plan.user_request_summary
    if plan_summary:
        plan_preview = plan_summary[:40] + ("..." if len(plan_summary) > 40 else "")
        message = load_i18n_string(
            "workspace.pipeline_stage.playbook_selection_with_summary",
            locale=locale,
            default=(
                f"Selected '{playbook_name}' Playbook for '{plan_preview}', "
                f"splitting into {task_count} tasks."
            ),
        ).format(
            playbook_name=playbook_name,
            plan_summary=plan_preview,
            task_count=task_count,
        )
    else:
        message = load_i18n_string(
            "workspace.pipeline_stage.playbook_selection",
            locale=locale,
            default=(
                f"Selected '{playbook_name}' Playbook, "
                f"splitting into {task_count} tasks for AI team."
            ),
        ).format(playbook_name=playbook_name, task_count=task_count)

    event = {
        "type": "pipeline_stage",
        "run_id": execution_plan.id or user_event_id,
        "stage": "playbook_selection",
        "message": message,
        "streaming": True,
        "metadata": {
            "playbook_code": playbook_code,
            "task_count": task_count,
        },
    }
    yield f"data: {json.dumps(event)}\n\n"
