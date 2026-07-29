"""One public orchestration facade for Meeting grounded answers."""

from __future__ import annotations

from typing import Any

from backend.app.models.request_contract import RequestContract
from backend.app.services.orchestration.meeting.meeting_command_authority import (
    MeetingCommandAuthority,
)
from backend.app.services.orchestration.meeting.meeting_llm_adapter import (
    MeetingLLMAdapter,
)

from .answer_synthesizer import GroundedAnswerSynthesizer
from .citation_verifier import GroundedAnswerCitationVerifier
from .contracts import GroundedKnowledgeAnswerResult
from .evidence_assembler import GroundedEvidenceAssembler, canonical_digest
from .knowledge_query_port import MeetingKnowledgeQueryPort
from .plan_compiler import GroundedKnowledgeAnswerPlanCompiler
from .guided_learning import GuidedLearningTurnPolicy


class GroundedKnowledgeAnswerFacade:
    def __init__(
        self,
        *,
        query_port: MeetingKnowledgeQueryPort | None = None,
        plan_compiler: GroundedKnowledgeAnswerPlanCompiler | None = None,
        assembler: GroundedEvidenceAssembler | None = None,
        verifier: GroundedAnswerCitationVerifier | None = None,
        guided_learning_policy: GuidedLearningTurnPolicy | None = None,
    ) -> None:
        self._query_port = query_port or MeetingKnowledgeQueryPort()
        self._plan_compiler = (
            plan_compiler or GroundedKnowledgeAnswerPlanCompiler()
        )
        self._assembler = assembler or GroundedEvidenceAssembler()
        self._verifier = verifier or GroundedAnswerCitationVerifier()
        self._guided_learning_policy = (
            guided_learning_policy or GuidedLearningTurnPolicy()
        )

    async def answer(
        self,
        *,
        contract: RequestContract,
        authority: MeetingCommandAuthority,
        llm: MeetingLLMAdapter,
    ) -> GroundedKnowledgeAnswerResult | None:
        plan = self._plan_compiler.compile(contract)
        if plan is None:
            return None
        tool_results = [
            await self._query_port.execute(
                operation,
                authority=authority,
            )
            for operation in plan.operations
        ]
        packet = self._assembler.assemble(tool_results)
        plan_digest = canonical_digest(plan.model_dump(mode="json"))
        base_receipt = {
            "schema_version": "meeting.grounded-answer-receipt.v1",
            "plan_digest": plan_digest,
            "evidence_digest": packet["evidence_digest"],
            "executed_modes": [
                operation.retrieval_mode for operation in plan.operations
            ],
            "tool_call_count": len(plan.operations),
            "synthesis_call_count": 0,
            "authorization_receipt_digests": packet[
                "admission_snapshot_hashes"
            ],
            "verification_status": "not_run",
        }
        guided_learning = self._guided_learning_policy.project(
            plan.guided_learning_context
        )
        if not packet["evidence"]:
            return GroundedKnowledgeAnswerResult(
                status="insufficient_evidence",
                answer_markdown=(
                    "目前沒有足夠且已授權的證據可以回答這個問題。"
                ),
                coverage={"operations": packet["coverage"]},
                guided_learning=guided_learning,
                receipt={
                    **base_receipt,
                    "verification_status": "insufficient_evidence",
                },
            )
        try:
            synthesis = await GroundedAnswerSynthesizer(llm).synthesize(
                question=plan.question,
                evidence_packet=packet,
            )
            claims = self._verifier.verify(
                synthesis=synthesis,
                citations=packet["citations"],
            )
        except Exception as exc:
            return GroundedKnowledgeAnswerResult(
                status="citation_verification_failed",
                answer_markdown=(
                    "已找到相關證據，但答案的逐項引用驗證未通過；"
                    "本次不輸出未驗證的結論。"
                ),
                citations=tuple(packet["citations"]),
                evidence_refs=tuple(packet["evidence_refs"]),
                coverage={"operations": packet["coverage"]},
                guided_learning=guided_learning,
                receipt={
                    **base_receipt,
                    "synthesis_call_count": 1,
                    "verification_status": "failed",
                    "degraded_reasons": [str(exc)],
                },
            )
        answer_markdown = "\n\n".join(
            (
                f"{claim.text} "
                + " ".join(
                    f"[{citation_id}]"
                    for citation_id in claim.citation_ids
                )
            )
            for claim in claims
        )
        uncertainties = tuple(
            str(item)[:1000]
            for item in list(synthesis.get("uncertainties") or [])[:16]
        )
        safety_notes = tuple(
            str(item)[:1000]
            for item in list(synthesis.get("safety_notes") or [])[:16]
        )
        return GroundedKnowledgeAnswerResult(
            status="answered",
            answer_markdown=answer_markdown,
            claims=claims,
            citations=tuple(packet["citations"]),
            evidence_refs=tuple(packet["evidence_refs"]),
            uncertainties=uncertainties,
            safety_notes=safety_notes,
            coverage={"operations": packet["coverage"]},
            guided_learning=guided_learning,
            receipt={
                **base_receipt,
                "synthesis_call_count": 1,
                "verification_status": "passed",
                "answer_digest": canonical_digest(
                    {
                        "claims": [
                            claim.model_dump(mode="json")
                            for claim in claims
                        ],
                        "uncertainties": uncertainties,
                        "safety_notes": safety_notes,
                    }
                ),
            },
        )


__all__ = ["GroundedKnowledgeAnswerFacade"]
