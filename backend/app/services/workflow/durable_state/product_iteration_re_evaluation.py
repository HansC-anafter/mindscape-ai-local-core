"""Fixed-definition product-iteration re-evaluation append seam."""

from __future__ import annotations

from typing import Any

from .contracts.v1.validator import validate_contract
from .product_iteration_contract import (
    promotion_request_hash,
    require_evaluation_parity,
    verify_signed,
)


class ProductIterationReEvaluationMixin:
    def record_iteration_re_evaluation(
        self,
        conn,
        *,
        workflow_id: str,
        expected_sequence: int,
        evaluation: dict[str, Any],
        approval_request: dict[str, Any] | None,
        actor: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Append another fixed-definition evaluation without rerunning work."""

        validate_contract("evaluation_receipt", evaluation)
        verify_signed(evaluation, self._verification_keys)
        locked, retry = self._begin_append(
            conn,
            workflow_id,
            expected_sequence,
            idempotency_key,
            lambda prior: (
                prior["event_type"] == "transition"
                and prior["payload"].get("from_state")
                == "decision_pending"
                and prior["payload"].get("to_state")
                == "decision_pending"
                and prior["payload"].get("typed_receipt", {}).get(
                    "receipt"
                )
                == evaluation
            ),
        )
        self._require_kind(locked, "product_iteration")
        if retry:
            return retry
        if locked["current_state"] != "decision_pending":
            raise ValueError(
                "iteration re-evaluation requires decision_pending state"
            )
        state = self._projection_state(conn, locked)
        definition = state["definition"]
        prior = state.get("evaluation")
        if not prior:
            raise ValueError("iteration re-evaluation has no prior evaluation")
        if prior["recommendation"] == "promote":
            raise ValueError(
                "promotion recommendation must be resolved before another attempt"
            )
        if (
            state.get("evaluation_attempt_count", 0)
            >= definition["budget"]["max_evaluation_attempts"]
        ):
            raise ValueError("iteration evaluation attempt budget is exhausted")
        if evaluation["evaluation_attempt_id"] == prior[
            "evaluation_attempt_id"
        ]:
            raise ValueError("iteration evaluation attempt ID must advance")
        require_evaluation_parity(state, definition, evaluation)
        if evaluation["recommendation"] == "promote":
            if (
                approval_request is None
                or approval_request.get("workflow_id") != workflow_id
                or approval_request.get("action_hash")
                != promotion_request_hash(definition, evaluation)
            ):
                raise ValueError(
                    "promotion re-evaluation requires exact approval request"
                )
        elif approval_request is not None:
            raise ValueError(
                "non-promotion re-evaluation cannot request approval"
            )
        event = self._append_locked(
            conn,
            locked=locked,
            event_type="transition",
            idempotency_key=idempotency_key,
            actor=actor,
            payload={
                "from_state": "decision_pending",
                "to_state": "decision_pending",
                "typed_receipt": {
                    "receipt_type": "evaluation_receipt",
                    "receipt": evaluation,
                },
            },
            current_state="decision_pending",
        )
        if approval_request is not None:
            self.request_approval(conn, approval_request)
        return event
