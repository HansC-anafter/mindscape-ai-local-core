"""Upper product-iteration commands behind the single durable facade."""

from __future__ import annotations

from typing import Any

from .canonical_json import sha256_hex
from .contracts.v1.validator import validate_contract
from .product_iteration_contract import (
    arm,
    immutable_definition,
    observation_rejection,
    product_iteration_definition_sha256,
    promotion_request_hash,
    require_definition,
    require_enrollment_parity,
    require_evaluation_parity,
    verify_signed,
)
from .transitions import require_transition


class ProductIterationMixin:
    """Caller-owned-transaction upper aggregate; no routes or workers."""

    def open_product_iteration(
        self,
        conn,
        *,
        identity: dict[str, Any],
        definition: dict[str, Any],
        actor: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        if identity.get("workflow_kind") != "product_iteration":
            raise ValueError(
                "product iteration identity must use product_iteration kind"
            )
        require_definition(definition, state="draft")
        if definition["iteration_id"] != identity["workflow_id"]:
            raise ValueError("iteration definition workflow identity mismatch")
        if definition["workspace_id"] != identity["workspace_id"]:
            raise ValueError("iteration definition workspace mismatch")
        self._open_workflow_kind(conn, identity)
        locked = self._repository.lock_instance(conn, identity["workflow_id"])
        self._append_locked(
            conn,
            locked=locked,
            event_type="product_iteration_defined",
            idempotency_key=idempotency_key,
            actor=actor,
            payload={"definition": definition},
        )
        return self.read_current(conn, identity["workflow_id"])

    def admit_product_iteration(
        self,
        conn,
        *,
        workflow_id: str,
        expected_sequence: int,
        definition: dict[str, Any],
        actor: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        require_definition(definition, state="admitted")
        locked, retry = self._begin_append(
            conn,
            workflow_id,
            expected_sequence,
            idempotency_key,
            lambda prior: (
                prior["event_type"] == "transition"
                and prior["payload"].get("to_state") == "admitted"
                and prior["payload"].get("typed_receipt", {}).get("receipt")
                == definition
            ),
        )
        self._require_kind(locked, "product_iteration")
        if retry:
            return retry
        prior_definition = self._projection_state(conn, locked).get("definition")
        if prior_definition is None:
            raise ValueError("iteration draft definition is missing")
        if immutable_definition(prior_definition) != (immutable_definition(definition)):
            raise ValueError("iteration definition is immutable at admission")
        if any(
            arm["consumer_compatibility_class"] != "compatible"
            for arm in definition["arms"]
        ):
            raise ValueError("every admitted arm must be consumer-compatible")
        require_transition("product_iteration", "draft", "admitted")
        return self._append_locked(
            conn,
            locked=locked,
            event_type="transition",
            idempotency_key=idempotency_key,
            actor=actor,
            payload={
                "from_state": "draft",
                "to_state": "admitted",
                "typed_receipt": {
                    "receipt_type": "product_iteration",
                    "receipt": definition,
                },
            },
            current_state="admitted",
        )

    def start_product_iteration_collection(self, conn, **kwargs) -> dict[str, Any]:
        return self._append_transition_for_kind(
            conn,
            expected_kind="product_iteration",
            target_state="collecting",
            **kwargs,
        )

    def accept_iteration_enrollment(
        self,
        conn,
        *,
        workflow_id: str,
        expected_sequence: int,
        enrollment: dict[str, Any],
        actor: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        validate_contract("iteration_enrollment", enrollment)
        verify_signed(enrollment, self._verification_keys)
        locked, retry = self._begin_append(
            conn,
            workflow_id,
            expected_sequence,
            idempotency_key,
            lambda prior: (
                prior["event_type"] == "iteration_enrollment_accepted"
                and prior["payload"].get("enrollment") == enrollment
            ),
        )
        self._require_kind(locked, "product_iteration")
        if retry:
            return retry
        if locked["current_state"] != "collecting":
            raise ValueError("iteration enrollment requires collecting state")
        state = self._projection_state(conn, locked)
        definition = state["definition"]
        if enrollment["iteration_id"] != definition["iteration_id"]:
            raise ValueError("enrollment iteration mismatch")
        if enrollment["enrollment_id"] in state.get("enrollment_ids", []):
            raise ValueError("iteration enrollment is already accepted")
        selected_arm = arm(definition, enrollment["arm_id"])
        require_enrollment_parity(definition, selected_arm, enrollment)
        adapter_ref = {
            "capability_identity": enrollment["capability_identity"],
            "adapter_contract_version": enrollment["adapter_contract_version"],
            "descriptor_sha256": enrollment["descriptor_sha256"],
            "evaluator_version": enrollment["evaluator_version"],
            "review_lens": enrollment.get("review_lens"),
        }
        prior_ref = state.get("adapter_refs_by_arm", {}).get(enrollment["arm_id"])
        if prior_ref is not None and prior_ref != adapter_ref:
            raise ValueError("iteration arm adapter identity is already pinned")
        return self._append_locked(
            conn,
            locked=locked,
            event_type="iteration_enrollment_accepted",
            idempotency_key=idempotency_key,
            actor=actor,
            payload={"enrollment": enrollment},
        )

    def accept_outcome_observation(
        self,
        conn,
        *,
        workflow_id: str,
        expected_sequence: int,
        enrollment: dict[str, Any],
        observation: dict[str, Any],
        actor: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        validate_contract("iteration_enrollment", enrollment)
        validate_contract("outcome_observation", observation)
        verify_signed(enrollment, self._verification_keys)
        verify_signed(observation, self._verification_keys)
        locked, retry = self._begin_append(
            conn,
            workflow_id,
            expected_sequence,
            idempotency_key,
            lambda prior: (
                prior["event_type"]
                in {
                    "outcome_observation_accepted",
                    "outcome_observation_rejected",
                }
                and prior["payload"].get("observation_id")
                == observation["observation_id"]
            ),
        )
        self._require_kind(locked, "product_iteration")
        if retry:
            return retry
        if locked["current_state"] != "collecting":
            raise ValueError("outcome observation requires collecting state")
        state = self._projection_state(conn, locked)
        definition = state["definition"]
        selected_arm = arm(definition, enrollment["arm_id"])
        reason = observation_rejection(
            state,
            definition,
            selected_arm,
            enrollment,
            observation,
        )
        if reason:
            return self._append_locked(
                conn,
                locked=locked,
                event_type="outcome_observation_rejected",
                idempotency_key=idempotency_key,
                actor=actor,
                payload={
                    "observation_id": observation["observation_id"],
                    "observation_sha256": sha256_hex(observation),
                    "reason": reason,
                },
            )
        return self._append_locked(
            conn,
            locked=locked,
            event_type="outcome_observation_accepted",
            idempotency_key=idempotency_key,
            actor=actor,
            payload={
                "observation_id": observation["observation_id"],
                "observation": observation,
            },
        )

    def append_outcome_evaluation_intent(
        self,
        conn,
        intent: dict[str, Any],
    ) -> dict[str, Any]:
        required = {
            "iteration_id",
            "terminal_receipt_id",
            "enrollment_id",
            "descriptor_sha256",
            "task_id",
            "idempotency_key",
        }
        missing = required.difference(intent)
        if missing:
            raise ValueError(
                "outcome evaluation intent is missing: " + ",".join(sorted(missing))
            )
        workflow_id = str(intent["iteration_id"])
        idempotency_key = str(intent["idempotency_key"])
        locked = self._repository.lock_instance(conn, workflow_id)
        self._require_kind(locked, "product_iteration")
        if locked["current_state"] != "collecting":
            raise ValueError("outcome evaluation intent requires collecting state")
        payload = {
            "terminal_receipt_id": str(intent["terminal_receipt_id"]),
            "enrollment_id": str(intent["enrollment_id"]),
            "descriptor_sha256": str(intent["descriptor_sha256"]),
            "task_id": str(intent["task_id"]),
        }
        prior = self._repository.find_idempotent_event(
            conn,
            workflow_id,
            idempotency_key,
        )
        if prior is not None:
            if (
                prior["event_type"] == "outcome_evaluation_intent_created"
                and prior["payload"] == payload
            ):
                return prior
            raise ValueError("outcome evaluation intent idempotency conflict")
        return self._append_locked(
            conn,
            locked=locked,
            event_type="outcome_evaluation_intent_created",
            idempotency_key=idempotency_key,
            actor={
                "actor_type": "service",
                "actor_id": "product-outcome-runtime",
            },
            payload=payload,
        )

    def mark_iteration_evidence_ready(self, conn, **kwargs) -> dict[str, Any]:
        workflow_id = kwargs["workflow_id"]
        locked = self._repository.lock_instance(conn, workflow_id)
        self._require_kind(locked, "product_iteration")
        state = self._projection_state(conn, locked)
        minimum = state["definition"]["validation_design"]["minimum_sample_size"]
        if state.get("accepted_observation_count", 0) < minimum:
            raise ValueError("iteration evidence is below minimum sample size")
        return self._append_transition_for_kind(
            conn,
            expected_kind="product_iteration",
            target_state="evidence_ready",
            **kwargs,
        )

    def record_iteration_evaluation(
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
        validate_contract("evaluation_receipt", evaluation)
        verify_signed(evaluation, self._verification_keys)
        locked = self._repository.lock_instance(conn, workflow_id)
        self._require_kind(locked, "product_iteration")
        if locked["current_sequence"] != expected_sequence:
            raise ValueError("evaluation expected sequence is stale")
        if locked["current_state"] != "evidence_ready":
            raise ValueError("evaluation requires evidence_ready state")
        state = self._projection_state(conn, locked)
        definition = state["definition"]
        require_evaluation_parity(state, definition, evaluation)
        if evaluation["recommendation"] == "promote":
            if approval_request is None:
                raise ValueError("promotion recommendation requires approval request")
            if approval_request.get(
                "workflow_id"
            ) != workflow_id or approval_request.get(
                "action_hash"
            ) != promotion_request_hash(
                definition, evaluation
            ):
                raise ValueError("promotion approval request identity mismatch")
        elif approval_request is not None:
            raise ValueError("non-promotion evaluation cannot request release approval")
        event = self._append_transition_for_kind(
            conn,
            workflow_id=workflow_id,
            expected_sequence=expected_sequence,
            target_state="decision_pending",
            idempotency_key=idempotency_key,
            actor=actor,
            expected_kind="product_iteration",
            typed_receipt=("evaluation_receipt", evaluation),
        )
        if approval_request is not None:
            self.request_approval(conn, approval_request)
        return event

    def finalize_iteration_decision(
        self,
        conn,
        *,
        workflow_id: str,
        expected_sequence: int,
        target_state: str,
        actor: dict[str, Any],
        idempotency_key: str,
        approval_consumption_id: str | None = None,
        release_effect_receipt_id: str | None = None,
        release_workflow_id: str | None = None,
    ) -> dict[str, Any]:
        locked, retry = self._begin_append(
            conn,
            workflow_id,
            expected_sequence,
            idempotency_key,
            lambda prior: (
                prior["event_type"] == "transition"
                and prior["payload"].get("to_state") == target_state
                and prior["payload"].get("release_workflow_id") == release_workflow_id
            ),
        )
        self._require_kind(locked, "product_iteration")
        if retry:
            return retry
        state = self._projection_state(conn, locked)
        evaluation = state.get("evaluation")
        definition = state.get("definition")
        if not evaluation or not definition:
            raise ValueError("iteration decision has no evaluation")
        expected = {
            "reject": "rejected",
            "inconclusive": "inconclusive",
            "promote": "promoted",
        }.get(evaluation["recommendation"])
        if expected != target_state:
            raise ValueError(
                "iteration target does not match evaluation recommendation"
            )
        if target_state == "promoted":
            if not release_workflow_id:
                raise ValueError("promotion requires an exact release workflow ID")
            self._require_release_effect(
                conn,
                workflow_id=workflow_id,
                definition=definition,
                evaluation=evaluation,
                approval_consumption_id=approval_consumption_id,
                release_effect_receipt_id=release_effect_receipt_id,
            )
        elif (
            approval_consumption_id or release_effect_receipt_id or release_workflow_id
        ):
            raise ValueError("reject or inconclusive cannot carry release linkage")
        require_transition("product_iteration", locked["current_state"], target_state)
        return self._append_locked(
            conn,
            locked=locked,
            event_type="transition",
            idempotency_key=idempotency_key,
            actor=actor,
            payload={
                "from_state": locked["current_state"],
                "to_state": target_state,
                "approval_consumption_id": approval_consumption_id,
                "release_effect_receipt_id": release_effect_receipt_id,
                "release_workflow_id": release_workflow_id,
            },
            current_state=target_state,
            terminal=True,
        )

    def _projection_state(self, conn, locked: dict) -> dict:
        projection = self._repository.read_projection(conn, locked["workflow_id"])
        if (
            projection is None
            or projection["last_sequence"] != locked["current_sequence"]
        ):
            raise ValueError("upper workflow projection is unavailable")
        return dict(projection["state"])

    @staticmethod
    def _require_kind(locked: dict, expected: str) -> None:
        if locked["workflow_kind"] != expected:
            raise ValueError(f"workflow must use {expected} kind")
