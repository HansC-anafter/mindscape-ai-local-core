"""Authorization-prefiltered aggregate, citation, and coverage SQL leaves."""

from __future__ import annotations

import json
from typing import Any

from psycopg2.extras import RealDictCursor

from backend.app.services.knowledge_authorization import RetrievalAccessContext

from .filter_compiler import CompiledFacetFilters
from .store import AuthorizationAwareKnowledgeRetrievalStore


_AUTHORIZED_PROJECTIONS_CTE = """
WITH request_principals AS (
    SELECT principal_type, principal_id
    FROM jsonb_to_recordset(%s::jsonb)
         AS principal(principal_type text, principal_id text)
),
authorized_projections AS (
    SELECT
        projection.projection_revision_id,
        projection.knowledge_resource_id,
        projection.status AS projection_status,
        resource.security_label_id,
        resource.source_app,
        resource.source_id,
        resource.source_ref,
        resource.source_kind,
        resource.owner_capability_code,
        label.authz_revision
    FROM knowledge_resource_projections AS projection
    JOIN knowledge_resources AS resource
      ON resource.knowledge_resource_id =
         projection.knowledge_resource_id
     AND resource.active
     AND resource.deleted_at IS NULL
    JOIN knowledge_security_labels AS label
      ON label.security_label_id = resource.security_label_id
    WHERE resource.tenant_id = %s
      AND resource.owner_scope_type = %s
      AND resource.owner_scope_id = %s
      AND projection.active
      AND projection.status IN (
          'active', 'degraded_channels', 'degraded_graph'
      )
      AND EXISTS (
          SELECT 1
          FROM knowledge_security_label_grants AS allowed
          JOIN request_principals AS principal
            ON principal.principal_type = allowed.principal_type
           AND principal.principal_id = allowed.principal_id
          WHERE allowed.security_label_id = label.security_label_id
            AND allowed.authz_revision = label.authz_revision
            AND allowed.effect = 'allow'
            AND (allowed.valid_from IS NULL OR allowed.valid_from <= NOW())
            AND (allowed.valid_until IS NULL OR allowed.valid_until > NOW())
      )
      AND NOT EXISTS (
          SELECT 1
          FROM knowledge_security_label_grants AS denied
          JOIN request_principals AS principal
            ON principal.principal_type = denied.principal_type
           AND principal.principal_id = denied.principal_id
          WHERE denied.security_label_id = label.security_label_id
            AND denied.authz_revision = label.authz_revision
            AND denied.effect = 'deny'
            AND (denied.valid_from IS NULL OR denied.valid_from <= NOW())
            AND (denied.valid_until IS NULL OR denied.valid_until > NOW())
      )
      AND (%s::text[] IS NULL OR resource.source_app = ANY(%s::text[]))
      AND (
          %s::text[] IS NULL
          OR resource.owner_capability_code = ANY(%s::text[])
      )
      AND (%s::text[] IS NULL OR resource.source_kind = ANY(%s::text[]))
      AND (
          %s::text IS NULL
          OR NOT EXISTS (
              SELECT 1
              FROM knowledge_resource_agent_masks AS any_mask
              WHERE any_mask.knowledge_resource_id =
                    resource.knowledge_resource_id
          )
          OR (
              NOT EXISTS (
                  SELECT 1
                  FROM knowledge_resource_agent_masks AS denied_mask
                  WHERE denied_mask.knowledge_resource_id =
                        resource.knowledge_resource_id
                    AND denied_mask.agent_role = %s
                    AND denied_mask.effect = 'deny'
              )
              AND (
                  NOT EXISTS (
                      SELECT 1
                      FROM knowledge_resource_agent_masks AS any_allow
                      WHERE any_allow.knowledge_resource_id =
                            resource.knowledge_resource_id
                        AND any_allow.effect = 'allow'
                  )
                  OR EXISTS (
                      SELECT 1
                      FROM knowledge_resource_agent_masks AS allowed_mask
                      WHERE allowed_mask.knowledge_resource_id =
                            resource.knowledge_resource_id
                        AND allowed_mask.agent_role = %s
                        AND allowed_mask.effect = 'allow'
                  )
              )
          )
      )
)
"""


def _principals_json(context: RetrievalAccessContext) -> str:
    return json.dumps(
        [
            {"principal_type": item.type, "principal_id": item.id}
            for item in context.principals
        ],
        sort_keys=True,
        separators=(",", ":"),
    )


def _common(
    *,
    context: RetrievalAccessContext,
    scope_type: str,
    scope_id: str,
    source_apps: tuple[str, ...] = (),
    owner_capabilities: tuple[str, ...] = (),
    source_kinds: tuple[str, ...] = (),
) -> tuple[Any, ...]:
    return (
        _principals_json(context),
        context.tenant_id,
        scope_type,
        scope_id,
        list(source_apps) or None,
        list(source_apps) or None,
        list(owner_capabilities) or None,
        list(owner_capabilities) or None,
        list(source_kinds) or None,
        list(source_kinds) or None,
        context.agent_mask.role if context.agent_mask else None,
        context.agent_mask.role if context.agent_mask else None,
        context.agent_mask.role if context.agent_mask else None,
    )


