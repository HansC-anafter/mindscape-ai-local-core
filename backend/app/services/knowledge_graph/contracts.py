"""Pack-neutral graph write contracts with exact evidence provenance."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional


def _required(value: str, reason: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(reason)
    return normalized


@dataclass(frozen=True)
class GraphEntityWrite:
    canonical_key: str
    entity_type: str
    resolver_revision: str

    def __post_init__(self) -> None:
        _required(self.canonical_key, "knowledge_graph_entity_key_required")
        _required(self.entity_type, "knowledge_graph_entity_type_required")
        _required(
            self.resolver_revision,
            "knowledge_graph_resolver_revision_required",
        )


@dataclass(frozen=True)
class GraphMentionWrite:
    entity_key: str
    evidence_unit_key: Optional[str]
    record_key: Optional[str]
    surface_text: str
    mention_type: str
    confidence: float
    citation: Mapping[str, Any]
    extractor_revision: str
    model_revision: str
    prompt_revision: str

    def __post_init__(self) -> None:
        _required(self.entity_key, "knowledge_graph_mention_entity_required")
        _required(
            self.surface_text,
            "knowledge_graph_mention_surface_required",
        )
        _required(
            self.extractor_revision,
            "knowledge_graph_mention_extractor_required",
        )
        _required(
            self.model_revision,
            "knowledge_graph_mention_model_required",
        )
        _required(
            self.prompt_revision,
            "knowledge_graph_mention_prompt_required",
        )
        if not self.evidence_unit_key and not self.record_key:
            raise ValueError("knowledge_graph_mention_evidence_required")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("knowledge_graph_mention_confidence_invalid")


@dataclass(frozen=True)
class GraphRelationWrite:
    relation_key: str
    source_entity_key: str
    target_entity_key: str
    relation_kind: str
    origin: str
    confidence: float
    supporting_evidence_unit_keys: tuple[str, ...]
    supporting_citations: tuple[Mapping[str, Any], ...]
    extractor_revision: Optional[str] = None
    owner_relation_revision: Optional[str] = None

    def __post_init__(self) -> None:
        for value, reason in (
            (self.relation_key, "knowledge_graph_relation_key_required"),
            (self.source_entity_key, "knowledge_graph_relation_source_required"),
            (self.target_entity_key, "knowledge_graph_relation_target_required"),
            (self.relation_kind, "knowledge_graph_relation_kind_required"),
        ):
            _required(value, reason)
        if self.origin not in {"owner_declared", "extracted"}:
            raise ValueError("knowledge_graph_relation_origin_forbidden")
        if self.origin == "owner_declared" and not self.owner_relation_revision:
            raise ValueError("knowledge_graph_owner_relation_revision_required")
        if self.origin == "extracted" and not self.extractor_revision:
            raise ValueError("knowledge_graph_extractor_revision_required")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("knowledge_graph_relation_confidence_invalid")
        if not self.supporting_evidence_unit_keys:
            raise ValueError("knowledge_graph_relation_evidence_required")


@dataclass(frozen=True)
class GraphCommunityWrite:
    community_key: str
    level: int
    parent_community_key: Optional[str]
    entity_keys: tuple[str, ...]
    relation_keys: tuple[str, ...]
    affected_subgraph_hash: str
    full_rebuild_hash: str

    def __post_init__(self) -> None:
        _required(
            self.community_key,
            "knowledge_graph_community_key_required",
        )
        if self.level < 0:
            raise ValueError("knowledge_graph_community_level_invalid")
        if not self.entity_keys:
            raise ValueError("knowledge_graph_community_entities_required")
        if (
            len(self.affected_subgraph_hash) != 64
            or len(self.full_rebuild_hash) != 64
        ):
            raise ValueError("knowledge_graph_community_hash_invalid")


@dataclass(frozen=True)
class GraphCommunityReportWrite:
    community_key: str
    summary: str
    findings: tuple[Mapping[str, Any], ...]
    rank: float
    supporting_citations: tuple[Mapping[str, Any], ...]
    model_revision: str
    prompt_revision: str

    def __post_init__(self) -> None:
        _required(
            self.community_key,
            "knowledge_graph_report_community_required",
        )
        _required(self.summary, "knowledge_graph_report_summary_required")
        _required(
            self.model_revision,
            "knowledge_graph_report_model_required",
        )
        _required(
            self.prompt_revision,
            "knowledge_graph_report_prompt_required",
        )


@dataclass(frozen=True)
class GraphProjectionWrite:
    algorithm_revision: str
    resolver_revision: str
    visibility_partition_hash: str
    entities: tuple[GraphEntityWrite, ...]
    mentions: tuple[GraphMentionWrite, ...]
    relations: tuple[GraphRelationWrite, ...]
    communities: tuple[GraphCommunityWrite, ...] = ()
    reports: tuple[GraphCommunityReportWrite, ...] = ()

    def __post_init__(self) -> None:
        _required(
            self.algorithm_revision,
            "knowledge_graph_algorithm_revision_required",
        )
        _required(
            self.resolver_revision,
            "knowledge_graph_resolver_revision_required",
        )
        if len(self.visibility_partition_hash) != 64:
            raise ValueError(
                "knowledge_graph_visibility_partition_hash_invalid"
            )
        entity_keys = {entity.canonical_key for entity in self.entities}
        if len(entity_keys) != len(self.entities):
            raise ValueError("knowledge_graph_entity_duplicate")
        if any(mention.entity_key not in entity_keys for mention in self.mentions):
            raise ValueError("knowledge_graph_mention_entity_missing")
        if any(
            relation.source_entity_key not in entity_keys
            or relation.target_entity_key not in entity_keys
            for relation in self.relations
        ):
            raise ValueError("knowledge_graph_relation_entity_missing")
        relation_keys = {relation.relation_key for relation in self.relations}
        if len(relation_keys) != len(self.relations):
            raise ValueError("knowledge_graph_relation_duplicate")
        community_keys = {
            community.community_key for community in self.communities
        }
        if len(community_keys) != len(self.communities):
            raise ValueError("knowledge_graph_community_duplicate")
        if any(
            community.parent_community_key
            and community.parent_community_key not in community_keys
            for community in self.communities
        ):
            raise ValueError("knowledge_graph_parent_community_missing")
        if any(
            set(community.entity_keys) - entity_keys
            or set(community.relation_keys) - relation_keys
            for community in self.communities
        ):
            raise ValueError("knowledge_graph_community_member_missing")
        if any(
            report.community_key not in community_keys
            for report in self.reports
        ):
            raise ValueError("knowledge_graph_report_community_missing")


__all__ = [
    "GraphCommunityReportWrite",
    "GraphCommunityWrite",
    "GraphEntityWrite",
    "GraphMentionWrite",
    "GraphProjectionWrite",
    "GraphRelationWrite",
]
