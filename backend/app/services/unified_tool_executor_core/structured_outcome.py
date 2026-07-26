"""Artifact-neutral interpretation of structured tool completion evidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping


StructuredOutcomeKind = Literal["completed", "waiting", "blocked"]


@dataclass(frozen=True)
class StructuredToolOutcome:
    kind: StructuredOutcomeKind
    review_requirements: tuple[str, ...] = ()
    blocking_codes: tuple[str, ...] = ()
    review_binding_sha256: str | None = None


def classify_structured_tool_outcome(
    result: Any,
) -> StructuredToolOutcome:
    """Classify an optional preflight result without tool-specific literals."""
    if not isinstance(result, Mapping):
        return StructuredToolOutcome(kind="completed")
    if result.get("artifact_created") is not False:
        return StructuredToolOutcome(kind="completed")
    review_requirements = _bounded_strings(
        result.get("review_requirements")
    )
    blocking_codes = _bounded_strings(result.get("blocking_codes"))
    binding = result.get("review_binding_sha256")
    review_binding_sha256 = (
        binding
        if isinstance(binding, str) and len(binding) == 64
        else None
    )
    if blocking_codes:
        return StructuredToolOutcome(
            kind="blocked",
            review_requirements=review_requirements,
            blocking_codes=blocking_codes,
            review_binding_sha256=review_binding_sha256,
        )
    if review_requirements:
        return StructuredToolOutcome(
            kind="waiting",
            review_requirements=review_requirements,
            review_binding_sha256=review_binding_sha256,
        )
    return StructuredToolOutcome(kind="completed")


def _bounded_strings(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(
        item
        for item in value[:20]
        if isinstance(item, str) and item
    )


__all__ = [
    "StructuredOutcomeKind",
    "StructuredToolOutcome",
    "classify_structured_tool_outcome",
]
