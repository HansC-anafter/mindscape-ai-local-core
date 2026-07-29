"""Authorization-first SQL preface for hybrid knowledge candidates."""

AUTHORIZED_CANDIDATES_CTE = """
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
      AND (%s::text[] IS NULL OR document.source_id = ANY(%s::text[]))
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


__all__ = ["AUTHORIZED_CANDIDATES_CTE"]
