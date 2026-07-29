"""Bounded requests and citation-aware results for the canonical reader."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping, Optional

from backend.app.services.knowledge_authorization import RetrievalAccessContext


RetrievalMode = Literal["hybrid", "local_graph", "multi_hop", "global_graph"]
KNOWLEDGE_RETRIEVAL_RUNTIME_REVISION = (
    "knowledge-retrieval.cjk-graph-seed.v4"
)


@dataclass(frozen=True)
class FacetFilter:
    key: str
    operator: Literal["eq", "in", "gt", "gte", "lt", "lte"]
    value: Any


@dataclass(frozen=True)
class CitationLookup:
    citation_id: str
    content_hash: str


@dataclass(frozen=True)
class KnowledgeAggregateRequest:
    access_context: RetrievalAccessContext
    scope_type: Literal["workspace", "group"]
    scope_id: str
    group_by: str
    measure: Literal["count", "distinct_count"]
    source_apps: tuple[str, ...] = ()
    owner_capabilities: tuple[str, ...] = ()
    source_kinds: tuple[str, ...] = ()
    record_kinds: tuple[str, ...] = ()
    facet_filters: tuple[FacetFilter, ...] = ()
    limit: int = 10


@dataclass(frozen=True)
class KnowledgeCitationFetchRequest:
    access_context: RetrievalAccessContext
    scope_type: Literal["workspace", "group"]
    scope_id: str
    citations: tuple[CitationLookup, ...]


@dataclass(frozen=True)
class KnowledgeCoverageRequest:
    access_context: RetrievalAccessContext
    scope_type: Literal["workspace", "group"]
    scope_id: str
    source_apps: tuple[str, ...] = ()
    owner_capabilities: tuple[str, ...] = ()
    source_kinds: tuple[str, ...] = ()
    limit: int = 20


@dataclass(frozen=True)
class KnowledgeRetrievalRequest:
    query: str
    access_context: RetrievalAccessContext
    scope_type: Literal["workspace", "group"]
    scope_id: str
    top_k: int = 5
    source_apps: tuple[str, ...] = ()
    owner_capabilities: tuple[str, ...] = ()
    retrieval_mode: RetrievalMode = "hybrid"
    modality_filter: Optional[Literal["text", "image", "video", "audio"]] = None
    query_evidence_refs: tuple[CitationLookup, ...] = ()

    def __post_init__(self) -> None:
        if not self.query.strip() and not self.query_evidence_refs:
            raise ValueError("knowledge_query_text_required")
        if not self.scope_id.strip():
            raise ValueError("knowledge_query_scope_required")
        if not 1 <= self.top_k <= 20:
            raise ValueError("knowledge_query_limit_out_of_bounds")
        object.__setattr__(
            self,
            "source_apps",
            tuple(sorted(set(filter(None, self.source_apps)))),
        )
        object.__setattr__(
            self,
            "owner_capabilities",
            tuple(sorted(set(filter(None, self.owner_capabilities)))),
        )
        if len(self.query_evidence_refs) > 8:
            raise ValueError(
                "knowledge_query_evidence_ref_limit_exceeded"
            )


@dataclass(frozen=True)
class AuthorizedKnowledgeHit:
    knowledge_resource_id: str
    security_label_id: str
    authz_revision: int
    projection_revision_id: Optional[str]
    source_app: str
    source_id: str
    content: str
    metadata: Mapping[str, Any]
    score: float
    channels: tuple[str, ...]
    citation: Mapping[str, Any]


@dataclass(frozen=True)
class KnowledgeRetrievalResult:
    hits: tuple[AuthorizedKnowledgeHit, ...]
    requested_mode: RetrievalMode
    executed_mode: RetrievalMode
    candidate_count: int
    final_authorized_count: int
    transaction_count: int
    degraded_reasons: tuple[str, ...]
    authorization_receipt_digest: str
    graph_metrics: Mapping[str, int] | None = None
    fusion_revision: str = "none"
    channel_coverage: Mapping[str, Any] | None = None


__all__ = [
    "AuthorizedKnowledgeHit",
    "CitationLookup",
    "FacetFilter",
    "KnowledgeAggregateRequest",
    "KnowledgeCitationFetchRequest",
    "KnowledgeCoverageRequest",
    "KnowledgeRetrievalRequest",
    "KnowledgeRetrievalResult",
    "KNOWLEDGE_RETRIEVAL_RUNTIME_REVISION",
    "RetrievalMode",
]
