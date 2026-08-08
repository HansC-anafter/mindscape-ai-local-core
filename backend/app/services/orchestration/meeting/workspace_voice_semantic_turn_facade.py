"""Canonical final-transcript compiler for bounded and realtime Meeting voice."""

from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

from fastapi import BackgroundTasks

from backend.app.models.meeting_voice_context import MeetingVoiceCommandContext
from backend.app.models.object_runtime import ObjectRef, ObjectRoleEntry
from backend.app.models.workspace import Workspace
from backend.app.models.workspace_voice_semantic_turn import (
    WorkspaceVoiceEvidence,
    WorkspaceVoicePackInteractionResult,
    WorkspaceVoiceReferenceCandidate,
    WorkspaceVoiceReferenceResolution,
    WorkspaceVoiceSemanticTurnResult,
)
from backend.app.services.conversation_orchestrator import ConversationOrchestrator
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.orchestration.meeting.active_pack_voice_interaction_port import (
    ActivePackVoiceInteractionPort,
)
from backend.app.services.orchestration.meeting.aol_voice_reference_resolver_facade import (
    AolVoiceReferenceResolverFacade,
)
from backend.app.services.orchestration.meeting.meeting_command_submission import (
    MeetingCommandSubmissionService,
)
from backend.app.services.orchestration.meeting.voice_client_actions import (
    build_voice_command_envelope,
)


AssertTargetCurrent = Callable[[], None]


def _reference_failure(
    *,
    transcript: str,
    resolution: WorkspaceVoiceReferenceResolution,
) -> WorkspaceVoiceSemanticTurnResult:
    status_map = {
        "unresolved": "reference_unresolved",
        "ambiguous": "reference_ambiguous",
        "count_exceeded": "reference_count_exceeded",
    }
    return WorkspaceVoiceSemanticTurnResult(
        status=status_map[resolution.status],
        outcome="clarification",
        decision_code=resolution.reason or status_map[resolution.status],
        transcript=transcript,
        candidates=resolution.candidates,
    )


def _safe_pack_candidates(
    decision: WorkspaceVoicePackInteractionResult,
) -> list[WorkspaceVoiceReferenceCandidate]:
    return [
        WorkspaceVoiceReferenceCandidate(
            object_ref=candidate.object_ref,
            display_label=candidate.display_label,
            score=candidate.score,
        )
        for candidate in decision.candidates
    ]


def _safe_evidence(
    decision: WorkspaceVoicePackInteractionResult,
) -> list[WorkspaceVoiceEvidence]:
    return [
        WorkspaceVoiceEvidence(
            source_ref=evidence.source_ref,
            title=evidence.title,
            excerpt=evidence.excerpt,
            score=evidence.score,
        )
        for evidence in decision.evidence
    ]


def _merge_context(
    context: MeetingVoiceCommandContext,
    refs: Sequence[ObjectRef],
) -> MeetingVoiceCommandContext:
    entries = list(context.context_objects)
    seen = {entry.ref.uri for entry in entries}
    for ref in refs:
        if ref.uri in seen:
            continue
        seen.add(ref.uri)
        entries.append(ObjectRoleEntry(role="source", ref=ref))
    return context.model_copy(update={"context_objects": entries}, deep=True)


def _dedupe_refs(values: Sequence[ObjectRef]) -> list[ObjectRef]:
    output: list[ObjectRef] = []
    seen: set[str] = set()
    for ref in values:
        if ref.uri in seen:
            continue
        seen.add(ref.uri)
        output.append(ref)
    return output


def _semantic_metadata(
    *,
    decision: WorkspaceVoicePackInteractionResult,
    reference_resolution: WorkspaceVoiceReferenceResolution,
    resolved_refs: Sequence[ObjectRef],
) -> dict[str, Any]:
    return {
        "schema_version": "workspace.voice_semantic_turn.v1",
        "outcome": decision.outcome,
        "decision_code": decision.decision_code,
        "confidence": decision.confidence,
        "reference_resolution": reference_resolution.status,
        "resolved_reference_uris": [ref.uri for ref in resolved_refs],
        "evidence_refs": [item.source_ref for item in decision.evidence],
        "answer_text": decision.answer_text,
        "answer_language": decision.answer_language,
    }


