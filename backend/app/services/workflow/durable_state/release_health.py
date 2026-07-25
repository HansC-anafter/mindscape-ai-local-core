"""Release-health contract validation on the shared durable ledger."""

from .contracts.v1.validator import validate_contract


def validate_release_health(payload: dict) -> None:
    validate_contract("release_health_receipt", payload)
