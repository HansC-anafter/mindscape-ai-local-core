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
from backend.app.models.meeting_voice import MeetingVoiceTurnRequest
from backend.app.services.host_services.whisper_proxy import (
    WhisperTranscriptionResult,
    WhisperTranscriptionUnavailable,
)
from backend.app.services.orchestration.meeting.voice_ingress import (
    MeetingVoiceIngressError,
    MeetingVoiceIngressService,
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
            command_id="cmd_voice",
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
            command_id="cmd_voice",
            status=MeetingCommandStatus.ACCEPTED,
            command=command,
        )


@pytest.mark.asyncio
async def test_voice_ingress_submits_one_command_for_valid_transcript() -> None:
    async def _transcriber(request):
        return WhisperTranscriptionResult(
            text="Start the student practice summary.",
            segments=[{"text": "drop me"}],
            language="en",
            duration=1.2,
        )

    submission_service = _FakeSubmissionService()
    service = MeetingVoiceIngressService(
        transcriber=_transcriber,
        submission_service=submission_service,
    )

    response = await service.submit_voice_turn(
        request=MeetingVoiceTurnRequest(
            client_turn_id="turn_1",
            audio_base64=_audio_base64(),
            mime_type="audio/webm;codecs=opus",
        ),
        workspace_id="ws_voice",
        meeting_id="mtg_voice",
        workspace=SimpleNamespace(id="ws_voice"),
        orchestrator=SimpleNamespace(),
        mindscape_store=SimpleNamespace(),
    )

    assert response.status == "transcribed_command_submitted"
    assert response.command_response is not None
    assert len(submission_service.envelopes) == 1
    envelope = submission_service.envelopes[0]
    assert envelope.origin_surface == "meeting_voice"
    assert envelope.actor == "user"
    assert envelope.intent_text == "Start the student practice summary."
    assert envelope.metadata["client_turn_id"] == "turn_1"
    assert envelope.metadata["audio_mime_type"] == "audio/webm"
    assert envelope.metadata["audio_byte_count"] == len(base64.b64decode(_audio_base64()))
    assert "audio_base64" not in envelope.metadata
    assert "segments" not in envelope.metadata


@pytest.mark.asyncio
async def test_voice_ingress_ignores_empty_transcript_without_command() -> None:
    async def _transcriber(request):
        return WhisperTranscriptionResult(
            text="  ",
            segments=[],
            language="en",
            duration=0.4,
        )

    submission_service = _FakeSubmissionService()
    service = MeetingVoiceIngressService(
        transcriber=_transcriber,
        submission_service=submission_service,
    )

    response = await service.submit_voice_turn(
        request=MeetingVoiceTurnRequest(
            client_turn_id="turn_empty",
            audio_base64=_audio_base64(),
            mime_type="audio/wav",
        ),
        workspace_id="ws_voice",
        meeting_id="mtg_voice",
        workspace=SimpleNamespace(id="ws_voice"),
        orchestrator=SimpleNamespace(),
        mindscape_store=SimpleNamespace(),
    )

    assert response.status == "ignored_empty_transcript"
    assert submission_service.envelopes == []


@pytest.mark.asyncio
async def test_voice_ingress_returns_stt_unavailable_without_command() -> None:
    async def _transcriber(request):
        raise WhisperTranscriptionUnavailable(reason="stt_timeout")

    submission_service = _FakeSubmissionService()
    service = MeetingVoiceIngressService(
        transcriber=_transcriber,
        submission_service=submission_service,
    )

    response = await service.submit_voice_turn(
        request=MeetingVoiceTurnRequest(
            client_turn_id="turn_timeout",
            audio_base64=_audio_base64(),
            mime_type="audio/webm",
        ),
        workspace_id="ws_voice",
        meeting_id="mtg_voice",
        workspace=SimpleNamespace(id="ws_voice"),
        orchestrator=SimpleNamespace(),
        mindscape_store=SimpleNamespace(),
    )

    assert response.status == "stt_unavailable"
    assert response.reason == "stt_timeout"
    assert submission_service.envelopes == []


