"""Resolve pack-declared voice intents into bounded AOL client actions."""

from __future__ import annotations

import copy
from typing import Any, Mapping

from backend.app.models.meeting_command import (
    MeetingCommandEnvelope,
    MeetingRequestedAction,
)
from backend.app.models.meeting_voice_context import MeetingVoiceCommandContext
from backend.app.models.workspace_voice_semantic_turn import (
    WorkspaceVoiceClientAction,
)
from backend.app.services.orchestration.meeting.active_pack_voice_interaction_port import (
    resolve_legacy_voice_client_action,
)


CLIENT_ACTION_SCHEMA_VERSION = "aol.client_action.v1"
VoiceClientActionResolution = WorkspaceVoiceClientAction


def resolve_voice_client_action(
    *,
    transcript: str,
    session: Any,
    registry: Any | None = None,
) -> VoiceClientActionResolution | None:
    return resolve_legacy_voice_client_action(
        transcript=transcript,
        session=session,
        registry=registry,
    )


def build_voice_command_envelope(
    *,
    workspace_id: str,
    meeting_id: str,
    origin_surface: str,
    transcript: str,
    metadata: Mapping[str, Any],
    context_objects: list[Any],
    resolution: VoiceClientActionResolution | None,
    command_context: MeetingVoiceCommandContext | None = None,
) -> MeetingCommandEnvelope:
    context = command_context or MeetingVoiceCommandContext(
        context_objects=context_objects,
    )
    context_metadata = copy.deepcopy(context.metadata)
    context_metadata.update(dict(metadata))
    context_metadata["raw_intent_text"] = transcript
    action_parameters = context_metadata.get("action_parameters")
    if isinstance(action_parameters, Mapping):
        normalized_action_parameters = copy.deepcopy(dict(action_parameters))
        normalized_action_parameters["meeting_command"] = transcript
        context_metadata["action_parameters"] = normalized_action_parameters
    requested_action = context.requested_action.model_copy(deep=True) \
        if context.requested_action is not None else None
    if requested_action is not None:
        requested_action.parameters["instruction"] = transcript
        requested_action.parameters["message"] = transcript
        if "meeting_command" in requested_action.parameters:
            requested_action.parameters["meeting_command"] = transcript

    if resolution is None:
        return MeetingCommandEnvelope(
            workspace_id=workspace_id,
            meeting_id=meeting_id,
            origin_surface=origin_surface,
            actor="user",
            intent_text=transcript,
            context_objects=context.context_objects,
            requested_action=requested_action,
            expected_outputs=context.expected_outputs,
            write_mode=context.write_mode,
            thread_id=context.thread_id,
            meeting_mentions=context.meeting_mentions,
            metadata=context_metadata,
        )
    if requested_action is not None:
        return MeetingCommandEnvelope(
            workspace_id=workspace_id,
            meeting_id=meeting_id,
            origin_surface=origin_surface,
            actor="user",
            intent_text=transcript,
            context_objects=context.context_objects,
            requested_action=requested_action,
            expected_outputs=context.expected_outputs,
            write_mode=context.write_mode,
            thread_id=context.thread_id,
            meeting_mentions=context.meeting_mentions,
            metadata=context_metadata,
        )
    client_action = {
        "schema_version": CLIENT_ACTION_SCHEMA_VERSION,
        "pack_code": resolution.pack_code,
        "intent_code": resolution.intent_code,
        "action_code": resolution.action_code,
        "requires_confirmation": resolution.requires_confirmation,
        "payload": resolution.payload,
    }
    return MeetingCommandEnvelope(
        workspace_id=workspace_id,
        meeting_id=meeting_id,
        origin_surface=origin_surface,
        actor="user",
        intent_text=transcript,
        context_objects=context.context_objects,
        requested_action=MeetingRequestedAction(
            verb="client_action",
            pack_code=resolution.pack_code,
            affordance_verb=resolution.action_code,
            write_mode="recommendation_only",
            parameters={"client_action": client_action},
        ),
        expected_outputs=context.expected_outputs,
        write_mode=context.write_mode,
        thread_id=context.thread_id,
        meeting_mentions=context.meeting_mentions,
        metadata={
            **context_metadata,
            "dispatch_mode": "route_client_action",
            "explicit_override": True,
            "active_pack_code": resolution.pack_code,
            "client_action": client_action,
        },
    )


__all__ = [
    "CLIENT_ACTION_SCHEMA_VERSION",
    "VoiceClientActionResolution",
    "build_voice_command_envelope",
    "resolve_voice_client_action",
]
