"""Project a grounded answer into the existing Meeting result contract."""

from __future__ import annotations

from typing import Any

from .contracts import GroundedKnowledgeAnswerResult


def project_grounded_answer_meeting_result(
    engine: Any,
    result: GroundedKnowledgeAnswerResult,
):
    result_class = engine._meeting_result_class()
    return result_class(
        session_id=engine.session.id,
        minutes_md=result.answer_markdown,
        decision=result.answer_markdown,
        action_items=[],
        event_ids=[],
        completion_status=(
            "completed" if result.status == "answered" else "accepted"
        ),
        grounded_answer_receipt=result.model_dump(mode="json"),
    )


__all__ = ["project_grounded_answer_meeting_result"]
