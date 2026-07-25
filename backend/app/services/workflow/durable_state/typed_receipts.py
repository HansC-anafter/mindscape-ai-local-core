"""Registry for signed product-semantic receipts carried by the event chain."""

from __future__ import annotations

from .contracts.v1.validator import validate_contract

RECEIPT_SCHEMAS = frozenset(
    {
        "development_change_attestation",
        "evaluation_receipt",
        "evidence_lifecycle_manifest",
        "execution_terminal_receipt",
        "iteration_enrollment",
        "outcome_adapter_descriptor",
        "outcome_observation",
        "product_iteration",
        "release_health_receipt",
        "replay_envelope",
        "side_effect_receipt",
    }
)


def validate_typed_receipt(receipt_type: str, receipt: dict) -> None:
    if receipt_type not in RECEIPT_SCHEMAS:
        raise ValueError(f"unknown typed receipt: {receipt_type}")
    validate_contract(receipt_type, receipt)
