"""Realtime voice session transcription for bounded utterance windows."""

from __future__ import annotations

import hashlib
from typing import Any, Awaitable, Callable

from backend.app.models.meeting_voice_session import (
    MeetingVoiceAudioWindow,
    MeetingVoiceTranscriptCandidate,
)
from backend.app.models.meeting_voice_context import (
    normalize_meeting_voice_command_context,
)
from backend.app.models.workspace import Workspace
from backend.app.services.conversation_orchestrator import ConversationOrchestrator
from backend.app.services.host_services.whisper_proxy import (
    WhisperTranscriptionRequest,
    WhisperTranscriptionResult,
    WhisperTranscriptionUnavailable,
    transcribe_whisper_audio,
)
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.orchestration.meeting.meeting_command_submission import (
    MeetingCommandSubmissionService,
)
from backend.app.services.orchestration.meeting.voice_ingress import (
    SUPPORTED_VOICE_TURN_MIME_LABEL,
    SUPPORTED_VOICE_TURN_MIME_TYPES,
    MeetingVoiceIngressError,
    decode_audio_base64,
    normalized_mime_type,
)
from backend.app.services.orchestration.meeting.workspace_voice_semantic_turn_facade import (
    WorkspaceVoiceSemanticTurnFacade,
)


class RealtimeVoiceTranscriptionError(Exception):
    """Recoverable or closing error for realtime voice transcription."""

    def __init__(
        self,
        *,
        reason: str,
        message: str,
        recoverable: bool,
        close_session: bool = False,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message
        self.recoverable = recoverable
        self.close_session = close_session


class RealtimeVoiceTranscriber:
    """Transcribe bounded voice windows and submit final transcripts."""

    def __init__(
        self,
        *,
        transcriber: Callable[
            [WhisperTranscriptionRequest],
            Awaitable[WhisperTranscriptionResult],
        ] = transcribe_whisper_audio,
        submission_service: MeetingCommandSubmissionService | None = None,
        semantic_facade: WorkspaceVoiceSemanticTurnFacade | None = None,
    ) -> None:
        self.transcriber = transcriber
        self.submission_service = submission_service
        self.semantic_facade = semantic_facade

    async def transcribe_audio_window(
        self,
        *,
        window: MeetingVoiceAudioWindow,
    ) -> MeetingVoiceTranscriptCandidate:
        mime_type = normalized_mime_type(window.mime_type)
        if mime_type not in SUPPORTED_VOICE_TURN_MIME_TYPES:
            raise RealtimeVoiceTranscriptionError(
                reason="unsupported_audio_mime_type",
                message=(
                    "Realtime voice session supports "
                    f"{SUPPORTED_VOICE_TURN_MIME_LABEL}."
                ),
                recoverable=False,
                close_session=True,
            )

        try:
            audio_bytes = decode_audio_base64(window.audio_base64)
        except MeetingVoiceIngressError as exc:
            detail = exc.detail
            raise RealtimeVoiceTranscriptionError(
                reason=str(detail.get("code") or "invalid_audio"),
                message=str(detail.get("message") or "Invalid realtime voice audio."),
                recoverable=False,
                close_session=True,
            ) from exc
        try:
            command_context = normalize_meeting_voice_command_context(
                command_context=window.command_context,
                context_objects=window.context_objects,
                metadata=window.metadata,
            )
        except ValueError as exc:
            raise RealtimeVoiceTranscriptionError(
                reason="conflicting_command_context",
                message="Realtime voice window must use command_context or legacy context, not both.",
                recoverable=False,
                close_session=True,
            ) from exc

        try:
            transcription = await self.transcriber(
                WhisperTranscriptionRequest(
                    audio_base64=window.audio_base64,
                    language=window.language or "auto",
                )
            )
        except WhisperTranscriptionUnavailable as exc:
            raise RealtimeVoiceTranscriptionError(
                reason=exc.reason,
                message="Realtime voice transcription is unavailable.",
                recoverable=True,
            ) from exc

        transcript = transcription.text.strip()
        if not transcript:
            raise RealtimeVoiceTranscriptionError(
                reason="empty_transcript",
                message="Realtime voice utterance did not contain a transcript.",
                recoverable=True,
            )

        return MeetingVoiceTranscriptCandidate(
            client_session_id=window.client_session_id,
            utterance_id=window.utterance_id,
            transcript=transcript,
            language=transcription.language,
            duration=transcription.duration,
            audio_mime_type=mime_type,
            audio_byte_count=len(audio_bytes),
            command_context=command_context,
            context_objects=command_context.context_objects,
            metadata={
                "client_metadata": window.metadata,
                "transcript_hash": hashlib.sha256(
                    transcript.encode("utf-8")
                ).hexdigest(),
            },
        )

    async def submit_final_transcript(
        self,
        *,
        candidate: MeetingVoiceTranscriptCandidate,
        workspace_id: str,
        meeting_id: str,
        workspace: Workspace,
        orchestrator: ConversationOrchestrator,
        mindscape_store: MindscapeStore,
    ):
        service = self.submission_service or MeetingCommandSubmissionService()
        session = service.session_store.get_by_id(meeting_id)
        semantic_facade = self.semantic_facade or WorkspaceVoiceSemanticTurnFacade(
            submission_service=service,
        )
        return await semantic_facade.submit_final_transcript(
            transcript=candidate.transcript,
            language=candidate.language,
            command_context=candidate.command_context
            or normalize_meeting_voice_command_context(
                command_context=None,
                context_objects=candidate.context_objects,
                metadata={},
            ),
            session=session,
            workspace_id=workspace_id,
            meeting_id=meeting_id,
            origin_surface="meeting_voice_session",
            transport_metadata={
                "client_session_id": candidate.client_session_id,
                "utterance_id": candidate.utterance_id,
                "transcript_hash": candidate.metadata.get("transcript_hash"),
                "stt_language": candidate.language,
                "stt_duration": candidate.duration,
                "audio_mime_type": candidate.audio_mime_type,
                "audio_byte_count": candidate.audio_byte_count,
                "protocol": "realtime_voice_session",
            },
            workspace=workspace,
            orchestrator=orchestrator,
            mindscape_store=mindscape_store,
        )


__all__ = [
    "RealtimeVoiceTranscriber",
    "RealtimeVoiceTranscriptionError",
]
