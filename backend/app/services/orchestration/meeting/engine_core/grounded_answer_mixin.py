"""Thin Meeting lifecycle delegation for grounded knowledge answers."""

from __future__ import annotations

from typing import Any

from backend.app.models.request_contract import RequestContract
from backend.app.services.orchestration.meeting.knowledge_answer import (
    GroundedKnowledgeAnswerFacade,
)
from backend.app.services.orchestration.meeting.knowledge_answer.result_projection import (
    project_grounded_answer_meeting_result,
)
from backend.app.services.orchestration.meeting.meeting_command_authority import (
    read_server_authority,
)
from backend.app.services.orchestration.meeting.meeting_llm_adapter import (
    MeetingLLMAdapter,
)


class MeetingEngineGroundedAnswerMixin:
    async def _stage_grounded_knowledge_answer(
        self,
        *,
        handoff_in: Any | None,
    ):
        contract = getattr(self, "_request_contract", None)
        if not isinstance(contract, RequestContract):
            return None
        if contract.grounded_knowledge_answer is None:
            return None
        handoff_metadata = getattr(handoff_in, "metadata", None)
        authority = read_server_authority(handoff_metadata)
        facade = GroundedKnowledgeAnswerFacade()
        result = await facade.answer(
            contract=contract,
            authority=authority,
            llm=MeetingLLMAdapter.from_engine(self),
        )
        if result is None:
            return None
        return project_grounded_answer_meeting_result(self, result)


__all__ = ["MeetingEngineGroundedAnswerMixin"]
