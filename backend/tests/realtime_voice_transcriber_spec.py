from __future__ import annotations

import base64
from types import SimpleNamespace

import pytest

from backend.app.models.meeting_command import (
    MeetingCommandAcceptResponse,
    MeetingCommandRecord,
    MeetingCommandStatus,
)
from backend.app.models.meeting_session import MeetingSession
from backend.app.models.meeting_voice_session import MeetingVoiceAudioWindow
from backend.app.services.host_services.whisper_proxy import WhisperTranscriptionResult
from backend.app.services.orchestration.meeting.realtime_voice_transcriber import (
    RealtimeVoiceTranscriber,
    RealtimeVoiceTranscriptionError,
)


def _audio_base64() -> str:
    return base64.b64encode(b"RIFF....WAVE").decode("ascii")


class _FakeSessionStore:
    def __init__(self) -> None:
        self.session = MeetingSession.new(workspace_id="ws_voice")
        self.session.id = "mtg_voice"

    def get_by_id(self, meeting_id):
        if meeting_id == self.session.id:
            return self.session
        return None


class _FakeSubmissionService:
    def __init__(self) -> None:
        self.session_store = _FakeSessionStore()
        self.envelopes = []

    async def submit_envelope(self, **kwargs):
        envelope = kwargs["envelope"]
        self.envelopes.append(envelope)
        command = MeetingCommandRecord(
            command_id="cmd_voice_session",
            workspace_id=kwargs["workspace_id"],
            meeting_id=kwargs["meeting_id"],
            origin_surface=envelope.origin_surface,
            actor=envelope.actor,
            intent_text=envelope.intent_text,
            status=MeetingCommandStatus.ACCEPTED,
            metadata=envelope.metadata,
        )
        return MeetingCommandAcceptResponse(
            workspace_id=kwargs["workspace_id"],
            meeting_id=kwargs["meeting_id"],
            command_id="cmd_voice_session",
            status=MeetingCommandStatus.ACCEPTED,
            command=command,
        )


@pytest.mark.asyncio
async def test_audio_window_candidate_does_not_submit_command() -> None:
    async def _transcriber(request):
        return WhisperTranscriptionResult(
            text="Create a practice cue.",
            segments=[{"text": "drop me"}],
            language="en",
            duration=0.8,
        )

    submission_service = _FakeSubmissionService()
    service = RealtimeVoiceTranscriber(
        transcriber=_transcriber,
        submission_service=submission_service,
    )

    candidate = await service.transcribe_audio_window(
        window=MeetingVoiceAudioWindow(
            client_session_id="session_1",
            utterance_id="utt_1",
            audio_base64=_audio_base64(),
            mime_type="audio/webm;codecs=opus",
        )
    )

    assert candidate.transcript == "Create a practice cue."
    assert candidate.audio_mime_type == "audio/webm"
    assert candidate.audio_byte_count == len(base64.b64decode(_audio_base64()))
    assert submission_service.envelopes == []


@pytest.mark.asyncio
async def test_final_transcript_submits_one_command_without_audio_payload() -> None:
    async def _transcriber(request):
        return WhisperTranscriptionResult(
            text="Create a practice cue.",
            segments=[],
            language="en",
            duration=0.8,
        )

    submission_service = _FakeSubmissionService()
    service = RealtimeVoiceTranscriber(
        transcriber=_transcriber,
        submission_service=submission_service,
    )
    candidate = await service.transcribe_audio_window(
        window=MeetingVoiceAudioWindow(
            client_session_id="session_1",
            utterance_id="utt_1",
            audio_base64=_audio_base64(),
            mime_type="audio/wav",
        )
    )

    response = await service.submit_final_transcript(
        candidate=candidate,
        workspace_id="ws_voice",
        meeting_id="mtg_voice",
        workspace=SimpleNamespace(id="ws_voice"),
        orchestrator=SimpleNamespace(),
        mindscape_store=SimpleNamespace(),
    )

    assert response.command_id == "cmd_voice_session"
    assert len(submission_service.envelopes) == 1
    envelope = submission_service.envelopes[0]
    assert envelope.origin_surface == "meeting_voice_session"
    assert envelope.intent_text == "Create a practice cue."
    assert envelope.metadata["client_session_id"] == "session_1"
    assert envelope.metadata["utterance_id"] == "utt_1"
    assert envelope.metadata["protocol"] == "realtime_voice_session"
    assert "audio_base64" not in envelope.metadata
    assert "segments" not in envelope.metadata


