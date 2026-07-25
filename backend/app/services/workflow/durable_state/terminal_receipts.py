"""Atomic execution terminal transition and signed receipt convergence."""

from __future__ import annotations

from .canonical_json import encode
from .contracts.v1.validator import validate_contract
from .transitions import require_transition

PARITY_FIELDS = (
    "workflow_id",
    "root_workflow_id",
    "execution_id",
    "attempt_id",
    "workspace_id",
    "capability_identity",
    "development_attestation_id",
    "development_attestation_sha256",
    "configuration_fingerprint",
    "environment_fingerprint",
    "data_fingerprint",
    "workflow_definition_version",
    "reducer_version",
    "effect_adapter_registry_version",
    "runtime_build_id",
)


def _append_execution_terminal(
    facade,
    conn,
    *,
    workflow_id: str,
    expected_sequence: int,
    target_state: str,
    receipt: dict,
    idempotency_key: str,
    actor: dict,
) -> dict:
    receipt_key = f"{idempotency_key}:receipt"
    existing = facade._repository.find_idempotent_event(
        conn, workflow_id, receipt_key
    )
    if existing:
        stored = existing["payload"]["typed_receipt"]["receipt"]
        if all(stored.get(key) == receipt.get(key) for key in receipt):
            return stored
        raise ValueError("terminal idempotency key was used for different input")

    locked = facade._repository.lock_instance(conn, workflow_id)
    if locked["current_sequence"] != expected_sequence:
        raise ValueError("terminal transition sequence is stale")
    if locked["workflow_kind"] != "execution":
        raise ValueError("execution terminal receipt requires execution workflow kind")
    if not require_transition("execution", locked["current_state"], target_state):
        raise ValueError("execution terminal target must be terminal")
    identity = locked["semantic_identity"]
    for field_name in PARITY_FIELDS:
        if receipt.get(field_name) != identity.get(field_name):
            raise ValueError(
                f"terminal receipt {field_name} does not match locked identity"
            )
    transition = facade._append_locked(
        conn,
        locked=locked,
        event_type="transition",
        idempotency_key=f"{idempotency_key}:transition",
        actor=actor,
        payload={
            "from_state": locked["current_state"],
            "to_state": target_state,
        },
        current_state=target_state,
        terminal=False,
    )
    unsigned = {
        **receipt,
        "terminal_sequence": transition["sequence"],
        "terminal_event_hash": transition["event_hash"],
    }
    unsigned.pop("signature", None)
    signature = facade._signer.sign(encode(unsigned))
    signed = {**unsigned, "signature": signature.value}
    validate_contract("execution_terminal_receipt", signed)
    after_transition = facade._repository.lock_instance(conn, workflow_id)
    facade._append_locked(
        conn,
        locked=after_transition,
        event_type="transition",
        idempotency_key=receipt_key,
        actor=actor,
        payload={
            "typed_receipt": {
                "receipt_type": "execution_terminal_receipt",
                "receipt": signed,
            }
        },
        current_state=target_state,
        terminal=True,
    )
    return signed
