"""Bounded vector-DB read model for the Knowledge access surface."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from psycopg2.extras import RealDictCursor

from backend.app.services.knowledge_authorization.contracts import (
    RetrievalAccessContext,
)
from backend.app.services.knowledge_retrieval.store import (
    AuthorizationAwareKnowledgeRetrievalStore,
)
from backend.app.services.vector_search import VectorSearchService


_SUMMARY_SQL = """
WITH scoped AS (
    SELECT
        resource.knowledge_resource_id,
        resource.security_label_id,
        resource.owner_capability_code,
        resource.source_kind,
        resource.source_app,
        resource.source_id,
        resource.source_ref,
        resource.source_revision,
        resource.owner_scope_type,
        resource.owner_scope_id,
        resource.active AS resource_active,
        resource.deleted_at,
        resource.updated_at,
        label.classification,
        label.authz_revision
    FROM knowledge_resources AS resource
    JOIN knowledge_security_labels AS label
      ON label.security_label_id = resource.security_label_id
    WHERE resource.tenant_id = %s
      AND resource.owner_scope_type = 'workspace'
      AND resource.owner_scope_id = %s
),
filtered AS (
    SELECT *
    FROM scoped
    WHERE (
        %s::timestamptz IS NULL
        OR (updated_at, knowledge_resource_id) <
           (%s::timestamptz, %s::text)
    )
),
page AS (
    SELECT *
    FROM filtered
    ORDER BY updated_at DESC, knowledge_resource_id DESC
    LIMIT %s
),
grant_stats AS (
    SELECT
        page.knowledge_resource_id,
        COUNT(acl_grant.grant_id)::integer AS grant_count,
        COUNT(*) FILTER (
            WHERE acl_grant.effect = 'deny'
        )::integer AS deny_count,
        COALESCE(
            ARRAY_AGG(DISTINCT acl_grant.principal_type)
                FILTER (
                    WHERE acl_grant.effect = 'allow'
                      AND acl_grant.principal_type IS NOT NULL
                ),
            ARRAY[]::text[]
        ) AS allowed_principal_types
    FROM page
    LEFT JOIN knowledge_security_label_grants AS acl_grant
      ON acl_grant.security_label_id = page.security_label_id
     AND acl_grant.authz_revision = page.authz_revision
    GROUP BY page.knowledge_resource_id
),
agent_mask_stats AS (
    SELECT
        page.knowledge_resource_id,
        COUNT(mask.mask_id)::integer AS agent_mask_count,
        COUNT(*) FILTER (
            WHERE mask.effect = 'deny'
        )::integer AS agent_deny_count
    FROM page
    LEFT JOIN knowledge_resource_agent_masks AS mask
      ON mask.knowledge_resource_id = page.knowledge_resource_id
    GROUP BY page.knowledge_resource_id
),
active_projection AS (
    SELECT DISTINCT ON (projection.knowledge_resource_id)
        projection.knowledge_resource_id,
        projection.projection_revision_id,
        projection.descriptor_id,
        projection.descriptor_revision,
        projection.projector_revision,
        projection.embedding_profile_revision,
        projection.status AS projection_status,
        projection.evidence_unit_count,
        projection.record_count,
        projection.relation_count,
        projection.activated_at
    FROM knowledge_resource_projections AS projection
    JOIN page
      ON page.knowledge_resource_id = projection.knowledge_resource_id
    WHERE projection.active
    ORDER BY
        projection.knowledge_resource_id,
        projection.activated_at DESC NULLS LAST,
        projection.projection_revision_id DESC
),
channel_rows AS (
    SELECT
        projection.knowledge_resource_id,
        channel.modality,
        channel.state,
        SUM(channel.row_count)::bigint AS row_count,
        SUM(channel.byte_count)::bigint AS byte_count
    FROM active_projection AS projection
    JOIN knowledge_embedding_channel_receipts AS channel
      ON channel.projection_revision_id =
         projection.projection_revision_id
    GROUP BY
        projection.knowledge_resource_id,
        channel.modality,
        channel.state
),
channel_stats AS (
    SELECT
        knowledge_resource_id,
        JSONB_AGG(
            JSONB_BUILD_OBJECT(
                'modality', modality,
                'state', state,
                'row_count', row_count,
                'byte_count', byte_count
            )
            ORDER BY modality, state
        ) AS channels
    FROM channel_rows
    GROUP BY knowledge_resource_id
),
graph_stats AS (
    SELECT
        projection.knowledge_resource_id,
        COUNT(DISTINCT community.community_id)::integer AS community_count,
        COUNT(DISTINCT report.community_report_id)
            FILTER (WHERE report.active)::integer AS active_report_count
    FROM active_projection AS projection
    LEFT JOIN knowledge_graph_communities AS community
      ON community.projection_revision_id =
         projection.projection_revision_id
    LEFT JOIN knowledge_graph_community_reports AS report
      ON report.community_id = community.community_id
    GROUP BY projection.knowledge_resource_id
),
items AS (
    SELECT
        page.*,
        grant_stats.grant_count,
        grant_stats.deny_count,
        grant_stats.allowed_principal_types,
        agent_mask_stats.agent_mask_count,
        agent_mask_stats.agent_deny_count,
        active_projection.projection_revision_id,
        active_projection.descriptor_id,
        active_projection.descriptor_revision,
        active_projection.projector_revision,
        active_projection.embedding_profile_revision,
        active_projection.projection_status,
        active_projection.evidence_unit_count,
        active_projection.record_count,
        active_projection.relation_count,
        active_projection.activated_at,
        COALESCE(channel_stats.channels, '[]'::jsonb) AS channels,
        COALESCE(graph_stats.community_count, 0) AS community_count,
        COALESCE(graph_stats.active_report_count, 0)
            AS active_report_count
    FROM page
    JOIN grant_stats USING (knowledge_resource_id)
    JOIN agent_mask_stats USING (knowledge_resource_id)
    LEFT JOIN active_projection USING (knowledge_resource_id)
    LEFT JOIN channel_stats USING (knowledge_resource_id)
    LEFT JOIN graph_stats USING (knowledge_resource_id)
)
SELECT
    (SELECT COUNT(*)::integer FROM scoped) AS total_count,
    COALESCE(
        (
            SELECT JSONB_AGG(TO_JSONB(items) ORDER BY
                items.updated_at DESC,
                items.knowledge_resource_id DESC
            )
            FROM items
        ),
        '[]'::jsonb
    ) AS items,
    COALESCE(
        (
            SELECT JSONB_OBJECT_AGG(state, amount)
            FROM (
                SELECT
                    CASE
                        WHEN NOT resource_active THEN 'revoked'
                        WHEN projection_status IS NULL THEN 'missing'
                        ELSE projection_status
                    END AS state,
                    COUNT(*)::integer AS amount
                FROM (
                    SELECT
                        scoped.resource_active,
                        projection.status AS projection_status
                    FROM scoped
                    LEFT JOIN knowledge_resource_projections AS projection
                      ON projection.knowledge_resource_id =
                         scoped.knowledge_resource_id
                     AND projection.active
                ) AS resource_state
                GROUP BY state
            ) AS state_counts
        ),
        '{}'::jsonb
    ) AS state_counts
