"""Evidence-lifecycle validation on the shared durable ledger."""

from .contracts.v1.validator import validate_contract


def validate_evidence_lifecycle(payload: dict) -> None:
    validate_contract("evidence_lifecycle_manifest", payload)
