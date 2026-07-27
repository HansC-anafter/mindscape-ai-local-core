from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.app.models.meeting_command import (
    MeetingCommandAcceptResponse,
    MeetingCommandRecord,
    MeetingCommandStatus,
)
from backend.app.models.meeting_voice_context import MeetingVoiceCommandContext
from backend.app.models.object_runtime import ObjectRef
from backend.app.models.workspace_voice_semantic_turn import (
    WorkspaceVoicePackInteractionResult,
    WorkspaceVoiceReferenceResolution,
)
from backend.app.services.orchestration.meeting.workspace_voice_semantic_turn_facade import (
    WorkspaceVoiceSemanticTurnFacade,
)


def _ref(object_id: str) -> ObjectRef:
    return ObjectRef(
        uri=f"mindscape://sample_coach/segment/{object_id}",
        owner_pack="sample_coach",
        object_kind="segment",
        object_id=object_id,
        workspace_id="ws_voice",
    )


class _Resolver:
    def __init__(self, result: WorkspaceVoiceReferenceResolution) -> None:
        self.result = result
        self.calls = 0

    def resolve(self, **kwargs):
        self.calls += 1
        return self.result


class _PackPort:
    def __init__(self, result: WorkspaceVoicePackInteractionResult) -> None:
        self.result = result
        self.calls = 0

    async def resolve(self, **kwargs):
        self.calls += 1
        return self.result


class _Submission:
    def __init__(self) -> None:
        self.envelopes = []

    async def submit_envelope(self, **kwargs):
        envelope = kwargs["envelope"]
        self.envelopes.append(envelope)
        command = MeetingCommandRecord(
            command_id="cmd_semantic",
            workspace_id=kwargs["workspace_id"],
            meeting_id=kwargs["meeting_id"],
            origin_surface=envelope.origin_surface,
            actor="user",
            intent_text=envelope.intent_text,
            context_objects=envelope.context_objects,
            requested_action=envelope.requested_action,
            metadata=envelope.metadata,
            status=MeetingCommandStatus.ACCEPTED,
        )
        return MeetingCommandAcceptResponse(
            workspace_id=kwargs["workspace_id"],
            meeting_id=kwargs["meeting_id"],
            command_id=command.command_id,
            status=command.status,
            command=command,
        )


def _decision(**updates) -> WorkspaceVoicePackInteractionResult:
    payload = {
        "schema_version": "aol.voice_interaction_result.v1",
        "outcome": "not_applicable",
        "decision_code": "not_applicable",
        "confidence": 1.0,
    }
    payload.update(updates)
    return WorkspaceVoicePackInteractionResult.model_validate(payload)


async def _submit(facade, *, assert_target_current=None):
    return await facade.submit_final_transcript(
        transcript="Recommend one practice.",
        language="en",
        command_context=MeetingVoiceCommandContext(),
        session=SimpleNamespace(metadata={"active_capability_code": "sample_coach"}),
        workspace_id="ws_voice",
        meeting_id="mtg_voice",
        origin_surface="meeting_voice_session",
        transport_metadata={"utterance_id": "utt-1"},
        workspace=SimpleNamespace(id="ws_voice"),
        orchestrator=SimpleNamespace(),
        mindscape_store=SimpleNamespace(),
        assert_target_current=assert_target_current,
    )


@pytest.mark.asyncio
async def test_not_applicable_submits_exactly_one_canonical_command() -> None:
    submission = _Submission()
    facade = WorkspaceVoiceSemanticTurnFacade(
        submission_service=submission,
        reference_resolver=_Resolver(WorkspaceVoiceReferenceResolution()),
        active_pack_port=_PackPort(_decision()),
    )

    result = await _submit(facade)

    assert result.status == "command_submitted"
    assert result.command_response is not None
    assert len(submission.envelopes) == 1
    assert submission.envelopes[0].intent_text == "Recommend one practice."
    assert (
        submission.envelopes[0]
        .metadata["workspace_voice_semantic_turn"]["decision_code"]
        == "not_applicable"
    )


