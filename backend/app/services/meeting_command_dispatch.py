"""Runtime dispatch helpers for Meeting Workbench command-ledger rows."""

from __future__ import annotations

from fastapi import BackgroundTasks

from backend.app.models.meeting_command import (
    MeetingCommandEnvelope,
    MeetingCommandRecord,
    MeetingCommandStatus,
)
from backend.app.models.object_runtime import (
    ObjectActionInvokeRequest,
    ObjectActionPlanRequest,
)
from backend.app.models.workspace import Workspace, WorkspaceChatRequest
from backend.app.services.conversation_orchestrator import ConversationOrchestrator


def command_instruction(canonical: MeetingCommandEnvelope) -> str:
    raw_intent = canonical.metadata.get("raw_intent_text")
    if isinstance(raw_intent, str) and raw_intent.strip():
        return raw_intent.strip()
    return canonical.intent_text


def requested_affordance_verb(canonical: MeetingCommandEnvelope) -> str | None:
    requested = canonical.requested_action
    if requested is None:
        return None
    if requested.affordance_verb:
        return requested.affordance_verb
    if requested.verb and requested.verb not in {"execute_playbook", "command"}:
        return requested.verb
    return None


def should_route_object_action(canonical: MeetingCommandEnvelope) -> bool:
    return (
        canonical.metadata.get("dispatch_mode") == "route_object_action"
        and len(canonical.context_objects) >= 2
        and not (canonical.requested_action and canonical.requested_action.playbook_code)
    )


def should_route_playbook(canonical: MeetingCommandEnvelope) -> bool:
    return (
        canonical.metadata.get("dispatch_mode") == "route_playbook"
        and canonical.requested_action is not None
        and bool(canonical.requested_action.playbook_code)
    )


def should_route_chat(canonical: MeetingCommandEnvelope) -> bool:
    return (
        canonical.metadata.get("dispatch_mode") == "route_chat"
        and not (canonical.requested_action and canonical.requested_action.playbook_code)
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


def command_context_objects(canonical: MeetingCommandEnvelope) -> list[dict]:
    return [entry.model_dump(exclude_none=True) for entry in canonical.context_objects]


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
    action_params = {
        **(requested.parameters if requested else {}),
        "playbook_code": playbook_code,
        "pack_code": requested.pack_code if requested else None,
        "instruction": instruction,
        "message": instruction,
        "command_id": command.command_id,
        "command_ledger_status": command.status.value,
        "meeting_id": meeting_id,
        "meeting_session_id": meeting_id,
        "thread_id": thread_id,
        "meeting_command": instruction,
        "meeting_mentions": canonical.meeting_mentions,
        "object_action_entries": command_context_objects(canonical),
        "source_surface": canonical.origin_surface,
        "request_context": {
            "command_id": command.command_id,
            "origin_surface": canonical.origin_surface,
            "source_surface": canonical.origin_surface,
            "dispatch_source": "meeting_command_route",
            "dispatch_mode": "route_playbook",
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


def metadata_action_parameters(canonical: MeetingCommandEnvelope) -> dict:
    action_parameters = canonical.metadata.get("action_parameters")
    return action_parameters if isinstance(action_parameters, dict) else {}


async def _run_chat_dispatch_and_sync_command(
    *,
    service,
    command_id: str,
    request: WorkspaceChatRequest,
    workspace: Workspace,
    workspace_id: str,
    profile_id: str,
    user_event_id: str,
) -> None:
    from backend.app.services.stores.meeting_command_store import MeetingCommandStore

    error = None
    try:
        await service.run_background_chat(
            request=request,
            workspace=workspace,
            workspace_id=workspace_id,
            profile_id=profile_id,
            user_event_id=user_event_id,
        )
        status = MeetingCommandStatus.COMPLETED
        dispatch_status = "completed"
    except Exception as exc:
        error = str(exc)
        status = MeetingCommandStatus.FAILED
        dispatch_status = "failed"

    store = MeetingCommandStore()
    command = store.get(command_id)
    if command is None:
        return
    chat_dispatch = dict(command.metadata.get("chat_dispatch") or {})
    chat_dispatch.update(
        {
            "status": dispatch_status,
            "task_id": user_event_id,
            "event_id": user_event_id,
            "thread_id": request.thread_id,
        }
    )
    if error:
        chat_dispatch["error"] = error
    command.status = status
    command.metadata = {
        **command.metadata,
        "dispatch_status": dispatch_status,
        "chat_dispatch": chat_dispatch,
    }
    store.save(command)


async def dispatch_chat_for_command(
    *,
    command: MeetingCommandRecord,
    canonical: MeetingCommandEnvelope,
    workspace: Workspace,
    orchestrator: ConversationOrchestrator,
    meeting_id: str,
    background_tasks: BackgroundTasks | None,
) -> tuple[MeetingCommandRecord, dict]:
    from backend.app.services.chat_orchestrator_service import ChatOrchestratorService

    instruction = command_instruction(canonical)
    thread_id = canonical.thread_id or command.thread_id or meeting_id
    action_params = {
        **metadata_action_parameters(canonical),
        "command_id": command.command_id,
        "command_ledger_status": command.status.value,
        "meeting_id": meeting_id,
        "meeting_session_id": meeting_id,
        "thread_id": thread_id,
        "meeting_command": instruction,
        "meeting_mentions": canonical.meeting_mentions,
        "object_action_entries": command_context_objects(canonical),
        "source_surface": canonical.origin_surface,
        "request_context": {
            "command_id": command.command_id,
            "origin_surface": canonical.origin_surface,
            "source_surface": canonical.origin_surface,
            "dispatch_source": "meeting_command_route",
            "dispatch_mode": "route_chat",
        },
    }
    request = WorkspaceChatRequest(
        message=f"Meeting graph command for attached object context: {instruction}",
        files=[],
        mode="auto",
        stream=True,
        project_id=workspace.primary_project_id,
        thread_id=thread_id,
        action_params=action_params,
    )
    service = ChatOrchestratorService(orchestrator)
    command.status = MeetingCommandStatus.RUNNING
    command.metadata = {
        **command.metadata,
        "dispatch_status": "running",
        "dispatch_mode": "route_chat",
    }
    event_id = command.command_id
    if background_tasks is not None:
        background_tasks.add_task(
            _run_chat_dispatch_and_sync_command,
            service=service,
            command_id=command.command_id,
            request=request,
            workspace=workspace,
            workspace_id=command.workspace_id,
            profile_id=workspace.owner_user_id,
            user_event_id=event_id,
        )
        dispatch_status = "accepted"
    else:
        await _run_chat_dispatch_and_sync_command(
            service=service,
            command_id=command.command_id,
            request=request,
            workspace=workspace,
            workspace_id=command.workspace_id,
            profile_id=workspace.owner_user_id,
            user_event_id=event_id,
        )
        command.status = MeetingCommandStatus.COMPLETED
        dispatch_status = "completed"

    command.accepted_task_id = event_id
    if dispatch_status == "accepted":
        command.status = MeetingCommandStatus.ACCEPTED
    command.metadata = {
        **command.metadata,
        "dispatch_status": dispatch_status,
        "chat_dispatch": {
            "status": dispatch_status,
            "task_id": event_id,
            "event_id": event_id,
            "thread_id": thread_id,
        },
    }
    return command, {
        "chat": {
            "status": dispatch_status,
            "task_id": event_id,
            "event_id": event_id,
            "thread_id": thread_id,
        }
    }
