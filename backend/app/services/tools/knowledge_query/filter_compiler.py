"""Tool-contract adapter for the neutral facet compiler."""

from __future__ import annotations

from typing import Iterable

from backend.app.services.knowledge_retrieval.contracts import FacetFilter
from backend.app.services.knowledge_retrieval.filter_compiler import (
    CompiledFacetFilters,
    compile_facet_filters as compile_neutral_facet_filters,
)
from .contracts import FacetPredicate


def compile_facet_filters(
    predicates: Iterable[FacetPredicate],
    *,
    record_alias: str = "record",
) -> CompiledFacetFilters:
    return compile_neutral_facet_filters(
        (
            FacetFilter(
                key=predicate.key,
                operator=predicate.operator,
                value=predicate.value,
            )
            for predicate in predicates
        ),
        record_alias=record_alias,
    )


__all__ = ["CompiledFacetFilters", "compile_facet_filters"]
