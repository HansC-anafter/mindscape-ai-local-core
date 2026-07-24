"""Runtime dispatch facade for Meeting Workbench command-ledger rows."""

from __future__ import annotations

from typing import Any

from backend.app.models.meeting_command import (
    MeetingCommandEnvelope,
    MeetingCommandRecord,
)
from backend.app.models.workspace import Workspace
from backend.app.services.conversation_orchestrator import ConversationOrchestrator
from backend.app.services.meeting_command_dispatch_actions import (
    dispatch_object_action_for_command,
    dispatch_playbook_for_command,
)
from backend.app.services.meeting_command_dispatch_chat import (
    _run_chat_dispatch_and_sync_command,
    dispatch_chat_for_command,
)
from backend.app.services.meeting_command_dispatch_client_actions import (
    dispatch_client_action_for_command,
)
from backend.app.services.meeting_command_dispatch_orchestration import (
    _meeting_orchestration_timeout_result,
    _request_contract_aol_metadata,
)
from backend.app.services.meeting_command_dispatch_orchestration import (
    _run_meeting_orchestration_in_background as _run_meeting_orchestration_impl,
)
from backend.app.services.meeting_command_dispatch_orchestration import (
    dispatch_meeting_orchestration_for_command as _dispatch_meeting_orchestration_impl,
)
from backend.app.services.meeting_command_dispatch_routing import (
    _command_active_capability_code,
    _has_action_entries,
    _has_selected_guidance,
    _is_explicit_playbook_route,
    _is_motion_practice_playbook_command,
    _metadata_action_value,
    _truthy_flag,
    command_context_objects,
    command_instruction,
    explicit_direct_override,
    meeting_orchestration_timeout_seconds,
    metadata_action_parameters,
    requested_affordance_verb,
    should_route_chat,
    should_route_client_action,
    should_route_meeting_orchestration,
    should_route_object_action,
    should_route_playbook,
)


async def _run_meeting_orchestration_in_background(
    *,
    command_id: str,
    canonical: MeetingCommandEnvelope,
    session: Any,
    workspace: Workspace,
    store: Any,
    session_store: Any,
    command_store: Any,
    workspace_id: str,
) -> None:
    await _run_meeting_orchestration_impl(
        command_id=command_id,
        canonical=canonical,
        session=session,
        workspace=workspace,
        store=store,
        session_store=session_store,
        command_store=command_store,
        workspace_id=workspace_id,
        dispatch_handler=dispatch_meeting_orchestration_for_command,
    )


async def dispatch_meeting_orchestration_for_command(
    *,
    command: MeetingCommandRecord,
    canonical: MeetingCommandEnvelope,
    session: Any,
    workspace: Workspace,
    store: Any,
    session_store: Any,
    workspace_id: str,
) -> tuple[MeetingCommandRecord, dict]:
    return await _dispatch_meeting_orchestration_impl(
        command=command,
        canonical=canonical,
        session=session,
        workspace=workspace,
        store=store,
        session_store=session_store,
        workspace_id=workspace_id,
        timeout_seconds_resolver=meeting_orchestration_timeout_seconds,
    )


__all__ = [
    "_command_active_capability_code",
    "_has_action_entries",
    "_has_selected_guidance",
    "_is_explicit_playbook_route",
    "_is_motion_practice_playbook_command",
    "_meeting_orchestration_timeout_result",
    "_metadata_action_value",
    "_request_contract_aol_metadata",
    "_run_chat_dispatch_and_sync_command",
    "_run_meeting_orchestration_in_background",
    "_truthy_flag",
    "command_context_objects",
    "command_instruction",
    "dispatch_chat_for_command",
    "dispatch_client_action_for_command",
    "dispatch_meeting_orchestration_for_command",
    "dispatch_object_action_for_command",
    "dispatch_playbook_for_command",
    "explicit_direct_override",
    "meeting_orchestration_timeout_seconds",
    "metadata_action_parameters",
    "requested_affordance_verb",
    "should_route_chat",
    "should_route_client_action",
    "should_route_meeting_orchestration",
    "should_route_object_action",
    "should_route_playbook",
]