@pytest.mark.asyncio
async def test_reference_failure_and_pack_clarification_are_zero_write() -> None:
    submission = _Submission()
    reference_failure = WorkspaceVoiceSemanticTurnFacade(
        submission_service=submission,
        reference_resolver=_Resolver(
            WorkspaceVoiceReferenceResolution(
                status="unresolved",
                explicit_kind="hash",
                token="missing",
                reason="hash_reference_unresolved",
                catalog_query_count=1,
            )
        ),
        active_pack_port=_PackPort(_decision()),
    )
    unresolved = await _submit(reference_failure)

    pack_clarification = WorkspaceVoiceSemanticTurnFacade(
        submission_service=submission,
        reference_resolver=_Resolver(
            WorkspaceVoiceReferenceResolution(
                status="resolved",
                explicit_kind="hash",
                token="#pose-42",
                resolved_references=[_ref("pose-42")],
                catalog_query_count=1,
            )
        ),
        active_pack_port=_PackPort(
            _decision(
                outcome="clarification",
                decision_code="material_not_found",
                confidence=0.0,
                clarification_reason="material_not_found",
            )
        ),
    )
    clarification = await _submit(pack_clarification)

    assert unresolved.status == "reference_unresolved"
    assert unresolved.command_response is None
    assert clarification.status == "clarification_required"
    assert clarification.command_response is None
    assert clarification.resolved_references == [_ref("pose-42")]
    assert submission.envelopes == []


@pytest.mark.asyncio
async def test_grounded_material_adds_canonical_ref_and_one_write() -> None:
    submission = _Submission()
    material_ref = _ref("seg-1")
    facade = WorkspaceVoiceSemanticTurnFacade(
        submission_service=submission,
        reference_resolver=_Resolver(WorkspaceVoiceReferenceResolution()),
        active_pack_port=_PackPort(
            _decision(
                outcome="grounded_material",
                decision_code="grounded_material",
                confidence=0.91,
                candidates=[
                    {
                        "object_ref": material_ref,
                        "display_label": "Short practice",
                        "score": 0.91,
                        "metadata": {},
                    }
                ],
            )
        ),
    )

    result = await _submit(facade)

    assert result.resolved_references == [material_ref]
    assert len(submission.envelopes) == 1
    assert submission.envelopes[0].context_objects[0].ref == material_ref


@pytest.mark.asyncio
async def test_grounded_answer_preserves_pack_language_and_evidence() -> None:
    submission = _Submission()
    facade = WorkspaceVoiceSemanticTurnFacade(
        submission_service=submission,
        reference_resolver=_Resolver(WorkspaceVoiceReferenceResolution()),
        active_pack_port=_PackPort(
            _decision(
                outcome="grounded_answer",
                decision_code="grounded_answer",
                confidence=0.9,
                answer_text="膝蓋應與腳趾方向一致。",
                answer_language="zh-TW",
                evidence=[
                    {
                        "source_ref": "mindscape://sample_coach/knowledge/k-1",
                        "title": "Alignment",
                        "excerpt": "Keep the knee aligned with the toes.",
                        "score": 0.9,
                    }
                ],
            )
        ),
    )

    result = await _submit(facade)

    assert result.answer_text == "膝蓋應與腳趾方向一致。"
    assert result.answer_language == "zh-TW"
    assert result.answer_language != "en"
    assert len(result.evidence) == 1
    assert len(submission.envelopes) == 1


@pytest.mark.asyncio
async def test_stale_target_after_semantic_work_is_zero_write() -> None:
    submission = _Submission()
    facade = WorkspaceVoiceSemanticTurnFacade(
        submission_service=submission,
        reference_resolver=_Resolver(WorkspaceVoiceReferenceResolution()),
        active_pack_port=_PackPort(_decision()),
    )

    def _stale() -> None:
        raise RuntimeError("stale_target")

    result = await _submit(facade, assert_target_current=_stale)

    assert result.status == "stale_target"
    assert result.command_response is None
    assert submission.envelopes == []