class AuthorizationAwareKnowledgeOperationStore:
    """Candidate operation store; the facade owns final batch authorization."""

    def __init__(self, connection_factory) -> None:
        self._connection_factory = connection_factory

    def fetch_aggregate_rows(
        self,
        *,
        context: RetrievalAccessContext,
        scope_type: str,
        scope_id: str,
        source_apps: tuple[str, ...],
        owner_capabilities: tuple[str, ...],
        source_kinds: tuple[str, ...],
        record_kinds: tuple[str, ...],
        group_by: str,
        measure: str,
        facet_filters: CompiledFacetFilters,
        candidate_limit: int = 2000,
    ) -> list[dict[str, Any]]:
        connection = self._connection_factory()
        try:
            cursor = connection.cursor(cursor_factory=RealDictCursor)
            AuthorizationAwareKnowledgeRetrievalStore._set_local_context(
                cursor,
                context,
            )
            count_sql = (
                "COUNT(DISTINCT record.projection_record_id)"
                if measure == "distinct_count"
                else "COUNT(*)"
            )
            query = (
                _AUTHORIZED_PROJECTIONS_CTE
                + """
                SELECT
                    authorized.knowledge_resource_id,
                    authorized.security_label_id,
                    authorized.authz_revision,
                    facet.facet_type,
                    COALESCE(
                        facet.text_value,
                        facet.number_value::text,
                        facet.bool_value::text,
                        facet.timestamp_value::text,
                        facet.ref_value
                    ) AS group_value,
                    """
                + count_sql
                + """ AS measured_value
                FROM authorized_projections AS authorized
                JOIN knowledge_projection_records AS record
                  ON record.projection_revision_id =
                     authorized.projection_revision_id
                 AND record.knowledge_resource_id =
                     authorized.knowledge_resource_id
                JOIN knowledge_projection_facets AS facet
                  ON facet.projection_record_id =
                     record.projection_record_id
                 AND facet.facet_key = %s
                WHERE (%s::text[] IS NULL OR record.record_kind = ANY(%s::text[]))
                  AND ("""
                + facet_filters.sql
                + """)
                GROUP BY
                    authorized.knowledge_resource_id,
                    authorized.security_label_id,
                    authorized.authz_revision,
                    facet.facet_type,
                    group_value
                ORDER BY measured_value DESC, group_value
                LIMIT %s
                """
            )
            cursor.execute(
                query,
                (
                    *_common(
                        context=context,
                        scope_type=scope_type,
                        scope_id=scope_id,
                        source_apps=source_apps,
                        owner_capabilities=owner_capabilities,
                        source_kinds=source_kinds,
                    ),
                    group_by,
                    list(record_kinds) or None,
                    list(record_kinds) or None,
                    *facet_filters.parameters,
                    candidate_limit + 1,
                ),
            )
            rows = [dict(row) for row in cursor.fetchall()]
            if len(rows) > candidate_limit:
                raise ValueError(
                    "knowledge_query_aggregate_candidate_budget_exceeded"
                )
            connection.commit()
            return rows
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def fetch_citation_rows(
        self,
        *,
        context: RetrievalAccessContext,
        scope_type: str,
        scope_id: str,
        citation_ids: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        by_kind: dict[str, list[str]] = {}
        for citation_id in citation_ids:
            kind, identity = citation_id.split(":", 1)
            by_kind.setdefault(kind, []).append(identity)
        connection = self._connection_factory()
        try:
            cursor = connection.cursor(cursor_factory=RealDictCursor)
            AuthorizationAwareKnowledgeRetrievalStore._set_local_context(
                cursor,
                context,
            )
            common = _common(
                context=context,
                scope_type=scope_type,
                scope_id=scope_id,
            )
            cursor.execute(
                _AUTHORIZED_PROJECTIONS_CTE
                + """
                SELECT
                    'external_doc:' || document.id::text AS citation_id,
                    encode(
                        sha256(convert_to(document.content, 'UTF8')),
                        'hex'
                    ) AS content_hash,
                    document.content,
                    document.metadata,
                    authorized.*
                FROM authorized_projections AS authorized
                JOIN external_docs AS document
                  ON document.projection_revision_id =
                     authorized.projection_revision_id
                 AND document.knowledge_resource_id =
                     authorized.knowledge_resource_id
                 AND document.id::text = ANY(%s::text[])
                UNION ALL
                SELECT
                    'projection_record:' ||
                        record.projection_record_id,
                    record.content_hash,
                    record.search_text,
                    jsonb_build_object(
                        'record_kind', record.record_kind,
                        'record_key', record.record_key,
                        'values', record.values,
                        'citation', record.citation
                    ),
                    authorized.*
                FROM authorized_projections AS authorized
                JOIN knowledge_projection_records AS record
                  ON record.projection_revision_id =
                     authorized.projection_revision_id
                 AND record.knowledge_resource_id =
                     authorized.knowledge_resource_id
                 AND record.projection_record_id = ANY(%s::text[])
                UNION ALL
                SELECT
                    'evidence_unit:' ||
                        evidence.evidence_unit_row_id,
                    evidence.content_hash,
                    '',
                    jsonb_build_object(
                        'unit_key', evidence.unit_key,
                        'unit_kind', evidence.unit_kind,
                        'owner_asset_ref', evidence.owner_asset_ref,
                        'media_type', evidence.media_type,
                        'anchor', evidence.anchor,
                        'derivative_refs', evidence.derivative_refs
                    ),
                    authorized.*
                FROM authorized_projections AS authorized
                JOIN knowledge_evidence_units AS evidence
                  ON evidence.projection_revision_id =
                     authorized.projection_revision_id
                 AND evidence.knowledge_resource_id =
                     authorized.knowledge_resource_id
                 AND evidence.evidence_unit_row_id = ANY(%s::text[])
                UNION ALL
                SELECT
                    'graph_mention:' || mention.mention_id,
                    encode(
                        sha256(convert_to(mention.surface_text, 'UTF8')),
                        'hex'
                    ),
                    mention.surface_text,
                    jsonb_build_object(
                        'mention_type', mention.mention_type,
                        'citation', mention.citation,
                        'evidence_unit_row_id',
                            mention.evidence_unit_row_id,
                        'projection_record_id',
                            mention.projection_record_id
                    ),
                    authorized.*
                FROM authorized_projections AS authorized
                JOIN knowledge_graph_mentions AS mention
                  ON mention.projection_revision_id =
                     authorized.projection_revision_id
                 AND mention.knowledge_resource_id =
                     authorized.knowledge_resource_id
                 AND mention.mention_id = ANY(%s::text[])
                UNION ALL
                SELECT
                    'community_report:' ||
                        report.community_report_id,
                    encode(
                        sha256(convert_to(report.summary, 'UTF8')),
                        'hex'
                    ),
                    report.summary,
                    jsonb_build_object(
                        'findings', report.findings,
                        'supporting_citations',
                            report.supporting_citations,
                        'community_id', community.community_id
                    ),
                    authorized.*
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
                JOIN knowledge_graph_community_reports AS report
                  ON report.community_id = community.community_id
                 AND report.active
                 AND report.authz_revision =
                     authorized.authz_revision
                 AND report.community_report_id = ANY(%s::text[])
                """,
                (
                    *common,
                    by_kind.get("external_doc") or [],
                    by_kind.get("projection_record") or [],
                    by_kind.get("evidence_unit") or [],
                    by_kind.get("graph_mention") or [],
                    by_kind.get("community_report") or [],
                ),
            )
            rows = [dict(row) for row in cursor.fetchall()]
            connection.commit()
            return rows
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def fetch_coverage_rows(
        self,
        *,
        context: RetrievalAccessContext,
        scope_type: str,
        scope_id: str,
        source_apps: tuple[str, ...],
        owner_capabilities: tuple[str, ...],
        source_kinds: tuple[str, ...],
        candidate_limit: int = 5000,
    ) -> list[dict[str, Any]]:
        connection = self._connection_factory()
        try:
            cursor = connection.cursor(cursor_factory=RealDictCursor)
            AuthorizationAwareKnowledgeRetrievalStore._set_local_context(
                cursor,
                context,
            )
            cursor.execute(
                _AUTHORIZED_PROJECTIONS_CTE
                + """
                SELECT DISTINCT
                    authorized.knowledge_resource_id,
                    authorized.security_label_id,
                    authorized.authz_revision,
                    authorized.source_app,
                    authorized.source_kind,
                    authorized.projection_status,
                    channel.channel_id,
                    channel.modality,
                    channel.state AS channel_state,
                    channel.reason AS channel_reason
                FROM authorized_projections AS authorized
                LEFT JOIN knowledge_embedding_channel_receipts AS channel
                  ON channel.projection_revision_id =
                     authorized.projection_revision_id
                ORDER BY
                    authorized.knowledge_resource_id,
                    channel.channel_id
                LIMIT %s
                """,
                (
                    *_common(
                        context=context,
                        scope_type=scope_type,
                        scope_id=scope_id,
                        source_apps=source_apps,
                        owner_capabilities=owner_capabilities,
                        source_kinds=source_kinds,
                    ),
                    candidate_limit + 1,
                ),
            )
            rows = [dict(row) for row in cursor.fetchall()]
            if len(rows) > candidate_limit:
                raise ValueError(
                    "knowledge_query_coverage_candidate_budget_exceeded"
                )
            connection.commit()
            return rows
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


__all__ = ["AuthorizationAwareKnowledgeOperationStore"]
