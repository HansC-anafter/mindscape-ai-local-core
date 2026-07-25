"""Runtime development-attestation validation without source-tree access."""

from __future__ import annotations

from .contracts.v1.validator import validate_contract


def verify_attestation(payload: dict, expected: dict[str, object]) -> None:
    validate_contract("development_change_attestation", payload)
    for field_name in (
        "contract_id",
        "provider",
        "decision",
        "repositories",
        "build_artifacts",
        "consumer_impact_receipt",
    ):
        if field_name in expected and payload.get(field_name) != expected[field_name]:
            raise ValueError(f"attestation {field_name} does not match runtime policy")