@pytest.mark.asyncio
async def test_empty_transcript_is_recoverable_and_submits_no_command() -> None:
    async def _transcriber(request):
        return WhisperTranscriptionResult(text=" ", segments=[], language="en", duration=0)

    submission_service = _FakeSubmissionService()
    service = RealtimeVoiceTranscriber(
        transcriber=_transcriber,
        submission_service=submission_service,
    )

    with pytest.raises(RealtimeVoiceTranscriptionError) as exc_info:
        await service.transcribe_audio_window(
            window=MeetingVoiceAudioWindow(
                client_session_id="session_1",
                utterance_id="utt_empty",
                audio_base64=_audio_base64(),
                mime_type="audio/webm",
            )
        )

    assert exc_info.value.reason == "empty_transcript"
    assert exc_info.value.recoverable is True
    assert submission_service.envelopes == []


@pytest.mark.asyncio
async def test_invalid_audio_closes_session_before_stt() -> None:
    called = False

    async def _transcriber(request):
        nonlocal called
        called = True
        return WhisperTranscriptionResult(text="", segments=[], language="en", duration=0)

    service = RealtimeVoiceTranscriber(transcriber=_transcriber)

    with pytest.raises(RealtimeVoiceTranscriptionError) as exc_info:
        await service.transcribe_audio_window(
            window=MeetingVoiceAudioWindow(
                client_session_id="session_1",
                utterance_id="utt_bad",
                audio_base64="not base64",
                mime_type="audio/webm",
            )
        )

    assert exc_info.value.reason == "invalid_audio_base64"
    assert exc_info.value.close_session is True
    assert called is False


@pytest.mark.asyncio
async def test_realtime_candidate_preserves_normalized_context_until_final_write() -> None:
    async def _transcriber(request):
        return WhisperTranscriptionResult(
            text="Run the selected guidance.",
            segments=[],
            language="en",
            duration=0.7,
        )

    submission_service = _FakeSubmissionService()
    service = RealtimeVoiceTranscriber(
        transcriber=_transcriber,
        submission_service=submission_service,
    )
    candidate = await service.transcribe_audio_window(
        window=MeetingVoiceAudioWindow.model_validate(
            {
                "client_session_id": "session_context",
                "utterance_id": "utt_context",
                "audio_base64": _audio_base64(),
                "mime_type": "audio/mp4",
                "command_context": {
                    "context_objects": [],
                    "expected_outputs": ["guidance_result"],
                    "thread_id": "mtg_voice",
                    "metadata": {
                        "raw_intent_text": "Voice command",
                        "action_parameters": {
                            "meeting_command": "Voice command",
                            "selected_guidance_id": "guide_1",
                        },
                    },
                },
            }
        )
    )

    assert submission_service.envelopes == []
    assert candidate.command_context is not None
    assert candidate.command_context.thread_id == "mtg_voice"
    await service.submit_final_transcript(
        candidate=candidate,
        workspace_id="ws_voice",
        meeting_id="mtg_voice",
        workspace=SimpleNamespace(id="ws_voice"),
        orchestrator=SimpleNamespace(),
        mindscape_store=SimpleNamespace(),
    )

    assert len(submission_service.envelopes) == 1
    envelope = submission_service.envelopes[0]
    assert envelope.expected_outputs == ["guidance_result"]
    assert envelope.thread_id == "mtg_voice"
    assert (
        envelope.metadata["action_parameters"]["meeting_command"]
        == "Run the selected guidance."
    )
    assert envelope.metadata["audio_mime_type"] == "audio/mp4"
