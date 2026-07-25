"""Atomic append and projection seam inherited by the durable facade."""

from __future__ import annotations

from typing import Any

from .canonical_json import sha256_hex
from .contracts.v1.validator import validate_contract
from .errors import DurableWorkflowConflict
from .events import build_signed_event
from .projections import project

MAX_SEGMENT_EVENTS = 10_000
MAX_SEGMENT_BYTES = 64 * 1024 * 1024


class DurableAppendMixin:
    def _begin_append(
        self,
        conn,
        workflow_id: str,
        expected: int,
        idempotency_key: str,
        matches,
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        locked = self._repository.lock_instance(conn, workflow_id)
        if locked["current_sequence"] == expected:
            return locked, None
        prior = self._repository.find_idempotent_event(
            conn, workflow_id, idempotency_key
        )
        if prior and matches(prior):
            return locked, prior
        raise DurableWorkflowConflict(
            f"expected sequence {expected}, found {locked['current_sequence']}"
        )

    def _append_locked(
        self,
        conn,
        *,
        locked: dict[str, Any],
        event_type: str,
        idempotency_key: str,
        actor: dict[str, Any],
        payload: dict[str, Any],
        current_state: str | None = None,
        terminal: bool | None = None,
        timer_id: str | None = None,
        external_message_id: str | None = None,
        next_durable_deadline=None,
        cancellation_state: str | None = None,
    ) -> dict[str, Any]:
        if locked["terminal"]:
            raise DurableWorkflowConflict(
                "terminal workflow is insert-closed"
            )
        payload_sha256 = sha256_hex(payload)
        prior = self._repository.find_idempotent_event(
            conn, locked["workflow_id"], idempotency_key
        )
        if prior:
            if (
                prior["event_type"] == event_type
                and prior["payload_sha256"] == payload_sha256
            ):
                return prior
            raise DurableWorkflowConflict(
                "idempotency key was used for different input"
            )
        contract_event = build_signed_event(
            self._signer,
            locked=locked,
            event_type=event_type,
            actor=actor,
            payload=payload,
        )
        event_hash = contract_event["event_hash"]
        canonical_bytes = contract_event["canonical_bytes"]
        if event_type != "segment_rollover" and (
            locked["event_count"] >= MAX_SEGMENT_EVENTS - 1
            or locked["canonical_event_bytes"] + canonical_bytes
            > MAX_SEGMENT_BYTES - 16_384
        ):
            raise DurableWorkflowConflict("segment rollover is required")
        if (
            event_type == "segment_rollover"
            and locked["canonical_event_bytes"] + canonical_bytes
            > MAX_SEGMENT_BYTES
        ):
            raise DurableWorkflowConflict(
                "segment byte boundary was exceeded"
            )
        validate_contract(
            "workflow_event",
            {
                key: value
                for key, value in contract_event.items()
                if key != "key_id"
            },
        )
        stored = {
            **contract_event,
            "idempotency_key": idempotency_key,
            "timer_id": timer_id,
            "external_message_id": external_message_id,
        }
        self._repository.insert_event(conn, stored)
        resulting_state = current_state or locked["current_state"]
        resulting_terminal = (
            locked["terminal"] if terminal is None else terminal
        )
        resulting_cancel = (
            cancellation_state
            if cancellation_state is not None
            else locked["cancellation_state"]
        )
        self._repository.advance_instance(
            conn,
            workflow_id=locked["workflow_id"],
            expected_sequence=locked["current_sequence"],
            event_hash=event_hash,
            event_bytes=canonical_bytes,
            current_state=resulting_state,
            terminal=resulting_terminal,
            next_durable_deadline=next_durable_deadline,
            cancellation_state=resulting_cancel,
        )
        prior_projection = self._repository.read_projection(
            conn, locked["workflow_id"]
        )
        if prior_projection is None:
            if locked["current_sequence"] != 0:
                raise DurableWorkflowConflict(
                    "current projection is missing for non-empty workflow"
                )
            prior_state = {
                "current_state": locked["current_state"],
                "cancellation_state": locked["cancellation_state"],
                "last_sequence": locked["current_sequence"],
                "last_event_hash": locked["current_event_hash"],
            }
        else:
            if (
                prior_projection["last_sequence"]
                != locked["current_sequence"]
            ):
                raise DurableWorkflowConflict(
                    "current projection sequence does not match aggregate"
                )
            prior_state = dict(prior_projection["state"])
        projection_state, state_hash = project(
            prior_state, contract_event
        )
        self._repository.upsert_projection(
            conn,
            workflow_id=locked["workflow_id"],
            sequence=contract_event["sequence"],
            reducer_version=locked["reducer_version"],
            state=projection_state,
            state_hash=state_hash,
        )
        return stored
