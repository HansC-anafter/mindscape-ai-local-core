"""Pure exact-input contract variant selection."""

from __future__ import annotations

import copy
from typing import Any, Mapping, Sequence


def select_exact_input_variant(
    raw_variants: Any,
    *,
    inputs: Mapping[str, Any],
    payload_key: str,
    contract_label: str,
) -> dict[str, Any]:
    """Return the only matching payload or an empty mapping."""

    if raw_variants is None:
        return {}
    if not isinstance(raw_variants, Sequence) or isinstance(
        raw_variants,
        (str, bytes, bytearray),
    ):
        raise ValueError(f"{contract_label} variants must be a list")

    matches: list[dict[str, Any]] = []
    for raw_variant in raw_variants:
        if not isinstance(raw_variant, Mapping):
            raise ValueError(f"{contract_label} variant must be an object")
        when = raw_variant.get("when")
        payload = raw_variant.get(payload_key)
        if not isinstance(when, Mapping) or not isinstance(payload, Mapping):
            raise ValueError(
                f"{contract_label} variant requires when and {payload_key}"
            )
        input_name = when.get("input")
        expected = when.get("equals")
        if not isinstance(input_name, str) or not input_name.strip():
            raise ValueError(f"{contract_label} variant input must be non-empty")
        if isinstance(expected, (Mapping, list, tuple, set)) or expected is None:
            raise ValueError(f"{contract_label} variant equals must be scalar")
        actual = inputs.get(input_name.strip())
        if _normalized_scalar(actual) == _normalized_scalar(expected):
            matches.append(copy.deepcopy(dict(payload)))

    if len(matches) > 1:
        raise ValueError(f"multiple {contract_label} variants matched")
    return matches[0] if matches else {}


def _normalized_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value or "").strip()


__all__ = ["select_exact_input_variant"]
