"""Versioned extraction port and provenance validation; no provider router."""

from __future__ import annotations

from typing import Protocol, Sequence

from .contracts import GraphProjectionWrite


class KnowledgeGraphExtractor(Protocol):
    def extract(
        self,
        *,
        evidence_units: Sequence[object],
        records: Sequence[object],
    ) -> GraphProjectionWrite: ...


def validate_extraction_result(
    result: GraphProjectionWrite,
    *,
    admitted_evidence_unit_keys: set[str],
) -> GraphProjectionWrite:
    cited = {
        key
        for relation in result.relations
        for key in relation.supporting_evidence_unit_keys
    } | {
        mention.evidence_unit_key
        for mention in result.mentions
        if mention.evidence_unit_key
    }
    if cited - admitted_evidence_unit_keys:
        raise ValueError("knowledge_graph_extraction_evidence_not_admitted")
    return result


__all__ = ["KnowledgeGraphExtractor", "validate_extraction_result"]
