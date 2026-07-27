"""Authorized citation hydration inside a caller-owned candidate transaction."""

from __future__ import annotations

import json
import re
from typing import Any, Iterable

from backend.app.services.knowledge_authorization import RetrievalAccessContext

from .contracts import CitationLookup


_SEARCH_TOKEN = re.compile(r"[\w.-]+", re.UNICODE)


_AUTHORIZED_SEED_CTE = """
WITH request_principals AS (
    SELECT principal_type, principal_id
    FROM jsonb_to_recordset(%s::jsonb)
         AS principal(principal_type text, principal_id text)
),
authorized_projections AS (
    SELECT
        projection.projection_revision_id,
        projection.knowledge_resource_id,
        resource.security_label_id,
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


def hydrate_authorized_query_seed(
    cursor: Any,
    *,
    context: RetrievalAccessContext,
    scope_type: str,
    scope_id: str,
    citations: Iterable[CitationLookup],
) -> tuple[str, tuple[tuple[str, int], ...]]:
    """Return a bounded text derivative and exact seed auth bindings."""

    expected = {
        citation.citation_id: citation.content_hash
        for citation in citations
    }
    if not expected:
        return "", ()
    by_kind: dict[str, list[str]] = {}
    for citation_id in expected:
        kind, identity = citation_id.split(":", 1)
        by_kind.setdefault(kind, []).append(identity)
    agent_role = context.agent_mask.role if context.agent_mask else None
    cursor.execute(
        _AUTHORIZED_SEED_CTE
        + """
        SELECT
            'external_doc:' || document.id::text AS citation_id,
            encode(
                sha256(convert_to(document.content, 'UTF8')),
                'hex'
            ) AS content_hash,
            document.content,
            authorized.knowledge_resource_id,
            authorized.authz_revision
        FROM authorized_projections AS authorized
        JOIN external_docs AS document
          ON document.projection_revision_id =
             authorized.projection_revision_id
         AND document.knowledge_resource_id =
             authorized.knowledge_resource_id
         AND document.id::text = ANY(%s::text[])
        UNION ALL
        SELECT
            'projection_record:' || record.projection_record_id,
            record.content_hash,
            record.search_text,
            authorized.knowledge_resource_id,
            authorized.authz_revision
        FROM authorized_projections AS authorized
        JOIN knowledge_projection_records AS record
          ON record.projection_revision_id =
             authorized.projection_revision_id
         AND record.knowledge_resource_id =
             authorized.knowledge_resource_id
         AND record.projection_record_id = ANY(%s::text[])
        UNION ALL
        SELECT
            'evidence_unit:' || evidence.evidence_unit_row_id,
            evidence.content_hash,
            COALESCE(document.content, ''),
            authorized.knowledge_resource_id,
            authorized.authz_revision
        FROM authorized_projections AS authorized
        JOIN knowledge_evidence_units AS evidence
          ON evidence.projection_revision_id =
             authorized.projection_revision_id
         AND evidence.knowledge_resource_id =
             authorized.knowledge_resource_id
         AND evidence.evidence_unit_row_id = ANY(%s::text[])
        LEFT JOIN external_docs AS document
          ON document.id = evidence.external_doc_id
         AND document.projection_revision_id =
             authorized.projection_revision_id
        UNION ALL
        SELECT
            'graph_mention:' || mention.mention_id,
            encode(
                sha256(convert_to(mention.surface_text, 'UTF8')),
                'hex'
            ),
            mention.surface_text,
            authorized.knowledge_resource_id,
            authorized.authz_revision
        FROM authorized_projections AS authorized
        JOIN knowledge_graph_mentions AS mention
          ON mention.projection_revision_id =
             authorized.projection_revision_id
         AND mention.knowledge_resource_id =
             authorized.knowledge_resource_id
         AND mention.mention_id = ANY(%s::text[])
        UNION ALL
        SELECT
            'community_report:' || report.community_report_id,
            encode(
                sha256(convert_to(report.summary, 'UTF8')),
                'hex'
            ),
            report.summary,
            authorized.knowledge_resource_id,
            authorized.authz_revision
        FROM authorized_projections AS authorized
        JOIN knowledge_graph_communities AS community
          ON community.projection_revision_id =
             authorized.projection_revision_id
         AND community.knowledge_resource_id =
             authorized.knowledge_resource_id
         AND community.security_label_id =
             authorized.security_label_id
         AND community.authz_revision = authorized.authz_revision
        JOIN knowledge_graph_community_reports AS report
          ON report.community_id = community.community_id
         AND report.active
         AND report.authz_revision = authorized.authz_revision
         AND report.community_report_id = ANY(%s::text[])
        """,
        (
            _principals_json(context),
            context.tenant_id,
            scope_type,
            scope_id,
            agent_role,
            agent_role,
            agent_role,
            by_kind.get("external_doc") or [],
            by_kind.get("projection_record") or [],
            by_kind.get("evidence_unit") or [],
            by_kind.get("graph_mention") or [],
            by_kind.get("community_report") or [],
        ),
    )
    rows = [dict(row) for row in cursor.fetchall()]
    exact = {
        str(row["citation_id"]): row
        for row in rows
        if expected.get(str(row["citation_id"]))
        == str(row["content_hash"])
    }
    if set(exact) != set(expected):
        raise ValueError(
            "knowledge_query_evidence_ref_unavailable_or_stale"
        )
    parts = [
        str(exact[citation_id].get("content") or "").strip()
        for citation_id in expected
    ]
    effective_query = "\n".join(part for part in parts if part)[:8000]
    if not effective_query:
        raise ValueError(
            "knowledge_query_evidence_ref_text_derivative_not_admitted"
        )
    bindings = tuple(
        sorted(
            {
                (
                    str(row["knowledge_resource_id"]),
                    int(row["authz_revision"]),
                )
                for row in exact.values()
            }
        )
    )
    return effective_query, bindings


def websearch_query_from_seed(
    *,
    explicit_query: str,
    seed_query: str,
) -> str:
    """Build a bounded OR seed without accepting raw query syntax."""

    parts = []
    if explicit_query.strip():
        parts.append(explicit_query.strip())
    tokens: list[str] = []
    for token in _SEARCH_TOKEN.findall(seed_query):
        normalized = token.strip("._-")
        if len(normalized) < 2 or normalized in tokens:
            continue
        tokens.append(normalized)
        if len(tokens) >= 64:
            break
    parts.extend(tokens)
    return " OR ".join(parts)[:8000]


__all__ = [
    "hydrate_authorized_query_seed",
    "websearch_query_from_seed",
]