"""


_DETAIL_SQL = """
WITH selected AS (
    SELECT
        resource.*,
        label.classification,
        label.authz_revision,
        label.updated_at AS label_updated_at
    FROM knowledge_resources AS resource
    JOIN knowledge_security_labels AS label
      ON label.security_label_id = resource.security_label_id
    WHERE resource.knowledge_resource_id = %s
      AND resource.tenant_id = %s
      AND resource.owner_scope_type = 'workspace'
      AND resource.owner_scope_id = %s
),
active_projection AS (
    SELECT projection.*
    FROM knowledge_resource_projections AS projection
    JOIN selected
      ON selected.knowledge_resource_id =
         projection.knowledge_resource_id
    WHERE projection.active
    ORDER BY
        projection.activated_at DESC NULLS LAST,
        projection.projection_revision_id DESC
    LIMIT 1
),
grants AS (
    SELECT acl_grant.*
    FROM knowledge_security_label_grants AS acl_grant
    JOIN selected
      ON selected.security_label_id = acl_grant.security_label_id
     AND selected.authz_revision = acl_grant.authz_revision
    ORDER BY
        acl_grant.effect DESC,
        acl_grant.principal_type,
        acl_grant.principal_id,
        acl_grant.relation
    LIMIT 201
),
agent_masks AS (
    SELECT mask.*
    FROM knowledge_resource_agent_masks AS mask
    JOIN selected
      ON selected.knowledge_resource_id =
         mask.knowledge_resource_id
    ORDER BY mask.effect DESC, mask.agent_role
    LIMIT 101
),
channels AS (
    SELECT channel.*
    FROM knowledge_embedding_channel_receipts AS channel
    JOIN active_projection
      ON active_projection.projection_revision_id =
         channel.projection_revision_id
    ORDER BY channel.modality, channel.channel_id
    LIMIT 64
),
audits AS (
    SELECT audit.*
    FROM knowledge_acl_audit_log AS audit
    JOIN selected
      ON selected.knowledge_resource_id =
         audit.knowledge_resource_id
    ORDER BY audit.created_at DESC, audit.mutation_id DESC
    LIMIT 20
),
agent_audits AS (
    SELECT audit.*
    FROM knowledge_agent_mask_audit_log AS audit
    JOIN selected
      ON selected.knowledge_resource_id =
         audit.knowledge_resource_id
    ORDER BY audit.created_at DESC, audit.mutation_id DESC
    LIMIT 20
),
graph_stats AS (
    SELECT
        COUNT(DISTINCT entity.entity_id)::integer AS entity_count,
        COUNT(DISTINCT mention.mention_id)::integer AS mention_count,
        COUNT(DISTINCT relation.relation_id)::integer AS relation_count,
        COUNT(DISTINCT community.community_id)::integer
            AS community_count,
        COUNT(DISTINCT report.community_report_id)
            FILTER (WHERE report.active)::integer
            AS active_report_count
    FROM active_projection AS projection
    LEFT JOIN knowledge_graph_mentions AS mention
      ON mention.projection_revision_id =
         projection.projection_revision_id
    LEFT JOIN knowledge_graph_entities AS entity
      ON entity.entity_id = mention.entity_id
    LEFT JOIN knowledge_graph_relations AS relation
      ON relation.projection_revision_id =
         projection.projection_revision_id
    LEFT JOIN knowledge_graph_communities AS community
      ON community.projection_revision_id =
         projection.projection_revision_id
    LEFT JOIN knowledge_graph_community_reports AS report
      ON report.community_id = community.community_id
)
SELECT
    (SELECT TO_JSONB(selected) FROM selected) AS resource,
    (SELECT TO_JSONB(active_projection) FROM active_projection)
        AS projection,
    COALESCE(
        (SELECT JSONB_AGG(TO_JSONB(grants)) FROM grants),
        '[]'::jsonb
    ) AS grants,
    (SELECT COUNT(*)::integer FROM grants) AS returned_grant_count,
    COALESCE(
        (
            SELECT COUNT(*)::integer
            FROM knowledge_security_label_grants AS acl_grant
            JOIN selected
              ON selected.security_label_id =
                 acl_grant.security_label_id
             AND selected.authz_revision = acl_grant.authz_revision
        ),
        0
    ) AS total_grant_count,
    COALESCE(
        (SELECT JSONB_AGG(TO_JSONB(agent_masks)) FROM agent_masks),
        '[]'::jsonb
    ) AS agent_masks,
    COALESCE(
        (
            SELECT COUNT(*)::integer
            FROM knowledge_resource_agent_masks AS mask
            JOIN selected
              ON selected.knowledge_resource_id =
                 mask.knowledge_resource_id
        ),
        0
    ) AS total_agent_mask_count,
    COALESCE(
        (SELECT JSONB_AGG(TO_JSONB(channels)) FROM channels),
        '[]'::jsonb
    ) AS channels,
    COALESCE(
        (SELECT JSONB_AGG(TO_JSONB(audits)) FROM audits),
        '[]'::jsonb
    ) AS audits,
    COALESCE(
        (
            SELECT JSONB_AGG(TO_JSONB(agent_audits))
            FROM agent_audits
        ),
        '[]'::jsonb
    ) AS agent_audits,
    (SELECT TO_JSONB(graph_stats) FROM graph_stats) AS graph
