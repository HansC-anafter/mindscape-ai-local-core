"""The only public write facade for durable product-semantic workflows."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .cancellation import validate_cancellation
from .canonical_json import sha256_hex
from .compatibility import CompatibilityRegistry
from .contracts.v1.validator import validate_contract
from .controls import DurableControlPlaneMixin
from .errors import DurableWorkflowConflict
from .events import verify_events
from .facade_append import DurableAppendMixin
from .product_iterations import ProductIterationMixin
from .product_iteration_re_evaluation import (
    ProductIterationReEvaluationMixin,
)
from .product_iteration_closure import ProductIterationClosureMixin
from .product_releases import ProductReleaseMixin
from .repository import DurableWorkflowRepository
from .signature import Ed25519Signer
from .messages import validate_external_message
from .timers import validate_timer
from .transitions import initial_state, require_transition
from .typed_receipts import validate_typed_receipt

MAX_READ_PAGE = 50
MAX_SEGMENT_EVENTS = 10_000
MAX_SEGMENT_BYTES = 64 * 1024 * 1024


class DurableWorkflowFacade(
    DurableAppendMixin,
    DurableControlPlaneMixin,
    ProductIterationMixin,
    ProductIterationReEvaluationMixin,
    ProductIterationClosureMixin,
    ProductReleaseMixin,
):
    """Caller-owned-connection facade; it never commits or publishes."""

    def __init__(
        self,
        *,
        signer: Ed25519Signer,
        compatibility: CompatibilityRegistry,
        repository: DurableWorkflowRepository | None = None,
        verification_keys: dict[str, Any] | None = None,
    ) -> None:
        self._signer = signer
        self._compatibility = compatibility
        self._repository = repository or DurableWorkflowRepository()
        self._verification_keys = verification_keys or {
            signer.key_id: signer.public_key()
        }

    def open_workflow(self, conn, identity: dict[str, Any]) -> dict[str, Any]:
        if identity.get("workflow_kind") != "execution":
            raise ValueError(
                "non-execution workflow requires its specialized facade seam"
            )
        return self._open_workflow_kind(conn, identity)

    def _open_workflow_kind(
        self, conn, identity: dict[str, Any]
    ) -> dict[str, Any]:
        validate_contract("semantic_execution_identity", identity)
        self._compatibility.require(identity)
        return self._insert_identity(
            conn, identity, initial_state(identity["workflow_kind"])
        )

    def _insert_identity(
        self, conn, identity: dict[str, Any], state: str
    ) -> dict[str, Any]:
        self._repository.insert_instance(
            conn,
            {
                **identity,
                "execution_id": identity.get("execution_id"),
                "predecessor_segment_id": identity.get("predecessor_segment_id"),
                "predecessor_terminal_hash": identity.get(
                    "predecessor_terminal_hash"
                ),
                "semantic_identity": identity,
                "semantic_identity_hash": sha256_hex(identity),
                "current_state": state,
            },
        )
        return self._repository.read_instance(conn, identity["workflow_id"])

    def append_transition(
        self,
        conn,
        *,
        workflow_id: str,
        expected_sequence: int,
        target_state: str,
        idempotency_key: str,
        actor: dict[str, Any],
        typed_receipt: tuple[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return self._append_transition_for_kind(
            conn,
            workflow_id=workflow_id,
            expected_sequence=expected_sequence,
            target_state=target_state,
            idempotency_key=idempotency_key,
            actor=actor,
            expected_kind="execution",
            typed_receipt=typed_receipt,
        )

    def _append_transition_for_kind(
        self,
        conn,
        *,
        workflow_id: str,
        expected_sequence: int,
        target_state: str,
        idempotency_key: str,
        actor: dict[str, Any],
        expected_kind: str,
        typed_receipt: tuple[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        locked, retry = self._begin_append(
            conn,
            workflow_id,
            expected_sequence,
            idempotency_key,
            lambda prior: (
                prior["event_type"] == "transition"
                and prior["actor"] == actor
                and prior["payload"].get("to_state") == target_state
                and prior["payload"].get("typed_receipt")
                == (
                    {
                        "receipt_type": typed_receipt[0],
                        "receipt": typed_receipt[1],
                    }
                    if typed_receipt
                    else None
                )
            ),
        )
        if locked["workflow_kind"] != expected_kind:
            raise DurableWorkflowConflict(
                f"{locked['workflow_kind']} transition requires its specialized facade seam"
            )
        if retry:
            return retry
        terminal = require_transition(
            locked["workflow_kind"], locked["current_state"], target_state
        )
        if locked["workflow_kind"] == "execution" and terminal:
            raise DurableWorkflowConflict(
                "execution terminal transition requires append_execution_terminal"
            )
        payload: dict[str, Any] = {
            "from_state": locked["current_state"],
            "to_state": target_state,
        }
        if typed_receipt:
            receipt_type, receipt = typed_receipt
            validate_typed_receipt(receipt_type, receipt)
            payload["typed_receipt"] = {
                "receipt_type": receipt_type,
                "receipt": receipt,
            }
        return self._append_locked(
            conn,
            locked=locked,
            event_type="transition",
            idempotency_key=idempotency_key,
            actor=actor,
            payload=payload,
            current_state=target_state,
            terminal=terminal,
        )

    def append_typed_receipt(
        self,
        conn,
        *,
        workflow_id: str,
        expected_sequence: int,
        receipt_type: str,
        receipt: dict[str, Any],
        idempotency_key: str,
        actor: dict[str, Any],
    ) -> dict[str, Any]:
        return self._append_typed_receipt_for_kind(
            conn,
            workflow_id=workflow_id,
            expected_sequence=expected_sequence,
            receipt_type=receipt_type,
            receipt=receipt,
            idempotency_key=idempotency_key,
            actor=actor,
            expected_kind="execution",
        )

    def _append_typed_receipt_for_kind(
        self,
        conn,
        *,
        workflow_id: str,
        expected_sequence: int,
        receipt_type: str,
        receipt: dict[str, Any],
        idempotency_key: str,
        actor: dict[str, Any],
        expected_kind: str | None,
    ) -> dict[str, Any]:
        validate_typed_receipt(receipt_type, receipt)
        wrapped = {"receipt_type": receipt_type, "receipt": receipt}
        locked, retry = self._begin_append(
            conn,
            workflow_id,
            expected_sequence,
            idempotency_key,
            lambda prior: (
                prior["event_type"] == "transition"
                and prior["actor"] == actor
                and prior["payload"].get("typed_receipt") == wrapped
            ),
        )
        if (
            expected_kind is not None
            and locked["workflow_kind"] != expected_kind
        ):
            raise DurableWorkflowConflict(
                f"{locked['workflow_kind']} receipt requires its specialized facade seam"
            )
        if retry:
            return retry
        return self._append_locked(
            conn,
            locked=locked,
            event_type="transition",
            idempotency_key=idempotency_key,
            actor=actor,
            payload={"typed_receipt": wrapped},
            current_state=locked["current_state"],
            terminal=locked["terminal"],
        )

    def append_release_health(self, conn, **kwargs) -> dict[str, Any]:
        receipt = kwargs.pop("health_receipt")
        return self._append_typed_receipt_for_kind(
            conn,
            receipt_type="release_health_receipt",
            receipt=receipt,
            expected_kind="product_release",
            **kwargs,
        )

    def append_evidence_lifecycle(self, conn, **kwargs) -> dict[str, Any]:
        receipt = kwargs.pop("lifecycle_manifest_or_receipt")
        return self._append_typed_receipt_for_kind(
            conn,
            receipt_type="evidence_lifecycle_manifest",
            receipt=receipt,
            expected_kind=None,
            **kwargs,
        )

    def record_timer(
        self,
        conn,
        *,
        workflow_id: str,
        expected_sequence: int,
        timer: dict[str, Any],
        idempotency_key: str,
        actor: dict[str, Any],
    ) -> dict[str, Any]:
        validate_timer(timer)
        locked, retry = self._begin_append(
            conn,
            workflow_id,
            expected_sequence,
            idempotency_key,
            lambda prior: (
                prior["event_type"] == "timer_recorded"
                and prior["actor"] == actor
                and prior["payload"] == timer
            ),
        )
        if retry:
            return retry
        return self._append_locked(
            conn,
            locked=locked,
            event_type="timer_recorded",
            idempotency_key=idempotency_key,
            actor=actor,
            payload=timer,
            timer_id=timer["timer_id"],
            next_durable_deadline=timer["deadline"],
        )

    def record_external_message(
        self,
        conn,
        *,
        workflow_id: str,
        expected_sequence: int,
        message: dict[str, Any],
        idempotency_key: str,
        actor: dict[str, Any],
    ) -> dict[str, Any]:
        validate_external_message(message)
        locked, retry = self._begin_append(
            conn,
            workflow_id,
            expected_sequence,
            idempotency_key,
            lambda prior: (
                prior["event_type"] == "external_message_recorded"
                and prior["actor"] == actor
                and prior["payload"] == message
            ),
        )
        if retry:
            return retry
        return self._append_locked(
            conn,
            locked=locked,
            event_type="external_message_recorded",
            idempotency_key=idempotency_key,
            actor=actor,
            payload=message,
            external_message_id=message["external_message_id"],
        )

    def request_cancellation(
        self,
        conn,
        *,
        workflow_id: str,
        expected_sequence: int,
        reason: dict[str, Any],
        idempotency_key: str,
        actor: dict[str, Any],
    ) -> dict[str, Any]:
        validate_cancellation(reason)
        locked, retry = self._begin_append(
            conn,
            workflow_id,
            expected_sequence,
            idempotency_key,
            lambda prior: (
                prior["event_type"] == "cancellation_requested"
                and prior["actor"] == actor
                and prior["payload"] == reason
            ),
        )
        if retry:
            return retry
        if locked["terminal"]:
            raise DurableWorkflowConflict("terminal workflow cannot be cancelled")
        return self._append_locked(
            conn,
            locked=locked,
            event_type="cancellation_requested",
            idempotency_key=idempotency_key,
            actor=actor,
            payload=reason,
            cancellation_state="requested",
        )

    def rollover_segment(
        self,
        conn,
        *,
        workflow_id: str,
        expected_sequence: int,
        successor_workflow_id: str,
        idempotency_key: str,
        actor: dict[str, Any],
    ) -> dict[str, Any]:
        locked, retry = self._begin_append(
            conn,
            workflow_id,
            expected_sequence,
            idempotency_key,
            lambda prior: (
                prior["event_type"] == "segment_rollover"
                and prior["actor"] == actor
                and prior["payload"].get("successor_workflow_id")
                == successor_workflow_id
            ),
        )
        if retry:
            return self._repository.read_instance(conn, successor_workflow_id)
        if (
            locked["event_count"] < MAX_SEGMENT_EVENTS - 1
            and locked["canonical_event_bytes"] < MAX_SEGMENT_BYTES - 16_384
        ):
            raise DurableWorkflowConflict("segment rollover threshold is not reached")
        event = self._append_locked(
            conn,
            locked=locked,
            event_type="segment_rollover",
            idempotency_key=idempotency_key,
            actor=actor,
            payload={"successor_workflow_id": successor_workflow_id},
            terminal=True,
        )
        successor_identity = deepcopy(locked["semantic_identity"])
        successor_identity.update(
            {
                "workflow_id": successor_workflow_id,
                "root_workflow_id": locked["root_workflow_id"],
                "segment_id": (
                    f"{successor_workflow_id}:segment:{locked['segment_number'] + 1}"
                ),
                "segment_number": locked["segment_number"] + 1,
                "predecessor_segment_id": locked["segment_id"],
                "predecessor_terminal_hash": event["event_hash"],
            }
        )
        validate_contract("semantic_execution_identity", successor_identity)
        self._compatibility.require(successor_identity)
        return self._insert_identity(
            conn, successor_identity, locked["current_state"]
        )

    def read_current(self, conn, workflow_id: str) -> dict[str, Any]:
        return self._repository.read_instance(conn, workflow_id)

    def read_events_after(
        self, conn, workflow_id: str, cursor: int, limit: int = MAX_READ_PAGE
    ) -> list[dict[str, Any]]:
        if not 1 <= limit <= MAX_READ_PAGE:
            raise ValueError("durable event page limit must be between 1 and 50")
        return self._repository.read_events_after(conn, workflow_id, cursor, limit)

    def verify_chain(
        self, conn, workflow_id: str, *, cursor: int = 0, limit: int = 50
    ) -> str | None:
        events = self.read_events_after(conn, workflow_id, cursor, limit)
        try:
            return verify_events(events, self._verification_keys)
        except ValueError as exc:
            raise DurableWorkflowConflict(str(exc)) from exc
