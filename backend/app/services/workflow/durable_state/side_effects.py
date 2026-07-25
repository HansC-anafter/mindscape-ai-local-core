"""Side-effect receipt validation at the durable facade boundary."""

from .contracts.v1.validator import validate_contract


def validate_side_effect(payload: dict) -> None:
    validate_contract("side_effect_receipt", payload)
