"""Bounded voice turn ingress for Meeting Engine commands."""

from __future__ import annotations

import base64
import hashlib
from typing import Any, Awaitable, Callable

from fastapi import BackgroundTasks

from backend.app.models.meeting_voice import (
    MeetingVoiceTurnRequest,
    MeetingVoiceTurnResponse,
)
from backend.app.models.meeting_voice_context import (
    normalize_meeting_voice_command_context,
)
from backend.app.models.workspace import Workspace
from backend.app.services.conversation_orchestrator import ConversationOrchestrator
from backend.app.services.host_services.whisper_proxy import (
    MAX_STT_AUDIO_BYTES,
    WhisperTranscriptionRequest,
    WhisperTranscriptionResult,
    WhisperTranscriptionUnavailable,
    transcribe_whisper_audio,
)
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.orchestration.meeting.meeting_command_submission import (
    MeetingCommandSubmissionService,
    validate_meeting_session,
)
from backend.app.services.orchestration.meeting.voice_client_actions import (
    build_voice_command_envelope,
    resolve_voice_client_action,
)

SUPPORTED_VOICE_TURN_MIME_TYPES = {"audio/mp4", "audio/webm", "audio/wav"}
SUPPORTED_VOICE_TURN_MIME_LABEL = "audio/mp4, audio/webm, or audio/wav"


class MeetingVoiceIngressError(Exception):
    """HTTP-safe voice ingress validation error."""

    def __init__(self, *, status_code: int, detail: dict[str, Any]) -> None:
        super().__init__(detail.get("message") or detail.get("code"))
        self.status_code = status_code
        self.detail = detail


def voice_error_detail(code: str, message: str, **extra):
    return {"code": code, "message": message, **extra}


def normalized_mime_type(value: str) -> str:
    return value.split(";", 1)[0].strip().lower()


def decode_audio_base64(value: str) -> bytes:
    try:
        audio_bytes = base64.b64decode(value, validate=True)
    except Exception as exc:
        raise MeetingVoiceIngressError(
            status_code=422,
            detail=voice_error_detail(
                "invalid_audio_base64",
                "Voice turn audio_base64 must be valid base64.",
            ),
        ) from exc
    if not audio_bytes:
        raise MeetingVoiceIngressError(
            status_code=422,
            detail=voice_error_detail(
                "empty_audio",
                "Voice turn audio_base64 must contain audio bytes.",
            ),
        )
    if len(audio_bytes) > MAX_STT_AUDIO_BYTES:
        raise MeetingVoiceIngressError(
            status_code=422,
            detail=voice_error_detail(
                "audio_too_large",
                "Voice turn audio exceeds the maximum audio byte limit.",
                max_audio_bytes=MAX_STT_AUDIO_BYTES,
            ),
        )
    return audio_bytes


class MeetingVoiceIngressService:
    """Transcribe one bounded voice turn and submit a meeting command."""

    def __init__(
        self,
        *,
        transcriber: Callable[
            [WhisperTranscriptionRequest],
            Awaitable[WhisperTranscriptionResult],
        ] = transcribe_whisper_audio,
        submission_service: MeetingCommandSubmissionService | None = None,
    ) -> None:
        self.transcriber = transcriber
        self.submission_service = submission_service

    async def submit_voice_turn(
        self,
        *,
        request: MeetingVoiceTurnRequest,
        workspace_id: str,
        meeting_id: str,
        workspace: Workspace,
        orchestrator: ConversationOrchestrator,
        mindscape_store: MindscapeStore,
        background_tasks: BackgroundTasks | None = None,
    ) -> MeetingVoiceTurnResponse:
        mime_type = normalized_mime_type(request.mime_type)
        if mime_type not in SUPPORTED_VOICE_TURN_MIME_TYPES:
            raise MeetingVoiceIngressError(
                status_code=422,
                detail=voice_error_detail(
                    "unsupported_audio_mime_type",
                    f"Voice turn supports {SUPPORTED_VOICE_TURN_MIME_LABEL}.",
                    mime_type=request.mime_type,
                ),
            )

        audio_bytes = decode_audio_base64(request.audio_base64)
        try:
            command_context = normalize_meeting_voice_command_context(
                command_context=request.command_context,
                context_objects=request.context_objects,
                metadata=request.metadata,
            )
        except ValueError as exc:
            raise MeetingVoiceIngressError(
                status_code=422,
                detail=voice_error_detail(
                    "conflicting_command_context",
                    "Voice turn must use command_context or legacy context, not both.",
                ),
            ) from exc
        service = self.submission_service or MeetingCommandSubmissionService()
        session = validate_meeting_session(
            workspace_id=workspace_id,
            meeting_id=meeting_id,
            session_store=service.session_store,
        )

        try:
            transcription = await self.transcriber(
                WhisperTranscriptionRequest(
                    audio_base64=request.audio_base64,
                    language=request.language or "auto",
                )
            )
        except WhisperTranscriptionUnavailable as exc:
            return MeetingVoiceTurnResponse(
                status="stt_unavailable",
                reason=exc.reason,
                audio_byte_count=len(audio_bytes),
            )

        transcript = transcription.text.strip()
        if not transcript:
            return MeetingVoiceTurnResponse(
                status="ignored_empty_transcript",
                transcript="",
                language=transcription.language,
                duration=transcription.duration,
                audio_byte_count=len(audio_bytes),
                reason="empty_transcript",
            )

        command_response = await service.submit_envelope(
            envelope=build_voice_command_envelope(
                workspace_id=workspace_id,
                meeting_id=meeting_id,
                origin_surface="meeting_voice",
                transcript=transcript,
                context_objects=command_context.context_objects,
                command_context=command_context,
                resolution=resolve_voice_client_action(
                    transcript=transcript,
                    session=session,
                ),
                metadata={
                    "client_turn_id": request.client_turn_id,
                    "transcript_hash": hashlib.sha256(
                        transcript.encode("utf-8")
                    ).hexdigest(),
                    "stt_language": transcription.language,
                    "stt_duration": transcription.duration,
                    "audio_mime_type": mime_type,
                    "audio_byte_count": len(audio_bytes),
                },
            ),
            workspace_id=workspace_id,
            meeting_id=meeting_id,
            workspace=workspace,
            orchestrator=orchestrator,
            mindscape_store=mindscape_store,
            background_tasks=background_tasks,
        )
        return MeetingVoiceTurnResponse(
            status="transcribed_command_submitted",
            transcript=transcript,
            language=transcription.language,
            duration=transcription.duration,
            audio_byte_count=len(audio_bytes),
            command_response=command_response,
        )


__all__ = [
    "MeetingVoiceIngressError",
    "MeetingVoiceIngressService",
    "SUPPORTED_VOICE_TURN_MIME_LABEL",
    "SUPPORTED_VOICE_TURN_MIME_TYPES",
    "decode_audio_base64",
    "normalized_mime_type",
    "voice_error_detail",
]
