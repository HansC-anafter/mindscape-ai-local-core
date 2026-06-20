"""Object-action and playbook dispatch helpers for meeting commands."""

from __future__ import annotations

from backend.app.models.meeting_command import (
    MeetingCommandEnvelope,
    MeetingCommandRecord,
    MeetingCommandStatus,
)
from backend.app.models.object_runtime import (
    ObjectActionInvokeRequest,
    ObjectActionPlanRequest,
)
from backend.app.models.workspace import Workspace
from backend.app.services.conversation_orchestrator import ConversationOrchestrator
from backend.app.services.meeting_command_dispatch_routing import (
    _is_motion_practice_playbook_command,
    command_context_objects,
    command_instruction,
    requested_affordance_verb,
)


async def dispatch_object_action_for_command(
    *,
    command: MeetingCommandRecord,
    canonical: MeetingCommandEnvelope,
    workspace_id: str,
    meeting_id: str,
) -> tuple[MeetingCommandRecord, dict]:
    from backend.app.routes.core.workspace import object_runtime

    instruction = command_instruction(canonical)
    request_context = {
        "command_id": command.command_id,
        "origin_surface": canonical.origin_surface,
        "source_surface": canonical.origin_surface,
        "dispatch_source": "meeting_command_route",
    }
    command.status = MeetingCommandStatus.RUNNING
    command.metadata = {
        **command.metadata,
        "dispatch_status": "running",
        "dispatch_mode": "route_object_action",
    }
    plan = await object_runtime.plan_workspace_object_action(
        ObjectActionPlanRequest(
            instruction=instruction,
            entries=canonical.context_objects,
            affordance_verb=requested_affordance_verb(canonical),
            write_mode=canonical.write_mode,
            meeting_id=meeting_id,
            request_context=request_context,
        ),
        workspace_id=workspace_id,
    )
    plan_payload = plan.model_dump(exclude_none=True)
    command.metadata = {
        **command.metadata,
        "object_action_plan": plan_payload,
    }
    if plan.status != "planned":
        command.status = MeetingCommandStatus.ACCEPTED
        command.metadata = {
            **command.metadata,
            "dispatch_status": "object_action_not_planned",
        }
        return command, {"object_action_plan": plan_payload}

    invoke = await object_runtime.invoke_workspace_object_action(
        ObjectActionInvokeRequest(
            instruction=instruction,
            object_action_plan=plan_payload,
            entries=canonical.context_objects,
            meeting_id=meeting_id,
            thread_id=canonical.thread_id or command.thread_id or meeting_id,
            request_context=request_context,
        ),
        workspace_id=workspace_id,
    )
    invoke_payload = invoke.model_dump(exclude_none=True)
    command.accepted_task_id = invoke.task_id
    command.status = (
        MeetingCommandStatus.FAILED
        if invoke.status == "failed"
        else MeetingCommandStatus.COMPLETED
    )
    command.metadata = {
        **command.metadata,
        "dispatch_status": "failed" if invoke.status == "failed" else "completed",
        "object_action": invoke_payload,
    }
    return command, {
        "object_action_plan": plan_payload,
        "object_action": invoke_payload,
    }


async def dispatch_playbook_for_command(
    *,
    command: MeetingCommandRecord,
    canonical: MeetingCommandEnvelope,
    workspace: Workspace,
    orchestrator: ConversationOrchestrator,
    meeting_id: str,
) -> tuple[MeetingCommandRecord, dict]:
    requested = canonical.requested_action
    playbook_code = requested.playbook_code if requested else None
    if not playbook_code:
        raise ValueError("playbook_code is required for route_playbook dispatch")

    instruction = command_instruction(canonical)
    thread_id = canonical.thread_id or command.thread_id or meeting_id
    motion_practice_command = _is_motion_practice_playbook_command(canonical)
    action_params = {
        **(requested.parameters if requested else {}),
        "playbook_code": playbook_code,
        "pack_code": requested.pack_code if requested else None,
        "instruction": instruction,
        "message": instruction,
        "command_id": command.command_id,
        "meeting_command_id": command.command_id,
        "command_ledger_status": command.status.value,
        "meeting_id": meeting_id,
        "meeting_session_id": meeting_id,
        "thread_id": thread_id,
        "meeting_command": instruction,
        "motion_practice_command": motion_practice_command,
        "meeting_mentions": canonical.meeting_mentions,
        "object_action_entries": command_context_objects(canonical),
        "source_surface": canonical.origin_surface,
        "request_context": {
            "command_id": command.command_id,
            "meeting_command_id": command.command_id,
            "origin_surface": canonical.origin_surface,
            "source_surface": canonical.origin_surface,
            "dispatch_source": "meeting_command_route",
            "dispatch_mode": "route_playbook",
            "motion_practice_command": motion_practice_command,
        },
    }
    command.status = MeetingCommandStatus.RUNNING
    command.metadata = {
        **command.metadata,
        "dispatch_status": "running",
        "dispatch_mode": "route_playbook",
    }

    result = await orchestrator.handle_suggestion_action(
        workspace_id=command.workspace_id,
        profile_id=workspace.owner_user_id,
        action="execute_playbook",
        action_params=action_params,
        project_id=workspace.primary_project_id,
        message_id=command.command_id,
    )
    task_id = (
        result.get("task_id")
        or (result.get("triggered_playbook") or {}).get("execution_id")
        if isinstance(result, dict)
        else None
    )
    command.accepted_task_id = task_id
    dispatch_failed = not isinstance(result, dict) or not result.get("triggered_playbook")
    command.status = (
        MeetingCommandStatus.FAILED if dispatch_failed else MeetingCommandStatus.ACCEPTED
    )
    command.metadata = {
        **command.metadata,
        "dispatch_status": "failed" if dispatch_failed else "accepted",
        "playbook_dispatch": result if isinstance(result, dict) else {"result": result},
    }
    return command, {"playbook": result if isinstance(result, dict) else {"result": result}}
