"""Compile a typed RequestContract into one explicit bounded answer plan."""

from __future__ import annotations

from backend.app.models.request_contract import RequestContract

from .contracts import (
    GroundedKnowledgeAnswerOperation,
    GroundedKnowledgeAnswerPlan,
)


class GroundedKnowledgeAnswerPlanCompiler:
    def compile(
        self,
        contract: RequestContract | None,
    ) -> GroundedKnowledgeAnswerPlan | None:
        if contract is None or contract.grounded_knowledge_answer is None:
            return None
        request = contract.grounded_knowledge_answer
        modes = list(request.retrieval_modes)
        if not modes:
            modes = [
                RequestContract._infer_grounded_answer_mode(request.question)
            ]
        operations = tuple(
            GroundedKnowledgeAnswerOperation(
                query=request.question,
                retrieval_mode=mode,
                scope=request.scope,
            )
            for mode in modes[:2]
        )
        return GroundedKnowledgeAnswerPlan(
            question=request.question,
            operations=operations,
            frontier_preview=request.frontier_preview,
            guided_learning_context=request.guided_learning_context,
        )


__all__ = ["GroundedKnowledgeAnswerPlanCompiler"]
