"""Strict public contracts for the single knowledge_query tool."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ResourceFilters(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_apps: tuple[str, ...] = Field(default=(), max_length=16)
    source_ids: tuple[str, ...] = Field(default=(), max_length=64)
    owner_capabilities: tuple[str, ...] = Field(default=(), max_length=16)
    source_kinds: tuple[
        Literal["object", "artifact", "memory", "document"], ...
    ] = Field(default=(), max_length=8)
    record_kinds: tuple[str, ...] = Field(default=(), max_length=16)

    @model_validator(mode="after")
    def normalize_source_ids(self) -> "ResourceFilters":
        if any(not item.strip() for item in self.source_ids):
            raise ValueError("knowledge_query_source_id_empty")
        object.__setattr__(
            self,
            "source_ids",
            tuple(sorted({item.strip() for item in self.source_ids})),
        )
        return self


class CitationRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    citation_id: str = Field(
        pattern=(
            r"^(external_doc|projection_record|evidence_unit|"
            r"graph_mention|community_report):[A-Za-z0-9_.:-]+$"
        ),
        max_length=512,
    )
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class FacetPredicate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(pattern=r"^[a-z0-9_.-]+$", max_length=128)
    operator: Literal["eq", "in", "gt", "gte", "lt", "lte"]
    value: Any

    @model_validator(mode="after")
    def validate_value_shape(self) -> "FacetPredicate":
        if self.operator == "in":
            if (
                not isinstance(self.value, list)
                or not 1 <= len(self.value) <= 20
            ):
                raise ValueError("knowledge_query_facet_in_values_required")
        elif isinstance(self.value, (dict, list)):
            raise ValueError("knowledge_query_facet_scalar_required")
        return self


class KnowledgeQueryInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    operation: Literal[
        "search",
        "aggregate",
        "fetch_by_citation",
        "explain_coverage",
    ] = "search"
    query: Optional[str] = Field(default=None, max_length=8000)
    retrieval_mode: Literal[
        "hybrid",
        "local_graph",
        "multi_hop",
        "global_graph",
    ] = "hybrid"
    scope: Literal["workspace", "active_group"] = "workspace"
    modality_filter: Optional[
        Literal["text", "image", "video", "audio"]
    ] = None
    resource_filters: ResourceFilters = Field(
        default_factory=ResourceFilters
    )
    facet_predicates: tuple[FacetPredicate, ...] = Field(
        default=(),
        max_length=12,
    )
    query_evidence_refs: tuple[CitationRef, ...] = Field(
        default=(),
        max_length=8,
    )
    citations: tuple[CitationRef, ...] = Field(default=(), max_length=20)
    group_by: Optional[str] = Field(
        default=None,
        pattern=r"^[a-z0-9_.-]+$",
        max_length=128,
    )
    measure: Optional[Literal["count", "distinct_count"]] = None
    limit: int = Field(default=10, ge=1, le=20)

    @model_validator(mode="after")
    def validate_operation_shape(self) -> "KnowledgeQueryInput":
        if (
            self.operation == "search"
            and not (self.query or "").strip()
            and not self.query_evidence_refs
        ):
            raise ValueError("knowledge_query_text_required")
        if self.operation == "fetch_by_citation" and not self.citations:
            raise ValueError("knowledge_query_citations_required")
        if self.operation == "aggregate" and (
            not self.group_by or not self.measure
        ):
            raise ValueError("knowledge_query_aggregate_shape_required")
        if self.operation != "search" and self.retrieval_mode != "hybrid":
            raise ValueError("knowledge_query_mode_only_for_search")
        if self.operation != "search" and self.resource_filters.source_ids:
            raise ValueError(
                "knowledge_query_source_ids_only_for_search"
            )
        return self


__all__ = [
    "CitationRef",
    "FacetPredicate",
    "KnowledgeQueryInput",
    "ResourceFilters",
]
