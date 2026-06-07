"""Playbook and tool action helpers for SuggestionActionHandler."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.app.core.domain_context import LocalDomainContext
from backend.app.models.workspace import ExecutionPlan, Task, TaskPlan, TaskStatus
from backend.app.services.capability_registry import get_registry
from backend.app.services.playbook_service import ExecutionMode as PlaybookExecutionMode

logger = logging.getLogger(__name__)


def _utc_now():
    return datetime.now(timezone.utc)


def build_object_action_dispatch_metadata(
    *,
    action_params: Dict[str, Any],
    execution_id: Optional[str],
) -> Optional[Dict[str, Any]]:
    """Build object-action dispatch metadata."""
    plan_payload = action_params.get("object_action_plan")
    if not isinstance(plan_payload, dict):
        return None

    request_plan = plan_payload.get("request_plan")
    if not isinstance(request_plan, dict):
        request_plan = {}
    selected_affordance = plan_payload.get("selected_affordance")
    if not isinstance(selected_affordance, dict):
        selected_affordance = {}

    action_plan_id = (
        action_params.get("object_action_plan_id")
        or request_plan.get("action_plan_id")
        or plan_payload.get("action_plan_id")
    )
    entries = action_params.get("object_action_entries")
    if not isinstance(entries, list):
        entries = plan_payload.get("role_assignments")
    if not isinstance(entries, list):
        entries = []

    return {
        "status": "closure_pending",
        "action_plan_id": action_plan_id,
        "execution_id": execution_id,
        "meeting_id": action_params.get("meeting_id")
        or action_params.get("meeting_session_id"),
        "affordance_verb": request_plan.get("affordance_verb")
        or selected_affordance.get("verb"),
        "entries_count": len(entries),
    }


async def handle_execute_playbook(
    handler: Any,
    *,
    ctx: LocalDomainContext,
    action_params: Dict[str, Any],
    project_id: Optional[str],
    message_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Handle execute_playbook action."""
    playbook_code = action_params.get("playbook_code")
    if not playbook_code:
        logger.error(
            "_handle_execute_playbook: playbook_code missing in action_params: %s",
            action_params,
        )
        raise ValueError("playbook_code is required for execute_playbook action")

    logger.info(
        "_handle_execute_playbook: Starting execution for playbook %s, workspace=%s, profile=%s",
        playbook_code,
        ctx.workspace_id,
        ctx.actor_id,
    )

    playbook_context = action_params.copy()
    playbook_context["from_suggestion_action"] = True
    playbook_context["task_id"] = action_params.get("task_id")
    locale = playbook_context.get("locale") or handler.default_locale

    logger.info(
        "_handle_execute_playbook: Loading playbook for %s, locale=%s",
        playbook_code,
        locale,
    )
    playbook = await handler.playbook_service.get_playbook(
        playbook_code=playbook_code,
        locale=locale,
        workspace_id=ctx.workspace_id,
    )
    if not playbook:
        logger.error("_handle_execute_playbook: Playbook %s not found", playbook_code)
        raise ValueError(f"Playbook {playbook_code} not found")

    playbook_run = await handler.playbook_service.load_playbook_run(
        playbook_code=playbook_code,
        locale=locale,
        workspace_id=ctx.workspace_id,
    )
    if not playbook_run or not playbook_run.has_json():
        logger.error(
            "_handle_execute_playbook: Playbook %s does not have playbook.json",
            playbook_code,
        )
        raise ValueError(
            f"Playbook {playbook_code} does not have playbook.json. "
            "HandoffPlan is required for execution. Please create playbook.json for structured workflow execution."
        )

    logger.info(
        "_handle_execute_playbook: Calling execute_playbook for %s, project_id=%s",
        playbook_code,
        project_id,
    )
    execution_result_obj = await handler.playbook_service.execute_playbook(
        playbook_code=playbook_code,
        workspace_id=ctx.workspace_id,
        profile_id=ctx.actor_id,
        inputs=playbook_context,
        execution_mode=PlaybookExecutionMode.ASYNC,
        locale=locale,
        project_id=project_id,
    )
    execution_result = {
        "execution_id": execution_result_obj.execution_id,
        "execution_mode": (
            "workflow" if execution_result_obj.status == "running" else "conversation"
        ),
        "result": execution_result_obj.result or {},
    }
    logger.info(
        "_handle_execute_playbook: Execution completed for %s, execution_id=%s",
        playbook_code,
        execution_result_obj.execution_id,
    )

    handler._create_user_event(
        ctx.workspace_id,
        ctx.actor_id,
        project_id,
        f"Execute playbook: {playbook_code}",
        "execute_playbook",
        action_params,
    )

    execution_id = None
    if execution_result.get("execution_id"):
        execution_id = execution_result.get("execution_id")
    elif execution_result.get("result", {}).get("execution_id"):
        execution_id = execution_result.get("result", {}).get("execution_id")

    logger.info(
        "_handle_execute_playbook: Returning execution_id=%s for %s",
        execution_id,
        playbook_code,
    )
    object_action = build_object_action_dispatch_metadata(
        action_params=action_params,
        execution_id=execution_id,
    )
    triggered_playbook = {
        "playbook_code": playbook_code,
        "execution_id": execution_id,
        "status": "triggered",
    }
    if object_action:
        triggered_playbook["object_action"] = object_action

    return {
        "workspace_id": ctx.workspace_id,
        "status": "accepted",
        "task_id": execution_id,
        "display_events": [],
        "triggered_playbook": triggered_playbook,
        "object_action": object_action,
        "pending_tasks": [],
    }


