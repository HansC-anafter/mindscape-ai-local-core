"""Chat dispatch helpers for meeting commands."""

from __future__ import annotations

from fastapi import BackgroundTasks

from backend.app.models.meeting_command import (
    MeetingCommandEnvelope,
    MeetingCommandRecord,
    MeetingCommandStatus,
)
from backend.app.models.workspace import Workspace, WorkspaceChatRequest
from backend.app.services.conversation_orchestrator import ConversationOrchestrator
from backend.app.services.meeting_command_dispatch_routing import (
    command_context_objects,
    command_instruction,
    metadata_action_parameters,
)


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
