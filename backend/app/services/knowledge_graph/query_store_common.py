"""Shared authorization-first SQL preface for graph query leaves."""

from __future__ import annotations

import json
from typing import Any

from backend.app.services.knowledge_authorization import RetrievalAccessContext


AUTHORIZED_PROJECTIONS_CTE = """
WITH request_principals AS (
    SELECT principal_type, principal_id
    FROM jsonb_to_recordset(%s::jsonb)
         AS principal(principal_type text, principal_id text)
),
authorized_projections AS (
    SELECT
        projection.projection_revision_id,
        projection.knowledge_resource_id,
        projection.visibility_partition_hash,
        resource.security_label_id,
        resource.source_app,
        resource.source_id,
        resource.source_ref,
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
      AND (
          %s::text IS NULL
          OR EXISTS (
              SELECT 1
              FROM knowledge_embedding_channel_receipts AS channel
              WHERE channel.projection_revision_id =
                    projection.projection_revision_id
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


def common_parameters(
    *,
    context: RetrievalAccessContext,
    scope_type: str,
    scope_id: str,
    source_apps: tuple[str, ...],
    owner_capabilities: tuple[str, ...],
    modality_filter: str | None,
) -> tuple[Any, ...]:
    principals_json = json.dumps(
        [
            {"principal_type": item.type, "principal_id": item.id}
            for item in context.principals
        ],
        sort_keys=True,
        separators=(",", ":"),
    )
    agent_role = context.agent_mask.role if context.agent_mask else None
    return (
        principals_json,
        context.tenant_id,
        scope_type,
        scope_id,
        list(source_apps) or None,
        list(source_apps) or None,
        list(owner_capabilities) or None,
        list(owner_capabilities) or None,
        modality_filter,
        modality_filter,
        agent_role,
        agent_role,
        agent_role,
    )


__all__ = ["AUTHORIZED_PROJECTIONS_CTE", "common_parameters"]
