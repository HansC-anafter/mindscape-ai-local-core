"""Graph SQL leaves under the projection writer's caller-owned transaction."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from backend.app.services.knowledge_authorization.write_contracts import (
    KnowledgeResourceBinding,
    KnowledgeResourceIdentity,
)

from .contracts import GraphProjectionWrite


def _id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256(
        "\x1f".join(str(part) for part in parts).encode("utf-8")
    ).hexdigest()
    return f"{prefix}_{digest}"


def _json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


class KnowledgeGraphRepository:
    def insert_generation(
        self,
        cursor: Any,
        *,
        projection_revision_id: str,
        identity: KnowledgeResourceIdentity,
        binding: KnowledgeResourceBinding,
        graph: GraphProjectionWrite,
        evidence_rows: dict[str, str],
        record_rows: dict[str, str],
    ) -> None:
        if (
            graph.visibility_partition_hash
            != binding.visibility_partition_hash
        ):
            raise ValueError(
                "knowledge_graph_visibility_partition_mismatch"
            )
        entity_rows: dict[str, str] = {}
        for entity in graph.entities:
            entity_id = _id(
                "kge",
                identity.tenant_id,
                identity.owner_scope_type,
                identity.owner_scope_id,
                entity.canonical_key,
                entity.entity_type,
                entity.resolver_revision,
            )
            entity_rows[entity.canonical_key] = entity_id
            cursor.execute(
                """
                INSERT INTO knowledge_graph_entities (
                    entity_id, tenant_id, scope_type, scope_id,
                    canonical_key, entity_type, resolver_revision
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (
                    tenant_id, scope_type, scope_id, canonical_key,
                    entity_type, resolver_revision
                ) DO NOTHING
                """,
                (
                    entity_id,
                    identity.tenant_id,
                    identity.owner_scope_type,
                    identity.owner_scope_id,
                    entity.canonical_key,
                    entity.entity_type,
                    entity.resolver_revision,
                ),
            )

        for mention in graph.mentions:
            evidence_row = (
                evidence_rows.get(mention.evidence_unit_key)
                if mention.evidence_unit_key
                else None
            )
            record_row = (
                record_rows.get(mention.record_key)
                if mention.record_key
                else None
            )
            if evidence_row is None and record_row is None:
                raise ValueError("knowledge_graph_mention_evidence_missing")
            mention_id = _id(
                "kgm",
                projection_revision_id,
                mention.entity_key,
                evidence_row or "",
                record_row or "",
                mention.surface_text,
                mention.extractor_revision,
            )
            cursor.execute(
                """
                INSERT INTO knowledge_graph_mentions (
                    mention_id, entity_id, projection_revision_id,
                    knowledge_resource_id, security_label_id,
                    evidence_unit_row_id, projection_record_id,
                    surface_text, mention_type, confidence, citation,
                    extractor_revision, model_revision, prompt_revision
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s::jsonb, %s, %s, %s
                )
                """,
                (
                    mention_id,
                    entity_rows[mention.entity_key],
                    projection_revision_id,
                    binding.knowledge_resource_id,
                    binding.security_label_id,
                    evidence_row,
                    record_row,
                    mention.surface_text,
                    mention.mention_type,
                    mention.confidence,
                    _json(mention.citation),
                    mention.extractor_revision,
                    mention.model_revision,
                    mention.prompt_revision,
                ),
            )

        relation_rows: dict[str, str] = {}
        visibility_hash = binding.visibility_partition_hash
        for relation in graph.relations:
            if any(
                unit_key not in evidence_rows
                for unit_key in relation.supporting_evidence_unit_keys
            ):
                raise ValueError("knowledge_graph_relation_evidence_missing")
            relation_id = _id(
                "kgr",
                projection_revision_id,
                relation.relation_key,
                relation.source_entity_key,
                relation.target_entity_key,
                relation.origin,
            )
            relation_rows[relation.relation_key] = relation_id
            cursor.execute(
                """
                INSERT INTO knowledge_graph_relations (
                    relation_id, projection_revision_id,
                    source_entity_id, target_entity_id, relation_kind,
                    origin, confidence, supporting_resource_ids,
                    supporting_citations, extractor_revision,
                    owner_relation_revision, visibility_partition_hash
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s::jsonb,
                    %s::jsonb, %s, %s, %s
                )
                """,
                (
                    relation_id,
                    projection_revision_id,
                    entity_rows[relation.source_entity_key],
                    entity_rows[relation.target_entity_key],
                    relation.relation_kind,
                    relation.origin,
                    relation.confidence,
                    _json([binding.knowledge_resource_id]),
                    _json(relation.supporting_citations),
                    relation.extractor_revision,
                    relation.owner_relation_revision,
                    visibility_hash,
                ),
            )

        graph_generation_id = _id(
            "kgg",
            projection_revision_id,
            graph.algorithm_revision,
            visibility_hash,
        )
        community_rows: dict[str, str] = {}
        for community in graph.communities:
            community_rows[community.community_key] = _id(
                "kgc",
                graph_generation_id,
                community.community_key,
            )
        for community in graph.communities:
            community_id = community_rows[community.community_key]
            parent_id = (
                community_rows.get(community.parent_community_key)
                if community.parent_community_key
                else None
            )
            cursor.execute(
                """
                INSERT INTO knowledge_graph_communities (
                    community_id, graph_generation_id,
                    projection_revision_id, knowledge_resource_id,
                    security_label_id, authz_revision,
                    algorithm_revision, level, parent_community_id,
                    visibility_partition_hash, affected_subgraph_hash,
                    full_rebuild_hash
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s
                )
                """,
                (
                    community_id,
                    graph_generation_id,
                    projection_revision_id,
                    binding.knowledge_resource_id,
                    binding.security_label_id,
                    binding.authz_revision,
                    graph.algorithm_revision,
                    community.level,
                    parent_id,
                    visibility_hash,
                    community.affected_subgraph_hash,
                    community.full_rebuild_hash,
                ),
            )
            for entity_key in community.entity_keys:
                cursor.execute(
                    """
                    INSERT INTO knowledge_graph_community_memberships (
                        community_id, entity_id, relation_ids
                    ) VALUES (%s, %s, %s::jsonb)
                    """,
                    (
                        community_id,
                        entity_rows[entity_key],
                        _json(
                            [
                                relation_rows[key]
                                for key in community.relation_keys
                            ]
                        ),
                    ),
                )

        for report in graph.reports:
            community_id = community_rows[report.community_key]
            cursor.execute(
                """
                INSERT INTO knowledge_graph_community_reports (
                    community_report_id, community_id, authz_revision,
                    visibility_partition_hash, summary, findings, rank,
                    supporting_citations, model_revision,
                    prompt_revision, active
                ) VALUES (
                    %s, %s, %s, %s, %s, %s::jsonb, %s,
                    %s::jsonb, %s, %s, FALSE
                )
                """,
                (
                    _id(
                        "kgcr",
                        community_id,
                        str(binding.authz_revision),
                        report.model_revision,
                        report.prompt_revision,
                    ),
                    community_id,
                    binding.authz_revision,
                    visibility_hash,
                    report.summary,
                    _json(report.findings),
                    report.rank,
                    _json(report.supporting_citations),
                    report.model_revision,
                    report.prompt_revision,
                ),
            )


__all__ = ["KnowledgeGraphRepository"]
