"""Bounded authorization-aware local and multi-hop graph SQL leaf."""

from __future__ import annotations

from typing import Any

from psycopg2.extras import RealDictCursor

from backend.app.services.knowledge_authorization import RetrievalAccessContext
from backend.app.services.knowledge_retrieval.contracts import CitationLookup
from backend.app.services.knowledge_retrieval.query_seed import (
    hydrate_authorized_query_seed,
    websearch_query_from_seed,
)
from backend.app.services.knowledge_retrieval.store import (
    AuthorizationAwareKnowledgeRetrievalStore,
)

from .query_store_common import (
    AUTHORIZED_PROJECTIONS_CTE,
    common_parameters,
)


class AuthorizationAwareKnowledgeGraphNeighborhoodMixin:
    def fetch_neighborhood_candidates(
        self,
        *,
        query: str,
        context: RetrievalAccessContext,
        scope_type: str,
        scope_id: str,
        source_apps: tuple[str, ...],
        owner_capabilities: tuple[str, ...],
        modality_filter: str | None,
        max_hops: int,
        max_nodes: int,
        max_edges: int,
        result_limit: int,
        query_evidence_refs: tuple[CitationLookup, ...] = (),
    ) -> tuple[
        list[dict[str, Any]],
        dict[str, int],
        tuple[tuple[str, int], ...],
    ]:
        connection = self._connection_factory()
        try:
            cursor = connection.cursor(cursor_factory=RealDictCursor)
            AuthorizationAwareKnowledgeRetrievalStore._set_local_context(
                cursor,
                context,
            )
            seed_query, query_seed_bindings = hydrate_authorized_query_seed(
                cursor,
                context=context,
                scope_type=scope_type,
                scope_id=scope_id,
                citations=query_evidence_refs,
            )
            effective_query = (
                websearch_query_from_seed(
                    explicit_query=query,
                    seed_query=seed_query,
                )
                if query_evidence_refs
                else query
            )
            common = common_parameters(
                context=context,
                scope_type=scope_type,
                scope_id=scope_id,
                source_apps=source_apps,
                owner_capabilities=owner_capabilities,
                modality_filter=modality_filter,
            )
            cursor.execute(
                AUTHORIZED_PROJECTIONS_CTE
                + """
                SELECT
                    entity.entity_id,
                    entity.canonical_key,
                    MAX(mention.confidence) AS seed_score
                FROM authorized_projections AS authorized
                JOIN knowledge_graph_mentions AS mention
                  ON mention.projection_revision_id =
                     authorized.projection_revision_id
                 AND mention.knowledge_resource_id =
                     authorized.knowledge_resource_id
                 AND mention.security_label_id =
                     authorized.security_label_id
                JOIN knowledge_graph_entities AS entity
                  ON entity.entity_id = mention.entity_id
                WHERE (
                    entity.canonical_key ILIKE %s
                    OR mention.surface_text ILIKE %s
                    OR to_tsvector(
                        'simple',
                        entity.canonical_key || ' ' || mention.surface_text
                    ) @@ websearch_to_tsquery('simple', %s)
                )
                  AND (
                      %s::text IS NULL
                      OR EXISTS (
                          SELECT 1
                          FROM knowledge_embedding_channel_receipts AS channel
                          WHERE channel.projection_revision_id =
                                authorized.projection_revision_id
                            AND channel.evidence_unit_row_id =
                                mention.evidence_unit_row_id
                            AND channel.modality = %s
                            AND channel.state = 'active'
                      )
                  )
                GROUP BY entity.entity_id, entity.canonical_key
                ORDER BY seed_score DESC, entity.entity_id
                LIMIT %s
                """,
                (
                    *common,
                    f"%{effective_query}%",
                    f"%{effective_query}%",
                    effective_query,
                    modality_filter,
                    modality_filter,
                    min(20, max_nodes),
                ),
            )
            seed_rows = [dict(row) for row in cursor.fetchall()]
            depths = {str(row["entity_id"]): 0 for row in seed_rows}
            frontier = set(depths)
            edges: dict[str, dict[str, Any]] = {}
            for depth in range(1, max_hops + 1):
                if (
                    not frontier
                    or len(depths) >= max_nodes
                    or len(edges) >= max_edges
                ):
                    break
                cursor.execute(
                    AUTHORIZED_PROJECTIONS_CTE
                    + """
                    SELECT
                        relation.relation_id,
                        relation.source_entity_id,
                        relation.target_entity_id,
                        relation.relation_kind,
                        relation.origin,
                        relation.confidence,
                        relation.supporting_citations,
                        relation.projection_revision_id,
                        authorized.knowledge_resource_id,
                        authorized.security_label_id,
                        authorized.authz_revision
                    FROM authorized_projections AS authorized
                    JOIN knowledge_graph_relations AS relation
                      ON relation.projection_revision_id =
                         authorized.projection_revision_id
                     AND relation.visibility_partition_hash =
                         authorized.visibility_partition_hash
                    WHERE
                        relation.source_entity_id = ANY(%s::text[])
                        OR relation.target_entity_id = ANY(%s::text[])
                    ORDER BY relation.confidence DESC, relation.relation_id
                    LIMIT %s
                    """,
                    (
                        *common,
                        sorted(frontier),
                        sorted(frontier),
                        max_edges - len(edges),
                    ),
                )
                next_frontier: set[str] = set()
                for row in cursor.fetchall():
                    edge = dict(row)
                    edge_id = str(edge["relation_id"])
                    edges.setdefault(edge_id, edge)
                    for endpoint in (
                        str(edge["source_entity_id"]),
                        str(edge["target_entity_id"]),
                    ):
                        if endpoint not in depths and len(depths) < max_nodes:
                            depths[endpoint] = depth
                            next_frontier.add(endpoint)
                frontier = next_frontier

            if not depths:
                connection.commit()
                return (
                    [],
                    {
                        "seed_count": 0,
                        "visited_nodes": 0,
                        "visited_edges": 0,
                    },
                    query_seed_bindings,
                )
            cursor.execute(
                AUTHORIZED_PROJECTIONS_CTE
                + """
                SELECT
                    mention.mention_id,
                    mention.entity_id,
                    mention.surface_text,
                    mention.mention_type,
                    mention.confidence,
                    mention.citation,
                    mention.evidence_unit_row_id,
                    mention.projection_record_id,
                    evidence.unit_key,
                    evidence.unit_kind,
                    evidence.owner_asset_ref,
                    evidence.media_type,
                    evidence.anchor,
                    evidence.content_hash AS evidence_content_hash,
                    record.search_text AS record_text,
                    record.values AS record_values,
                    record.content_hash AS record_content_hash,
                    document.id AS external_doc_id,
                    document.content AS document_content,
                    document.metadata AS document_metadata,
                    authorized.*
                FROM authorized_projections AS authorized
                JOIN knowledge_graph_mentions AS mention
                  ON mention.projection_revision_id =
                     authorized.projection_revision_id
                 AND mention.knowledge_resource_id =
                     authorized.knowledge_resource_id
                 AND mention.security_label_id =
                     authorized.security_label_id
                LEFT JOIN knowledge_evidence_units AS evidence
                  ON evidence.evidence_unit_row_id =
                     mention.evidence_unit_row_id
                 AND evidence.projection_revision_id =
                     authorized.projection_revision_id
                LEFT JOIN knowledge_projection_records AS record
                  ON record.projection_record_id =
                     mention.projection_record_id
                 AND record.projection_revision_id =
                     authorized.projection_revision_id
                LEFT JOIN external_docs AS document
                  ON document.projection_revision_id =
                     authorized.projection_revision_id
                 AND document.knowledge_resource_id =
                     authorized.knowledge_resource_id
                 AND (
                     document.metadata->>'chunk_id' = evidence.unit_key
                     OR document.source_id = evidence.unit_key
                 )
                WHERE mention.entity_id = ANY(%s::text[])
                  AND (
                      %s::text IS NULL
                      OR EXISTS (
                          SELECT 1
                          FROM knowledge_embedding_channel_receipts AS channel
                          WHERE channel.projection_revision_id =
                                authorized.projection_revision_id
                            AND channel.evidence_unit_row_id =
                                mention.evidence_unit_row_id
                            AND channel.modality = %s
                            AND channel.state = 'active'
                      )
                  )
                ORDER BY mention.confidence DESC, mention.mention_id
                LIMIT %s
                """,
                (
                    *common,
                    sorted(depths),
                    modality_filter,
                    modality_filter,
                    min(max_nodes, max(result_limit * 4, result_limit)),
                ),
            )
            rows = []
            for raw in cursor.fetchall():
                row = dict(raw)
                entity_id = str(row["entity_id"])
                row["graph_depth"] = depths[entity_id]
                row["graph_relation_ids"] = [
                    edge_id
                    for edge_id, edge in edges.items()
                    if entity_id
                    in {
                        str(edge["source_entity_id"]),
                        str(edge["target_entity_id"]),
                    }
                ]
                rows.append(row)
            connection.commit()
            return (
                rows,
                {
                    "seed_count": len(seed_rows),
                    "visited_nodes": len(depths),
                    "visited_edges": len(edges),
                },
                query_seed_bindings,
            )
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


__all__ = ["AuthorizationAwareKnowledgeGraphNeighborhoodMixin"]