@pytest.mark.asyncio
async def test_voice_ingress_rejects_invalid_audio_before_stt() -> None:
    called = False

    async def _transcriber(request):
        nonlocal called
        called = True
        return WhisperTranscriptionResult(text="", segments=[], language="en", duration=0)

    service = MeetingVoiceIngressService(
        transcriber=_transcriber,
        submission_service=_FakeSubmissionService(),
    )

    with pytest.raises(MeetingVoiceIngressError) as exc_info:
        await service.submit_voice_turn(
            request=MeetingVoiceTurnRequest(
                client_turn_id="turn_bad",
                audio_base64="not base64",
                mime_type="audio/webm",
            ),
            workspace_id="ws_voice",
            meeting_id="mtg_voice",
            workspace=SimpleNamespace(id="ws_voice"),
            orchestrator=SimpleNamespace(),
            mindscape_store=SimpleNamespace(),
        )

    assert exc_info.value.status_code == 422
    assert called is False


@pytest.mark.asyncio
async def test_voice_ingress_preserves_full_command_context_for_mp4() -> None:
    async def _transcriber(request):
        return WhisperTranscriptionResult(
            text="Create the selected scene now.",
            segments=[],
            language="en",
            duration=0.9,
        )

    submission_service = _FakeSubmissionService()
    service = MeetingVoiceIngressService(
        transcriber=_transcriber,
        submission_service=submission_service,
    )
    response = await service.submit_voice_turn(
        request=MeetingVoiceTurnRequest.model_validate(
            {
                "client_turn_id": "turn_context",
                "audio_base64": _audio_base64(),
                "mime_type": "audio/mp4;codecs=mp4a.40.2",
                "command_context": {
                    "context_objects": [],
                    "requested_action": {
                        "verb": "execute_playbook",
                        "pack_code": "ig",
                        "playbook_code": "create_scene",
                        "write_mode": "recommendation_only",
                        "parameters": {
                            "instruction": "Voice command",
                            "message": "Voice command",
                            "meeting_command": "Voice command",
                        },
                    },
                    "expected_outputs": ["scene"],
                    "write_mode": "recommendation_only",
                    "thread_id": "mtg_voice",
                    "meeting_mentions": [
                        {
                            "kind": "pack",
                            "id": "ig",
                            "token": "@ig",
                        }
                    ],
                    "metadata": {
                        "raw_intent_text": "Voice command",
                        "action_parameters": {
                            "meeting_command": "Voice command",
                            "graph_selection": {"selection_hash": "gsel_1"},
                        },
                    },
                },
            }
        ),
        workspace_id="ws_voice",
        meeting_id="mtg_voice",
        workspace=SimpleNamespace(id="ws_voice"),
        orchestrator=SimpleNamespace(),
        mindscape_store=SimpleNamespace(),
    )

    assert response.status == "transcribed_command_submitted"
    assert len(submission_service.envelopes) == 1
    envelope = submission_service.envelopes[0]
    assert envelope.intent_text == "Create the selected scene now."
    assert envelope.thread_id == "mtg_voice"
    assert envelope.expected_outputs == ["scene"]
    assert envelope.meeting_mentions[0]["token"] == "@ig"
    assert envelope.requested_action is not None
    assert envelope.requested_action.playbook_code == "create_scene"
    assert (
        envelope.requested_action.parameters["instruction"]
        == "Create the selected scene now."
    )
    assert (
        envelope.metadata["action_parameters"]["meeting_command"]
        == "Create the selected scene now."
    )
    assert envelope.metadata["audio_mime_type"] == "audio/mp4"


@pytest.mark.asyncio
async def test_voice_ingress_rejects_conflicting_context_before_stt_or_write() -> None:
    called = False

    async def _transcriber(request):
        nonlocal called
        called = True
        return WhisperTranscriptionResult(
            text="must not run",
            segments=[],
            language="en",
            duration=0.1,
        )

    submission_service = _FakeSubmissionService()
    service = MeetingVoiceIngressService(
        transcriber=_transcriber,
        submission_service=submission_service,
    )

    with pytest.raises(MeetingVoiceIngressError) as exc_info:
        await service.submit_voice_turn(
            request=MeetingVoiceTurnRequest.model_validate(
                {
                    "client_turn_id": "turn_conflict",
                    "audio_base64": _audio_base64(),
                    "mime_type": "audio/webm",
                    "command_context": {
                        "context_objects": [],
                        "metadata": {"source": "normalized"},
                    },
                    "metadata": {"source": "legacy"},
                }
            ),
            workspace_id="ws_voice",
            meeting_id="mtg_voice",
            workspace=SimpleNamespace(id="ws_voice"),
            orchestrator=SimpleNamespace(),
            mindscape_store=SimpleNamespace(),
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["code"] == "conflicting_command_context"
    assert called is False
    assert submission_service.envelopes == []
