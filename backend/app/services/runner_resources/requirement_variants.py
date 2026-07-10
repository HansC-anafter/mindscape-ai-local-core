"""Deterministic input-exact resource requirement variants."""

from __future__ import annotations

from typing import Any, Mapping

from backend.app.services.contract_variants import select_exact_input_variant


def select_requirement_variant(
    raw_variants: Any,
    *,
    inputs: Mapping[str, Any],
) -> dict[str, Any]:
    """Return the only exact-match variant or an empty mapping.

    Variant contracts are intentionally narrow: one scalar input equality and
    one resource_requirements object. Invalid or overlapping cases fail closed
    during requirement resolution instead of choosing by list order.
    """

    return select_exact_input_variant(
        raw_variants,
        inputs=inputs,
        payload_key="resource_requirements",
        contract_label="resource requirement",
    )


__all__ = ["select_requirement_variant"]
