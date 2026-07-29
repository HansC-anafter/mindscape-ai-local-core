"""Compile owner-declared records and graph data into neutral write contracts."""

from __future__ import annotations

from dataclasses import asdict, replace
from typing import Any, Iterable, Mapping

from backend.app.services.knowledge_graph.contracts import (
    GraphCommunityReportWrite,
    GraphCommunityWrite,
    GraphEntityWrite,
    GraphMentionWrite,
    GraphProjectionWrite,
    GraphRelationWrite,
)

from .canonical_json import canonical_sha256
from .write_contracts import (
    ProjectionFacetWrite,
    ProjectionRecordWrite,
    RetrievableProjectionWrite,
)


def _mapping(value: Mapping[str, Any] | Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "model_dump"):
        return dict(value.model_dump(mode="python"))
    raise ValueError("owner_declared_projection_mapping_required")


def _compile_records(
    records: Iterable[Mapping[str, Any] | Any],
) -> tuple[ProjectionRecordWrite, ...]:
    compiled: list[ProjectionRecordWrite] = []
    for raw_value in records:
        raw = _mapping(raw_value)
        values = dict(raw.get("values") or {})
        citation = dict(raw.get("citation") or {})
        record_key = str(raw.get("record_key") or "").strip()
        search_text = str(raw.get("search_text") or "").strip()
        record_kind = str(raw.get("record_kind") or "").strip()
        if not record_key or not search_text or not record_kind:
            raise ValueError("owner_declared_projection_record_incomplete")
        facets = tuple(
            ProjectionFacetWrite(
                key=str(item["key"]),
                value_type=str(item["value_type"]),
                value=item["value"],
                ordinal=int(item.get("ordinal") or 0),
            )
            for item in (
                _mapping(value)
                for value in tuple(raw.get("facets") or ())
            )
        )
        compiled.append(
            ProjectionRecordWrite(
                record_kind=record_kind,
                record_key=record_key,
                search_text=search_text,
                citation=citation,
                values=values,
                content_hash=canonical_sha256(
                    {
                        "record_kind": record_kind,
                        "record_key": record_key,
                        "search_text": search_text,
                        "citation": citation,
                        "values": values,
                        "facets": [
                            {
                                "key": facet.key,
                                "value_type": facet.value_type,
                                "value": facet.value,
                                "ordinal": facet.ordinal,
                            }
                            for facet in facets
                        ],
                    }
                ),
                facets=facets,
            )
        )
    keys = {record.record_key for record in compiled}
    if len(keys) != len(compiled):
        raise ValueError("owner_declared_projection_record_duplicate")
    return tuple(compiled)