class WorkspaceVoiceSemanticTurnFacade:
    """Own one final transcript, one semantic decision, and at most one write."""

    def __init__(
        self,
        *,
        submission_service: MeetingCommandSubmissionService | None = None,
        reference_resolver: AolVoiceReferenceResolverFacade | None = None,
        active_pack_port: ActivePackVoiceInteractionPort | None = None,
    ) -> None:
        self.submission_service = (
            submission_service or MeetingCommandSubmissionService()
        )
        self.reference_resolver = (
            reference_resolver or AolVoiceReferenceResolverFacade()
        )
        self.active_pack_port = active_pack_port or ActivePackVoiceInteractionPort()

    async def submit_final_transcript(
        self,
        *,
        transcript: str,
        language: str | None,
        command_context: MeetingVoiceCommandContext,
        session: Any,
        workspace_id: str,
        meeting_id: str,
        origin_surface: str,
        transport_metadata: Mapping[str, Any],
        workspace: Workspace,
        orchestrator: ConversationOrchestrator,
        mindscape_store: MindscapeStore,
        background_tasks: BackgroundTasks | None = None,
        assert_target_current: AssertTargetCurrent | None = None,
    ) -> WorkspaceVoiceSemanticTurnResult:
        normalized_transcript = transcript.strip()
        frozen_refs = [entry.ref for entry in command_context.context_objects]
        reference_resolution = self.reference_resolver.resolve(
            transcript=normalized_transcript,
            workspace_id=workspace_id,
            frozen_context_objects=frozen_refs,
        )
        if reference_resolution.status in {
            "unresolved",
            "ambiguous",
            "count_exceeded",
        }:
            return _reference_failure(
                transcript=normalized_transcript,
                resolution=reference_resolution,
            )

        explicit_refs = reference_resolution.resolved_references
        decision = await self.active_pack_port.resolve(
            transcript=normalized_transcript,
            workspace_id=workspace_id,
            language=language,
            session=session,
            resolved_references=explicit_refs,
        )
        candidates = _safe_pack_candidates(decision)
        evidence = _safe_evidence(decision)
        if decision.outcome == "clarification":
            status = (
                "interaction_unavailable"
                if decision.decision_code.startswith("active_pack_voice_")
                else "clarification_required"
            )
            return WorkspaceVoiceSemanticTurnResult(
                status=status,
                outcome=decision.outcome,
                decision_code=decision.decision_code,
                transcript=normalized_transcript,
                resolved_references=explicit_refs,
                candidates=candidates,
                evidence=evidence,
            )

        material_refs = (
            [decision.candidates[0].object_ref]
            if decision.outcome == "grounded_material"
            else []
        )
        resolved_refs = _dedupe_refs([*explicit_refs, *material_refs])
        try:
            if assert_target_current is not None:
                assert_target_current()
        except Exception:
            return WorkspaceVoiceSemanticTurnResult(
                status="stale_target",
                outcome="clarification",
                decision_code="stale_target",
                transcript=normalized_transcript,
                resolved_references=resolved_refs,
            )

        merged_context = _merge_context(command_context, resolved_refs)
        metadata = dict(transport_metadata)
        metadata["workspace_voice_semantic_turn"] = _semantic_metadata(
            decision=decision,
            reference_resolution=reference_resolution,
            resolved_refs=resolved_refs,
        )
        command_response = await self.submission_service.submit_envelope(
            envelope=build_voice_command_envelope(
                workspace_id=workspace_id,
                meeting_id=meeting_id,
                origin_surface=origin_surface,
                transcript=normalized_transcript,
                context_objects=merged_context.context_objects,
                command_context=merged_context,
                resolution=decision.client_action,
                metadata=metadata,
            ),
            workspace_id=workspace_id,
            meeting_id=meeting_id,
            workspace=workspace,
            orchestrator=orchestrator,
            mindscape_store=mindscape_store,
            background_tasks=background_tasks,
        )
        return WorkspaceVoiceSemanticTurnResult(
            status="command_submitted",
            outcome=decision.outcome,
            decision_code=decision.decision_code,
            transcript=normalized_transcript,
            command_response=command_response,
            answer_text=decision.answer_text,
            answer_language=decision.answer_language,
            resolved_references=resolved_refs,
            candidates=candidates,
            evidence=evidence,
            client_action=decision.client_action,
        )


__all__ = [
    "AssertTargetCurrent",
    "WorkspaceVoiceSemanticTurnFacade",
]
