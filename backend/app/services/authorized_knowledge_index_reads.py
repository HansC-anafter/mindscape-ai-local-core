"""Read-only compatibility lookup leaf for the authorized writer facade."""

from __future__ import annotations

import json

from backend.app.services.authorized_knowledge_index_contracts import (
    AuthorizedIndexWriteResult,
)
from backend.app.services.knowledge_authorization import (
    KnowledgePermission,
    PrincipalRef,
    RetrievalAccessContext,
    set_local_knowledge_context,
)


DOCUMENT_SOURCE_APP = "document_ingestion"


class AuthorizedKnowledgeIndexReadMixin:
    def find_active_document_revision(
        self,
        *,
        user_id: str,
        workspace_id: str,
        document_id: str,
        checksum: str,
        pipeline_version: str,
    ) -> AuthorizedIndexWriteResult | None:
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            set_local_knowledge_context(
                cursor,
                RetrievalAccessContext.create(
                    subject_user_id=user_id,
                    tenant_id="local",
                    principals=(PrincipalRef("user", user_id),),
                    permissions=(
                        KnowledgePermission(
                            "knowledge.read",
                            "workspace",
                            workspace_id,
                        ),
                    ),
                ),
            )
            cursor.execute(
                """
                SELECT
                    projection.source_revision,
                    document.metadata->>'embedding_model',
                    COUNT(*),
                    resource.knowledge_resource_id,
                    resource.security_label_id,
                    projection.projection_revision_id,
                    label.authz_revision
                FROM knowledge_resources AS resource
                JOIN knowledge_security_labels AS label
                  ON label.security_label_id = resource.security_label_id
                JOIN knowledge_security_label_grants AS grant_row
                  ON grant_row.security_label_id = resource.security_label_id
                 AND grant_row.authz_revision = label.authz_revision
                 AND grant_row.principal_type = 'user'
                 AND grant_row.principal_id = %s
                 AND grant_row.effect = 'allow'
                 AND (
                    grant_row.valid_from IS NULL
                    OR grant_row.valid_from <= NOW()
                 )
                 AND (
                    grant_row.valid_until IS NULL
                    OR grant_row.valid_until > NOW()
                 )
                JOIN knowledge_resource_projections AS projection
                  ON projection.knowledge_resource_id =
                     resource.knowledge_resource_id
                 AND projection.active
                JOIN external_docs AS document
                  ON document.projection_revision_id =
                     projection.projection_revision_id
                 AND document.knowledge_resource_id =
                     resource.knowledge_resource_id
                 AND document.security_label_id = resource.security_label_id
                WHERE resource.owner_capability_code = %s
                  AND resource.source_kind = 'document'
                  AND resource.source_ref = %s
                  AND resource.owner_scope_type = 'workspace'
                  AND resource.owner_scope_id = %s
                  AND resource.active
                  AND document.metadata @> %s::jsonb
                  AND NOT EXISTS (
                      SELECT 1
                      FROM knowledge_security_label_grants AS denied
                      WHERE denied.security_label_id =
                            resource.security_label_id
                        AND denied.authz_revision = label.authz_revision
                        AND denied.principal_type = 'user'
                        AND denied.principal_id = %s
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
                GROUP BY
                    projection.source_revision,
                    document.metadata->>'embedding_model',
                    resource.knowledge_resource_id,
                    resource.security_label_id,
                    projection.projection_revision_id,
                    label.authz_revision
                LIMIT 1
                """,
                (
                    user_id,
                    DOCUMENT_SOURCE_APP,
                    f"document:{document_id}",
                    workspace_id,
                    json.dumps(
                        {
                            "checksum": checksum,
                            "pipeline_version": pipeline_version,
                            "active": True,
                        }
                    ),
                    user_id,
                ),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return AuthorizedIndexWriteResult(
                state="reused",
                indexed_chunks=int(row[2]),
                revision_id=str(row[0]),
                embedding_model=str(row[1]) if row[1] else None,
                knowledge_resource_id=str(row[3]),
                security_label_id=str(row[4]),
                projection_revision_id=str(row[5]),
                authz_revision=int(row[6]),
            )
        finally:
            connection.close()


__all__ = ["AuthorizedKnowledgeIndexReadMixin", "DOCUMENT_SOURCE_APP"]
