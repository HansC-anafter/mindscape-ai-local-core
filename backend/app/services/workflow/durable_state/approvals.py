"""Approval contract validation at the durable facade boundary."""

from .contracts.v1.validator import validate_contract


def validate_approval(payload: dict) -> None:
    validate_contract("approval", payload)
