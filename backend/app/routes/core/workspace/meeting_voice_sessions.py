"""Workspace-scoped Meeting Engine realtime voice session WebSocket."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from backend.app.models.meeting_voice_session import (
    MeetingVoiceAudioWindow,
    MeetingVoiceSessionClientMessage,
    MeetingVoiceSessionEvent,
    MeetingVoiceTranscriptCandidate,
)
from backend.app.models.workspace import Workspace
from backend.app.routes.workspace_dependencies import get_orchestrator, get_store, get_workspace
from backend.app.services.conversation_orchestrator import ConversationOrchestrator
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.orchestration.meeting.meeting_command_submission import (
    MeetingCommandSubmissionError,
)
from backend.app.services.orchestration.meeting.realtime_voice_transcriber import (
    RealtimeVoiceTranscriber,
    RealtimeVoiceTranscriptionError,
)
from backend.app.services.orchestration.meeting.voice_session_registry import (
    MeetingVoiceSessionEntry,
    MeetingVoiceSessionRegistry,
    MeetingVoiceSessionRegistryError,
    get_meeting_voice_session_registry,
)

router = APIRouter()


def get_realtime_voice_transcriber() -> RealtimeVoiceTranscriber:
    return RealtimeVoiceTranscriber()


async def _send_event(websocket: WebSocket, event: MeetingVoiceSessionEvent) -> None:
    await websocket.send_text(json.dumps(event.model_dump(mode="json", exclude_none=True)))


def _event(
    *,
    event_type: str,
    entry: MeetingVoiceSessionEntry,
    **extra: Any,
) -> MeetingVoiceSessionEvent:
    return MeetingVoiceSessionEvent(
        type=event_type,
        workspace_id=entry.workspace_id,
        meeting_id=entry.meeting_id,
        client_session_id=entry.client_session_id,
        state=entry.state,
        **extra,
    )


async def _send_session_error(
    websocket: WebSocket,
    entry: MeetingVoiceSessionEntry,
    *,
    reason: str,
    message: str,
    recoverable: bool,
) -> None:
    await _send_event(
        websocket,
        _event(
            event_type="session_error",
            entry=entry,
            reason=reason,
            message=message,
            recoverable=recoverable,
        ),
    )


@router.websocket(
    "/{workspace_id}/meetings/{meeting_id}/voice-sessions/{client_session_id}/stream"
)
async def stream_meeting_voice_session(
    websocket: WebSocket,
    workspace_id: str,
    meeting_id: str,
    client_session_id: str,
    workspace: Workspace = Depends(get_workspace),
    orchestrator: ConversationOrchestrator = Depends(get_orchestrator),
    mindscape_store: MindscapeStore = Depends(get_store),
    registry: MeetingVoiceSessionRegistry = Depends(get_meeting_voice_session_registry),
    transcriber: RealtimeVoiceTranscriber = Depends(get_realtime_voice_transcriber),
) -> None:
    """Run one realtime voice session over a single WebSocket."""

    await websocket.accept()
    try:
        entry = registry.connect(
            workspace_id=workspace_id,
            meeting_id=meeting_id,
            client_session_id=client_session_id,
            websocket=websocket,
        )
    except MeetingVoiceSessionRegistryError as exc:
        fallback_entry = MeetingVoiceSessionEntry(
            key=f"{workspace_id}:{meeting_id}:{client_session_id}",
            workspace_id=workspace_id,
            meeting_id=meeting_id,
            client_session_id=client_session_id,
            websocket=websocket,
            state="closed",
            created_at_epoch=0,
            updated_at_epoch=0,
        )
        await _send_session_error(
            websocket,
            fallback_entry,
            reason=exc.reason,
            message=exc.message,
            recoverable=False,
        )
        await websocket.close(code=4409, reason=exc.reason)
        return

    pending: dict[str, MeetingVoiceTranscriptCandidate] = {}
    close_sent = False
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
                message = MeetingVoiceSessionClientMessage.model_validate(payload)
            except json.JSONDecodeError:
                await _send_session_error(
                    websocket,
                    entry,
                    reason="invalid_json",
                    message="Realtime voice session messages must be JSON.",
                    recoverable=True,
                )
                continue
            except ValidationError as exc:
                await _send_session_error(
                    websocket,
                    entry,
                    reason="invalid_message",
                    message=str(exc.errors()[0].get("msg") or "Invalid message."),
                    recoverable=True,
                )
                continue

            if message.type == "session_start":
                entry = registry.update_state(entry, "listening")
                await _send_event(
                    websocket,
                    _event(event_type="session_ready", entry=entry),
                )
                continue

            if message.type == "audio_window":
                if not message.utterance_id or not message.audio_base64 or not message.mime_type:
                    await _send_session_error(
                        websocket,
                        entry,
                        reason="invalid_audio_window",
                        message="audio_window requires utterance_id, audio_base64, and mime_type.",
                        recoverable=True,
                    )
                    continue
                entry = registry.update_state(entry, "transcribing")
                try:
                    candidate = await transcriber.transcribe_audio_window(
                        window=MeetingVoiceAudioWindow(
                            client_session_id=client_session_id,
                            utterance_id=message.utterance_id,
                            audio_base64=message.audio_base64,
                            mime_type=message.mime_type,
                            language=message.language or "auto",
                            context_objects=message.context_objects,
                            metadata=message.metadata,
                        )
                    )
                except RealtimeVoiceTranscriptionError as exc:
                    await _send_session_error(
                        websocket,
                        entry,
                        reason=exc.reason,
                        message=exc.message,
                        recoverable=exc.recoverable,
                    )
                    if exc.close_session:
                        close_sent = True
                        await websocket.close(code=4400, reason=exc.reason)
                        break
                    entry = registry.update_state(entry, "listening")
                    continue

                pending[candidate.utterance_id] = candidate
                entry = registry.update_state(entry, "listening")
                await _send_event(
                    websocket,
                    _event(
                        event_type="transcript_candidate",
                        entry=entry,
                        utterance_id=candidate.utterance_id,
                        transcript=candidate.transcript,
                        language=candidate.language,
                        duration=candidate.duration,
                        audio_byte_count=candidate.audio_byte_count,
                    ),
                )
                continue

            if message.type == "utterance_end":
                if not message.utterance_id:
                    await _send_session_error(
                        websocket,
                        entry,
                        reason="missing_utterance_id",
                        message="utterance_end requires utterance_id.",
                        recoverable=True,
                    )
                    continue
                candidate = pending.pop(message.utterance_id, None)
                if candidate is None:
                    await _send_session_error(
                        websocket,
                        entry,
                        reason="unknown_utterance",
                        message="No transcript candidate exists for this utterance_id.",
                        recoverable=True,
                    )
                    continue
                await _send_event(
                    websocket,
                    _event(
                        event_type="transcript_final",
                        entry=entry,
                        utterance_id=candidate.utterance_id,
                        transcript=candidate.transcript,
                        language=candidate.language,
                        duration=candidate.duration,
                        audio_byte_count=candidate.audio_byte_count,
                    ),
                )
                try:
                    command_response = await transcriber.submit_final_transcript(
                        candidate=candidate,
                        workspace_id=workspace_id,
                        meeting_id=meeting_id,
                        workspace=workspace,
                        orchestrator=orchestrator,
                        mindscape_store=mindscape_store,
                    )
                except MeetingCommandSubmissionError as exc:
                    await _send_session_error(
                        websocket,
                        entry,
                        reason=str(exc.detail.get("code") or "command_submission_failed"),
                        message=str(exc.detail.get("message") or "Command submission failed."),
                        recoverable=True,
                    )
                    continue
                await _send_event(
                    websocket,
                    _event(
                        event_type="command_submitted",
                        entry=entry,
                        utterance_id=candidate.utterance_id,
                        command_response=command_response,
                    ),
                )
                continue

            if message.type == "interrupt":
                pending.clear()
                entry = registry.update_state(entry, "interrupted")
                await _send_event(websocket, _event(event_type="interrupted", entry=entry))
                entry = registry.update_state(entry, "listening")
                continue

            if message.type == "cancel":
                pending.clear()
                entry = registry.update_state(entry, "listening")
                await _send_event(websocket, _event(event_type="cancelled", entry=entry))
                continue

            if message.type == "ack":
                continue

            if message.type == "session_close":
                entry = registry.update_state(entry, "closed")
                await _send_event(
                    websocket,
                    _event(event_type="session_closed", entry=entry),
                )
                registry.close(entry)
                close_sent = True
                await websocket.close(code=1000, reason="session_closed")
                break
    except WebSocketDisconnect:
        pass
    finally:
        registry.close(entry)
        if not close_sent:
            try:
                await websocket.close()
            except Exception:
                pass


__all__ = [
    "get_realtime_voice_transcriber",
    "stream_meeting_voice_session",
    "router",
]
