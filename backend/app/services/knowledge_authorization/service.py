"""Authorization admission facade for the single knowledge writer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts import PrincipalRef, RetrievalAccessContext
from .store import KnowledgeAuthorizationStore
from .write_contracts import (
    KnowledgeAclMutation,
    KnowledgeResourceBinding,
    KnowledgeResourceIdentity,
    KnowledgeGrant,
)


class KnowledgeWriteForbiddenError(PermissionError):
    pass


@dataclass(frozen=True)
class KnowledgeReadAdmission:
    access_context: RetrievalAccessContext
    scope_type: str
    scope_id: str


class KnowledgeAuthorizationService:
    """Validate write authority, then delegate SQL to the ACL store."""

    def __init__(
        self,
        store: KnowledgeAuthorizationStore | None = None,
    ) -> None:
        self.store = store or KnowledgeAuthorizationStore()

    def ensure_project_resource(
        self,
        cursor: Any,
        *,
        identity: KnowledgeResourceIdentity,
        access_context: RetrievalAccessContext,
        acl_mutation: KnowledgeAclMutation | None = None,
        initial_grants: tuple[KnowledgeGrant, ...] = (),
    ) -> KnowledgeResourceBinding:
        self.require_project_permission(
            identity=identity,
            access_context=access_context,
        )
        if acl_mutation is not None and not access_context.has_permission(
            "knowledge.manage_acl",
            scope_type=identity.owner_scope_type,
            scope_id=identity.owner_scope_id,
        ):
            raise KnowledgeWriteForbiddenError(
                "knowledge_manage_acl_permission_required"
            )
        return self.store.ensure_resource(
            cursor,
            identity=identity,
            access_context=access_context,
            acl_mutation=acl_mutation,
            initial_grants=initial_grants,
        )

    @staticmethod
    def require_project_permission(
        *,
        identity: KnowledgeResourceIdentity,
        access_context: RetrievalAccessContext,
    ) -> None:
        if not access_context.has_permission(
            "knowledge.project",
            scope_type=identity.owner_scope_type,
            scope_id=identity.owner_scope_id,
        ):
            raise KnowledgeWriteForbiddenError(
                "knowledge_project_permission_required"
            )

    def admit_read(
        self,
        *,
        access_context: RetrievalAccessContext,
        scope_type: str,
        scope_id: str,
    ) -> KnowledgeReadAdmission:
        """Validate immutable request identity before any candidate query."""

        if scope_type not in {"workspace", "group"} or not str(
            scope_id or ""
        ).strip():
            raise KnowledgeWriteForbiddenError(
                "knowledge_read_scope_invalid"
            )
        if (
            PrincipalRef("user", access_context.subject_user_id)
            not in access_context.principals
        ):
            raise KnowledgeWriteForbiddenError(
                "knowledge_read_subject_principal_required"
            )
        scoped_memberships = {
            (membership.scope_type, membership.scope_id)
            for membership in access_context.memberships
        }
        scoped_permissions = {
            (permission.scope_type, permission.scope_id)
            for permission in access_context.permissions
            if permission.name
            in {"knowledge.read", "knowledge.read_all_scope"}
        }
        # A direct user grant remains queryable without a role membership.
        # Role expansion is accepted only for a server-verified matching scope.
        has_role_principal = any(
            principal.type in {"workspace_role", "group_role"}
            for principal in access_context.principals
        )
        if has_role_principal and (
            scope_type,
            scope_id,
        ) not in scoped_memberships | scoped_permissions:
            raise KnowledgeWriteForbiddenError(
                "knowledge_read_role_scope_unverified"
            )
        return KnowledgeReadAdmission(
            access_context=access_context,
            scope_type=scope_type,
            scope_id=scope_id,
        )

    def ensure_trusted_document_resource(
        self,
        cursor: Any,
        *,
        identity: KnowledgeResourceIdentity,
        access_context: RetrievalAccessContext,
    ) -> KnowledgeResourceBinding:
        """Admit the existing host document compiler, never a pack caller."""

        if (
            identity.owner_capability_code != "document_ingestion"
            or identity.source_app != "document_ingestion"
            or identity.source_kind != "document"
            or identity.owner_scope_type != "workspace"
            or access_context.principal_keys
            != (f"user:{access_context.subject_user_id}",)
        ):
            raise KnowledgeWriteForbiddenError(
                "knowledge_trusted_document_ingest_boundary_violation"
            )
        return self.store.ensure_resource(
            cursor,
            identity=identity,
            access_context=access_context,
        )


__all__ = [
    "KnowledgeReadAdmission",
    "KnowledgeAuthorizationService",
    "KnowledgeWriteForbiddenError",
]
