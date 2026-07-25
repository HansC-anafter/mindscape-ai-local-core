"""Fail-closed JSON Schema validation for the v1 machine contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .manifest import SCHEMA_NAMES


class ContractValidationError(ValueError):
    """Raised when a contract payload does not match its exact schema."""


def load_schema(name: str) -> dict[str, Any]:
    if name not in SCHEMA_NAMES:
        raise ContractValidationError(f"unknown durable workflow schema: {name}")
    path = Path(__file__).resolve().parent / "schemas" / f"{name}.schema.json"
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return schema


def validate_contract(name: str, payload: dict[str, Any]) -> None:
    validator = Draft202012Validator(load_schema(name))
    errors = sorted(validator.iter_errors(payload), key=lambda item: list(item.path))
    if not errors:
        return
    rendered = "; ".join(
        f"{'/'.join(str(part) for part in error.path) or '<root>'}: {error.message}"
        for error in errors
    )
    raise ContractValidationError(f"{name} contract rejected: {rendered}")