async def handle_use_tool(
    handler: Any,
    *,
    ctx: LocalDomainContext,
    action_params: Dict[str, Any],
    project_id: Optional[str],
    message_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Handle use_tool action."""
    tool_name = action_params.get("tool")
    if not tool_name:
        raise ValueError("tool is required for use_tool action")

    registry = get_registry()
    tool_info = registry.get_tool(tool_name)
    if not tool_info:
        raise ValueError(f"Tool {tool_name} not found")

    capability_code = tool_info.get("capability")
    capability_info = registry.capabilities.get(capability_code)
    side_effect_level = (
        capability_info.get("manifest", {}).get("side_effect_level", "readonly")
        if capability_info
        else "readonly"
    )

    plan = ExecutionPlan(
        message_id=message_id or str(uuid.uuid4()),
        workspace_id=ctx.workspace_id,
        tasks=[
            TaskPlan(
                pack_id=capability_code,
                task_type=tool_name.split(".")[-1],
                params=action_params,
                side_effect_level=side_effect_level,
                auto_execute=(side_effect_level == "readonly"),
                requires_cta=(side_effect_level != "readonly"),
            )
        ],
    )

    task_results = []
    for task_plan in plan.tasks:
        task = Task(
            id=str(uuid.uuid4()),
            workspace_id=ctx.workspace_id,
            message_id=plan.message_id,
            execution_id=None,
            pack_id=task_plan.pack_id,
            task_type=task_plan.task_type,
            status=TaskStatus.PENDING if task_plan.requires_cta else TaskStatus.RUNNING,
            params=task_plan.params,
            result=None,
            created_at=_utc_now(),
            started_at=_utc_now() if not task_plan.requires_cta else None,
            completed_at=None,
            error=None,
        )
        handler.task_manager.tasks_store.create_task(task)
        task_results.append(
            {
                "task_id": task.id,
                "pack_id": task_plan.pack_id,
                "task_type": task_plan.task_type,
                "status": task.status.value,
                "requires_cta": task_plan.requires_cta,
            }
        )
    task_result = task_results[0] if task_results else None

    handler._create_user_event(
        ctx.workspace_id,
        ctx.actor_id,
        project_id,
        f"Use tool: {tool_name}",
        "use_tool",
        action_params,
    )

    return {
        "workspace_id": ctx.workspace_id,
        "display_events": [],
        "triggered_playbook": None,
        "pending_tasks": [task_result] if task_result else [],
    }
