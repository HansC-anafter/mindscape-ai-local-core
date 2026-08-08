"""Deterministic one-action projection over a bounded learning snapshot."""

from __future__ import annotations

from backend.app.models.guided_learning_contract import (
    GuidedLearningContext,
)

from .contracts import GuidedLearningTurn


class GuidedLearningTurnPolicy:
    def project(
        self,
        context: GuidedLearningContext | None,
    ) -> GuidedLearningTurn | None:
        if context is None:
            return None
        if context.due_state in {
            "retention_due",
            "material_change_revalidation_required",
        }:
            action = "request_teach_back"
        elif context.session_state == "counterexample":
            action = "ask_counterexample"
        elif context.session_state == "transfer":
            action = "ask_transfer"
        elif context.session_state in {"diagnose", "teach_back"}:
            action = "probe"
        elif context.belief_uncertainty >= 0.35:
            action = "probe"
        elif len(context.next_routes) > 1:
            action = "offer_branch_choice"
        else:
            action = "explain"
        return GuidedLearningTurn(
            pedagogical_action=action,
            current_question_id=context.current_question_id,
            current_checkpoint_id=context.current_checkpoint_id,
            current_competency_key=context.current_competency_key,
            why_this_next=context.why_this_next,
            route_choices=tuple(
                route.model_dump(mode="json")
                for route in context.next_routes[:3]
            ),
            writes_mastery=False,
        )


__all__ = ["GuidedLearningTurnPolicy"]
