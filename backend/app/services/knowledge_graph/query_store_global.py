"""Authorization-aware global community-report SQL leaf."""

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


class AuthorizationAwareKnowledgeGraphGlobalMixin:
    def fetch_global_candidates(
        self,
        *,
        query: str,
        context: RetrievalAccessContext,
        scope_type: str,
        scope_id: str,
        source_apps: tuple[str, ...],
        owner_capabilities: tuple[str, ...],
        modality_filter: str | None,
        candidate_limit: int,
        query_evidence_refs: tuple[CitationLookup, ...] = (),
    ) -> tuple[
        list[dict[str, Any]],
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
                    report.community_report_id,
                    report.summary,
                    report.findings,
                    report.rank,
                    report.supporting_citations,
                    community.community_id,
                    community.level,
                    authorized.*,
                    ts_rank_cd(
                        to_tsvector(
                            'simple',
                            report.summary || ' ' || report.findings::text
                        ),
                        websearch_to_tsquery('simple', %s)
                    ) AS keyword_score
                FROM authorized_projections AS authorized
                JOIN knowledge_graph_communities AS community
                  ON community.projection_revision_id =
                     authorized.projection_revision_id
                 AND community.knowledge_resource_id =
                     authorized.knowledge_resource_id
                 AND community.security_label_id =
                     authorized.security_label_id
                 AND community.authz_revision =
                     authorized.authz_revision
                 AND community.visibility_partition_hash =
                     authorized.visibility_partition_hash
                JOIN knowledge_graph_community_reports AS report
                  ON report.community_id = community.community_id
                 AND report.active
                 AND report.authz_revision = authorized.authz_revision
                 AND report.visibility_partition_hash =
                     authorized.visibility_partition_hash
                ORDER BY
                    keyword_score DESC,
                    report.rank DESC,
                    report.community_report_id
                LIMIT %s
                """,
                (*common, effective_query, candidate_limit),
            )
            rows = [dict(row) for row in cursor.fetchall()]
            connection.commit()
            return rows, query_seed_bindings
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


__all__ = ["AuthorizationAwareKnowledgeGraphGlobalMixin"]