"""


class KnowledgeAccessRepository:
    """One vector transaction per bounded governance operation."""

    def __init__(
        self,
        connection_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._connection_factory = (
            connection_factory or VectorSearchService()._get_connection
        )

    def list_summary(
        self,
        *,
        context: RetrievalAccessContext,
        workspace_id: str,
        limit: int,
        before_updated_at: datetime | None,
        before_resource_id: str | None,
    ) -> dict[str, Any]:
        connection = self._connection_factory()
        try:
            cursor = connection.cursor(cursor_factory=RealDictCursor)
            AuthorizationAwareKnowledgeRetrievalStore._set_local_context(
                cursor,
                context,
            )
            cursor.execute(
                _SUMMARY_SQL,
                (
                    context.tenant_id,
                    workspace_id,
                    before_updated_at,
                    before_updated_at,
                    before_resource_id or "",
                    limit + 1,
                ),
            )
            row = dict(cursor.fetchone() or {})
            connection.commit()
            items = list(row.get("items") or [])
            return {
                "items": items[:limit],
                "has_more": len(items) > limit,
                "total_count": int(row.get("total_count") or 0),
                "state_counts": dict(row.get("state_counts") or {}),
            }
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_detail(
        self,
        *,
        context: RetrievalAccessContext,
        workspace_id: str,
        resource_id: str,
    ) -> dict[str, Any] | None:
        connection = self._connection_factory()
        try:
            cursor = connection.cursor(cursor_factory=RealDictCursor)
            AuthorizationAwareKnowledgeRetrievalStore._set_local_context(
                cursor,
                context,
            )
            detail = self.detail_with_cursor(
                cursor,
                context=context,
                workspace_id=workspace_id,
                resource_id=resource_id,
            )
            connection.commit()
            return detail
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def detail_with_cursor(
        cursor: Any,
        *,
        context: RetrievalAccessContext,
        workspace_id: str,
        resource_id: str,
    ) -> dict[str, Any] | None:
        cursor.execute(
            _DETAIL_SQL,
            (
                resource_id,
                context.tenant_id,
                workspace_id,
            ),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        result = dict(row)
        if result.get("resource") is None:
            return None
        return result


__all__ = ["KnowledgeAccessRepository"]
