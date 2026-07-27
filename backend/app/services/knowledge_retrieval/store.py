"""Exact ACL-prefiltered candidate SQL and one bounded final authorization check."""

from __future__ import annotations

import json
from typing import Any, Iterable, Mapping, Optional

from psycopg2.extras import RealDictCursor

from backend.app.services.knowledge_authorization import (
    RetrievalAccessContext,
    set_local_knowledge_context,
)
from backend.app.services.knowledge_authorization.context_sql import (
    principals_json,
)

from .contracts import CitationLookup
from .query_seed import (
    hydrate_authorized_query_seed,
    websearch_query_from_seed,
)


_AUTHORIZED_CTE = """
WITH request_principals AS (
    SELECT principal_type, principal_id
    FROM jsonb_to_recordset(%s::jsonb)
         AS principal(principal_type text, principal_id text)
),
authorized_rows AS (
    SELECT
        document.id,
        document.source_app,
        document.source_id,
        document.doc_type,
        document.title,
        document.content,
        document.embedding,
        document.metadata,
        document.knowledge_resource_id,
        document.security_label_id,
        document.projection_revision_id,
        resource.owner_capability_code,
        resource.source_kind,
        resource.source_ref,
        label.authz_revision
    FROM external_docs AS document
    JOIN knowledge_resources AS resource
      ON resource.knowledge_resource_id = document.knowledge_resource_id
     AND resource.security_label_id = document.security_label_id
     AND resource.active
     AND resource.deleted_at IS NULL
    JOIN knowledge_security_labels AS label
      ON label.security_label_id = resource.security_label_id
    LEFT JOIN knowledge_resource_projections AS projection
      ON projection.projection_revision_id = document.projection_revision_id
     AND projection.knowledge_resource_id = resource.knowledge_resource_id
    WHERE resource.tenant_id = %s
      AND resource.owner_scope_type = %s
      AND resource.owner_scope_id = %s
      AND (
          (
              document.projection_revision_id IS NULL
              AND LOWER(COALESCE(document.metadata->>'active', 'true')) = 'true'
          )
          OR (
              document.projection_revision_id IS NOT NULL
              AND projection.active
              AND projection.status IN (
                  'active', 'degraded_channels', 'degraded_graph'
              )
          )
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
      AND (%s::text[] IS NULL OR document.source_app = ANY(%s::text[]))
      AND (
          %s::text[] IS NULL
          OR resource.owner_capability_code = ANY(%s::text[])
      )
      AND (
          %s::text IS NULL
          OR (
              %s::text = 'text'
              AND document.projection_revision_id IS NULL
          )
          OR EXISTS (
              SELECT 1
              FROM knowledge_evidence_units AS evidence
              JOIN knowledge_embedding_channel_receipts AS channel
                ON channel.evidence_unit_row_id =
                   evidence.evidence_unit_row_id
               AND channel.projection_revision_id =
                   evidence.projection_revision_id
              WHERE evidence.projection_revision_id =
                    document.projection_revision_id
                AND (
                    evidence.external_doc_id = document.id
                    OR evidence.unit_key =
                       COALESCE(
                           document.metadata->>'chunk_id',
                           document.source_id
                       )
                )
                AND channel.modality = %s
                AND channel.state = 'active'
          )
      )
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
    return principals_json(context)


def _agent_role(context: RetrievalAccessContext) -> Optional[str]:
    return context.agent_mask.role if context.agent_mask else None


class AuthorizationAwareKnowledgeRetrievalStore:
    """Use at most one candidate and one final-check transaction per request."""

    def __init__(self, connection_factory) -> None:
        self._connection_factory = connection_factory

    @staticmethod
    def _set_local_context(
        cursor: Any,
        context: RetrievalAccessContext,
    ) -> None:
        set_local_knowledge_context(cursor, context)

    def fetch_hybrid_candidates(
        self,
        *,
        query: str,
        query_embedding: Optional[list[float]],
        model_name: Optional[str],
        context: RetrievalAccessContext,
        scope_type: str,
        scope_id: str,
        source_apps: tuple[str, ...],
        owner_capabilities: tuple[str, ...],
        modality_filter: Optional[str],
        candidate_limit: int,
        query_evidence_refs: tuple[CitationLookup, ...] = (),
    ) -> tuple[
        list[dict[str, Any]],
        list[dict[str, Any]],
        tuple[tuple[str, int], ...],
    ]:
        connection = self._connection_factory()
        try:
            cursor = connection.cursor(cursor_factory=RealDictCursor)
            self._set_local_context(cursor, context)
            seed_query, seed_bindings = hydrate_authorized_query_seed(
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
            common = (
                _principals_json(context),
                context.tenant_id,
                scope_type,
                scope_id,
                list(source_apps) or None,
                list(source_apps) or None,
                list(owner_capabilities) or None,
                list(owner_capabilities) or None,
                modality_filter,
                modality_filter,
                modality_filter,
                _agent_role(context),
                _agent_role(context),
                _agent_role(context),
            )
            vector_rows: list[dict[str, Any]] = []
            if query_embedding is not None and model_name:
                cursor.execute(
                    _AUTHORIZED_CTE
                    + """
                    SELECT
                        authorized_rows.*,
                        1 - (embedding <=> %s::vector) AS vector_score
                    FROM authorized_rows
                    WHERE embedding IS NOT NULL
                      AND metadata->>'embedding_model' = %s
                    ORDER BY embedding <=> %s::vector, id
                    LIMIT %s
                    """,
                    (
                        *common,
                        str(query_embedding),
                        model_name,
                        str(query_embedding),
                        candidate_limit,
                    ),
                )
                vector_rows = [dict(row) for row in cursor.fetchall()]
            cursor.execute(
                _AUTHORIZED_CTE
                + """
                SELECT
                    authorized_rows.*,
                    ts_rank_cd(
                        to_tsvector('simple', COALESCE(content, '')),
                        websearch_to_tsquery('simple', %s)
                    ) AS keyword_score
                FROM authorized_rows
                WHERE to_tsvector('simple', COALESCE(content, ''))
                      @@ websearch_to_tsquery('simple', %s)
                ORDER BY keyword_score DESC, id
                LIMIT %s
                """,
                (
                    *common,
                    effective_query,
                    effective_query,
                    candidate_limit,
                ),
            )
            keyword_rows = [dict(row) for row in cursor.fetchall()]
            connection.commit()
            return vector_rows, keyword_rows, seed_bindings
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def final_authorize(
        self,
        *,
        context: RetrievalAccessContext,
        scope_type: str,
        scope_id: str,
        expected_bindings: Iterable[tuple[str, int]],
    ) -> dict[str, int]:
        expected = [
            {"resource_id": resource_id, "authz_revision": revision}
            for resource_id, revision in sorted(set(expected_bindings))
        ]
        if not expected:
            return {}
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            self._set_local_context(cursor, context)
            cursor.execute(
                """
                WITH request_principals AS (
                    SELECT principal_type, principal_id
                    FROM jsonb_to_recordset(%s::jsonb)
                         AS principal(
                             principal_type text,
                             principal_id text
                         )
                ),
                expected AS (
                    SELECT resource_id, authz_revision
                    FROM jsonb_to_recordset(%s::jsonb)
                         AS binding(
                             resource_id text,
                             authz_revision bigint
                         )
                )
                SELECT resource.knowledge_resource_id, label.authz_revision
                FROM expected
                JOIN knowledge_resources AS resource
                  ON resource.knowledge_resource_id = expected.resource_id
                 AND resource.active
                 AND resource.deleted_at IS NULL
                 AND resource.tenant_id = %s
                 AND resource.owner_scope_type = %s
                 AND resource.owner_scope_id = %s
                JOIN knowledge_security_labels AS label
                  ON label.security_label_id = resource.security_label_id
                 AND label.authz_revision = expected.authz_revision
                WHERE EXISTS (
                    SELECT 1
                    FROM knowledge_security_label_grants AS allowed
                    JOIN request_principals AS principal
                      ON principal.principal_type =
                         allowed.principal_type
                     AND principal.principal_id = allowed.principal_id
                    WHERE allowed.security_label_id =
                          label.security_label_id
                      AND allowed.authz_revision =
                          label.authz_revision
                      AND allowed.effect = 'allow'
                      AND (
                          allowed.valid_from IS NULL
                          OR allowed.valid_from <= NOW()
                      )
                      AND (
                          allowed.valid_until IS NULL
                          OR allowed.valid_until > NOW()
                      )
                )
                  AND NOT EXISTS (
                    SELECT 1
                    FROM knowledge_security_label_grants AS denied
                    JOIN request_principals AS principal
                      ON principal.principal_type =
                         denied.principal_type
                     AND principal.principal_id = denied.principal_id
                    WHERE denied.security_label_id =
                          label.security_label_id
                      AND denied.authz_revision = label.authz_revision
                      AND denied.effect = 'deny'
                      AND (
                          denied.valid_from IS NULL
                          OR denied.valid_from <= NOW()
                      )
                      AND (
                          denied.valid_until IS NULL
                          OR denied.valid_until > NOW()
                      )
                )
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
                              FROM knowledge_resource_agent_masks
                                   AS denied_mask
                              WHERE denied_mask.knowledge_resource_id =
                                    resource.knowledge_resource_id
                                AND denied_mask.agent_role = %s
                                AND denied_mask.effect = 'deny'
                          )
                          AND (
                              NOT EXISTS (
                                  SELECT 1
                                  FROM knowledge_resource_agent_masks
                                       AS any_allow
                                  WHERE any_allow.knowledge_resource_id =
                                        resource.knowledge_resource_id
                                    AND any_allow.effect = 'allow'
                              )
                              OR EXISTS (
                                  SELECT 1
                                  FROM knowledge_resource_agent_masks
                                       AS allowed_mask
                                  WHERE allowed_mask.knowledge_resource_id =
                                        resource.knowledge_resource_id
                                    AND allowed_mask.agent_role = %s
                                    AND allowed_mask.effect = 'allow'
                              )
                          )
                      )
                  )
                """,
                (
                    _principals_json(context),
                    json.dumps(expected, sort_keys=True, separators=(",", ":")),
                    context.tenant_id,
                    scope_type,
                    scope_id,
                    _agent_role(context),
                    _agent_role(context),
                    _agent_role(context),
                ),
            )
            result = {str(row[0]): int(row[1]) for row in cursor.fetchall()}
            connection.commit()
            return result
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


__all__ = ["AuthorizationAwareKnowledgeRetrievalStore"]
