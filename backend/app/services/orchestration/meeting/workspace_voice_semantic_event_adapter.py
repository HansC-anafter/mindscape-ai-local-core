"""Project one typed Workspace voice semantic result into a Meeting event."""

from __future__ import annotations

from backend.app.models.meeting_voice_session import MeetingVoiceSessionEvent
from backend.app.models.workspace_voice_semantic_turn import (
    WorkspaceVoiceSemanticTurnResult,
)
from backend.app.services.orchestration.meeting.voice_session_registry import (
    MeetingVoiceSessionEntry,
)


def workspace_voice_semantic_event(
    *,
    result: WorkspaceVoiceSemanticTurnResult,
    entry: MeetingVoiceSessionEntry,
    utterance_id: str,
) -> MeetingVoiceSessionEvent:
    """Return an accepted event only when the canonical command receipt exists."""

    command_submitted = (
        result.status == "command_submitted"
        and result.command_response is not None
    )
    return MeetingVoiceSessionEvent(
        type="command_submitted" if command_submitted else "semantic_clarification",
        workspace_id=entry.workspace_id,
        meeting_id=entry.meeting_id,
        client_session_id=entry.client_session_id,
        state=entry.state,
        utterance_id=utterance_id,
        command_response=result.command_response if command_submitted else None,
        semantic_result=result,
        reason=None if command_submitted else result.decision_code,
    )


__all__ = ["workspace_voice_semantic_event"]
