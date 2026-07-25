"""Authenticated cancellation, inconclusive closure, and supersession."""

from __future__ import annotations

from .transitions import require_transition


class ProductIterationClosureMixin:
    def cancel_product_iteration(
        self,
        conn,
        *,
        workflow_id: str,
        expected_sequence: int,
        reason: dict,
        actor: dict,
        idempotency_key: str,
    ) -> dict:
        self.request_cancellation(
            conn,
            workflow_id=workflow_id,
            expected_sequence=expected_sequence,
            reason=reason,
            idempotency_key=f"{idempotency_key}:request",
            actor=actor,
        )
        return self._append_transition_for_kind(
            conn,
            workflow_id=workflow_id,
            expected_sequence=expected_sequence + 1,
            target_state="cancelled",
            idempotency_key=f"{idempotency_key}:transition",
            actor=actor,
            expected_kind="product_iteration",
        )

    def close_product_iteration_inconclusive(
        self,
        conn,
        *,
        workflow_id: str,
        expected_sequence: int,
        closure: dict,
        actor: dict,
        idempotency_key: str,
    ) -> dict:
        required = {"reason_code", "evidence_hash", "recorded_at"}
        if set(closure) != required:
            raise ValueError(
                "inconclusive closure requires exact bounded receipt"
            )
        if closure["reason_code"] not in {
            "window_ended",
            "budget_exhausted",
            "validation_inconclusive",
        }:
            raise ValueError("inconclusive closure reason is invalid")
        if (
            len(closure["evidence_hash"]) != 64
            or any(
                character not in "0123456789abcdef"
                for character in closure["evidence_hash"]
            )
        ):
            raise ValueError("inconclusive closure evidence hash is invalid")
        locked, retry = self._begin_append(
            conn,
            workflow_id,
            expected_sequence,
            idempotency_key,
            lambda prior: (
                prior["event_type"] == "transition"
                and prior["payload"].get("to_state") == "inconclusive"
                and prior["payload"].get("closure") == closure
            ),
        )
        if locked["workflow_kind"] != "product_iteration":
            raise ValueError("workflow must use product_iteration kind")
        if retry:
            return retry
        require_transition(
            "product_iteration",
            locked["current_state"],
            "inconclusive",
        )
        return self._append_locked(
            conn,
            locked=locked,
            event_type="transition",
            idempotency_key=idempotency_key,
            actor=actor,
            payload={
                "from_state": locked["current_state"],
                "to_state": "inconclusive",
                "closure": closure,
            },
            current_state="inconclusive",
            terminal=True,
        )

    def supersede_product_iteration(
        self,
        conn,
        *,
        workflow_id: str,
        successor_workflow_id: str,
        expected_sequence: int,
        actor: dict,
        idempotency_key: str,
    ) -> dict:
        locked = {
            item: self._repository.lock_instance(conn, item)
            for item in sorted({workflow_id, successor_workflow_id})
        }
        source = locked[workflow_id]
        successor = locked[successor_workflow_id]
        if (
            source["workflow_kind"] != "product_iteration"
            or successor["workflow_kind"] != "product_iteration"
        ):
            raise ValueError("supersede requires product_iteration kinds")
        successor_definition = self._projection_state(
            conn, successor
        ).get("definition", {})
        if (
            successor["current_state"] != "admitted"
            or successor_definition.get("parent_iteration_id")
            != workflow_id
        ):
            raise ValueError(
                "successor must be admitted and pin its source iteration"
            )
        if source["current_sequence"] != expected_sequence:
            raise ValueError("supersede expected sequence is stale")
        require_transition(
            "product_iteration", source["current_state"], "superseded"
        )
        return self._append_locked(
            conn,
            locked=source,
            event_type="transition",
            idempotency_key=idempotency_key,
            actor=actor,
            payload={
                "from_state": source["current_state"],
                "to_state": "superseded",
                "successor_workflow_id": successor_workflow_id,
            },
            current_state="superseded",
            terminal=True,
        )