def _compile_graph(
    graph_value: Mapping[str, Any] | Any,
) -> GraphProjectionWrite:
    graph = _mapping(graph_value)
    entities = tuple(
        GraphEntityWrite(
            canonical_key=str(raw["canonical_key"]),
            entity_type=str(raw["entity_type"]),
            resolver_revision=str(
                raw.get("resolver_revision") or "owner-declared.v1"
            ),
        )
        for raw in (
            _mapping(value) for value in tuple(graph.get("entities") or ())
        )
    )
    mentions = tuple(
        GraphMentionWrite(
            entity_key=str(raw["entity_key"]),
            evidence_unit_key=(
                str(raw["evidence_unit_key"])
                if raw.get("evidence_unit_key")
                else None
            ),
            record_key=(
                str(raw["record_key"]) if raw.get("record_key") else None
            ),
            surface_text=str(raw["surface_text"]),
            mention_type=str(raw.get("mention_type") or "owner_declared"),
            confidence=float(raw.get("confidence", 1.0)),
            citation=dict(raw.get("citation") or {}),
            extractor_revision="owner-declared",
            model_revision="owner-declared",
            prompt_revision="owner-declared",
        )
        for raw in (
            _mapping(value) for value in tuple(graph.get("mentions") or ())
        )
    )
    relations = tuple(
        GraphRelationWrite(
            relation_key=str(raw["relation_key"]),
            source_entity_key=str(raw["source_entity_key"]),
            target_entity_key=str(raw["target_entity_key"]),
            relation_kind=str(raw["relation_kind"]),
            origin="owner_declared",
            confidence=float(raw.get("confidence", 1.0)),
            supporting_evidence_unit_keys=tuple(
                str(value)
                for value in tuple(
                    raw.get("supporting_evidence_unit_keys")
                    or ("chunk-0",)
                )
            ),
            supporting_citations=tuple(
                dict(value)
                for value in tuple(
                    raw.get("supporting_citations") or ()
                )
            ),
            owner_relation_revision=str(
                raw.get("owner_relation_revision")
                or "owner-declared.v1"
            ),
        )
        for raw in (
            _mapping(value) for value in tuple(graph.get("relations") or ())
        )
    )
    communities: list[GraphCommunityWrite] = []
    for raw in (
        _mapping(value) for value in tuple(graph.get("communities") or ())
    ):
        digest_input = {
            "community_key": str(raw["community_key"]),
            "level": int(raw.get("level") or 0),
            "parent_community_key": raw.get("parent_community_key"),
            "entity_keys": list(raw.get("entity_keys") or ()),
            "relation_keys": list(raw.get("relation_keys") or ()),
        }
        digest = canonical_sha256(digest_input)
        communities.append(
            GraphCommunityWrite(
                community_key=str(raw["community_key"]),
                level=int(raw.get("level") or 0),
                parent_community_key=(
                    str(raw["parent_community_key"])
                    if raw.get("parent_community_key")
                    else None
                ),
                entity_keys=tuple(
                    str(value)
                    for value in tuple(raw.get("entity_keys") or ())
                ),
                relation_keys=tuple(
                    str(value)
                    for value in tuple(raw.get("relation_keys") or ())
                ),
                affected_subgraph_hash=digest,
                full_rebuild_hash=digest,
            )
        )
    reports = tuple(
        GraphCommunityReportWrite(
            community_key=str(raw["community_key"]),
            summary=str(raw["summary"]),
            findings=tuple(
                dict(value)
                for value in tuple(raw.get("findings") or ())
            ),
            rank=float(raw.get("rank", 1.0)),
            supporting_citations=tuple(
                dict(value)
                for value in tuple(
                    raw.get("supporting_citations") or ()
                )
            ),
            model_revision="owner-declared",
            prompt_revision="owner-declared",
        )
        for raw in (
            _mapping(value) for value in tuple(graph.get("reports") or ())
        )
    )
    return GraphProjectionWrite(
        algorithm_revision=str(
            graph.get("algorithm_revision")
            or "owner-declared.communities.v1"
        ),
        resolver_revision=str(
            graph.get("resolver_revision")
            or "owner-declared.entities.v1"
        ),
        visibility_partition_hash="0" * 64,
        entities=entities,
        mentions=mentions,
        relations=relations,
        communities=tuple(communities),
        reports=reports,
    )


def enrich_document_projection(
    payload: RetrievableProjectionWrite,
    *,
    projection_records: Iterable[Mapping[str, Any] | Any] = (),
    owner_declared_graph: Mapping[str, Any] | Any | None = None,
) -> RetrievableProjectionWrite:
    """Return one complete generation; never mutate or side-write."""

    records = _compile_records(projection_records)
    graph = (
        _compile_graph(owner_declared_graph)
        if owner_declared_graph is not None
        else None
    )
    projection_hash = canonical_sha256(
        {
            "base_projection_hash": payload.projection_hash,
            "records": [
                {
                    "record_kind": record.record_kind,
                    "record_key": record.record_key,
                    "content_hash": record.content_hash,
                }
                for record in records
            ],
            "graph": asdict(graph) if graph is not None else None,
            "projector_revision": "document-index.owner-declared.v1",
        }
    )
    return replace(
        payload,
        projector_revision=(
            "document-index.owner-declared.v1"
            if records or graph is not None
            else payload.projector_revision
        ),
        facet_schema_revision=(
            "owner-declared-facets.v1"
            if records
            else payload.facet_schema_revision
        ),
        projection_hash=projection_hash,
        records=records,
        relation_count=len(graph.relations) if graph is not None else 0,
        graph_complete=graph is not None,
        graph_required=graph is not None,
        graph=graph,
    )


__all__ = ["enrich_document_projection"]
