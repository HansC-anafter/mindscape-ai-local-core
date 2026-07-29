"""Transactional projection revocation leaf for the writer facade."""

from __future__ import annotations

from backend.app.services.authorized_knowledge_index_contracts import (
    AuthorizedIndexRevokeResult,
)
from backend.app.services.knowledge_authorization import (
    KnowledgeResourceIdentity,
    RetrievalAccessContext,
    set_local_knowledge_context,
)
from backend.app.services.knowledge_authorization.identity import (
    knowledge_resource_id,
    security_label_id,
)
from backend.app.services.knowledge_projection.retrievable.repository import (
    ProjectionWriteConflictError,
)


class AuthorizedKnowledgeIndexRevokeMixin:
    def revoke_projection(
        self,
        *,
        access_context: RetrievalAccessContext,
        identity: KnowledgeResourceIdentity,
    ) -> AuthorizedIndexRevokeResult:
        """Make one exact source revision nonqueryable without deleting truth."""

        self._authorization_service.require_project_permission(
            identity=identity,
            access_context=access_context,
        )
        resource_id = knowledge_resource_id(
            owner_capability_code=identity.owner_capability_code,
            source_kind=identity.source_kind,
            source_ref=identity.source_ref,
            owner_scope_type=identity.owner_scope_type,
            owner_scope_id=identity.owner_scope_id,
        )
        label_id = security_label_id(resource_id)
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            set_local_knowledge_context(
                cursor,
                access_context,
                write_scope_type=identity.owner_scope_type,
                write_scope_id=identity.owner_scope_id,
                write_resource_id=resource_id,
                write_security_label_id=label_id,
            )
            cursor.execute(
                """
                SELECT
                    resource.source_revision,
                    resource.active,
                    label.authz_revision,
                    (
                        SELECT projection_revision_id
                        FROM knowledge_resource_projections
                        WHERE knowledge_resource_id =
                              resource.knowledge_resource_id
                          AND active
                        ORDER BY activated_at DESC NULLS LAST
                        LIMIT 1
                    )
                FROM knowledge_resources AS resource
                JOIN knowledge_security_labels AS label
                  ON label.security_label_id =
                     resource.security_label_id
                WHERE resource.knowledge_resource_id = %s
                  AND resource.security_label_id = %s
                  AND resource.tenant_id = %s
                  AND resource.owner_capability_code = %s
                  AND resource.source_kind = %s
                  AND resource.source_ref = %s
                  AND resource.owner_scope_type = %s
                  AND resource.owner_scope_id = %s
                FOR UPDATE OF resource, label
                """,
                (
                    resource_id,
                    label_id,
                    identity.tenant_id,
                    identity.owner_capability_code,
                    identity.source_kind,
                    identity.source_ref,
                    identity.owner_scope_type,
                    identity.owner_scope_id,
                ),
            )
            row = cursor.fetchone()
            if row is None:
                connection.commit()
                return AuthorizedIndexRevokeResult(
                    state="reused",
                    knowledge_resource_id=resource_id,
                    security_label_id=label_id,
                    projection_revision_id=None,
                    authz_revision=None,
                )
            if str(row[0]) != identity.source_revision:
                raise ProjectionWriteConflictError(
                    "knowledge_projection_revoke_source_revision_conflict"
                )
            active_projection_id = (
                str(row[3]) if row[3] is not None else None
            )
            if not bool(row[1]):
                connection.commit()
                return AuthorizedIndexRevokeResult(
                    state="reused",
                    knowledge_resource_id=resource_id,
                    security_label_id=label_id,
                    projection_revision_id=active_projection_id,
                    authz_revision=int(row[2]),
                )
            cursor.execute(
                """
                UPDATE knowledge_resources
                SET active = FALSE,
                    deleted_at = NOW(),
                    updated_at = NOW()
                WHERE knowledge_resource_id = %s
                  AND active
                """,
                (resource_id,),
            )
            cursor.execute(
                """
                UPDATE knowledge_resource_projections
                SET active = FALSE,
                    status = 'revoked',
                    superseded_at = NOW()
                WHERE knowledge_resource_id = %s
                  AND active
                """,
                (resource_id,),
            )
            cursor.execute(
                """
                UPDATE knowledge_embedding_channel_receipts
                SET state = 'revoked',
                    row_count = 0,
                    byte_count = 0,
                    reason = COALESCE(reason, 'source_revoked')
                WHERE projection_revision_id IN (
                    SELECT projection_revision_id
                    FROM knowledge_resource_projections
                    WHERE knowledge_resource_id = %s
                )
                  AND state <> 'revoked'
                """,
                (resource_id,),
            )
            cursor.execute(
                """
                UPDATE knowledge_graph_community_reports AS report
                SET active = FALSE
                FROM knowledge_graph_communities AS community
                WHERE report.community_id = community.community_id
                  AND community.knowledge_resource_id = %s
                """,
                (resource_id,),
            )
            cursor.execute(
                """
                UPDATE external_docs
                SET metadata =
                    COALESCE(metadata, '{}'::jsonb)
                    || '{"active": false, "revoked": true}'::jsonb,
                    updated_at = NOW()
                WHERE knowledge_resource_id = %s
                """,
                (resource_id,),
            )
            self._failpoint("projection_revoked")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return AuthorizedIndexRevokeResult(
            state="revoked",
            knowledge_resource_id=resource_id,
            security_label_id=label_id,
            projection_revision_id=active_projection_id,
            authz_revision=int(row[2]),
        )


__all__ = ["AuthorizedKnowledgeIndexRevokeMixin"]
