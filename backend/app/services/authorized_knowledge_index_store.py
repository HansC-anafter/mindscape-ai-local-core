"""Facade for the single ACL-bound knowledge projection transaction path."""

from __future__ import annotations

from typing import Any, Callable

from backend.app.services.authorized_knowledge_index_contracts import (
    AuthorizedIndexRevokeResult,
    AuthorizedIndexWriteResult,
)
from backend.app.services.authorized_knowledge_index_generation import (
    AuthorizedKnowledgeIndexGenerationMixin,
)
from backend.app.services.authorized_knowledge_index_reads import (
    AuthorizedKnowledgeIndexReadMixin,
    DOCUMENT_SOURCE_APP,
)
from backend.app.services.authorized_knowledge_index_revoke import (
    AuthorizedKnowledgeIndexRevokeMixin,
)
from backend.app.services.knowledge_authorization import (
    KnowledgeAclMutation,
    KnowledgeAuthorizationService,
    KnowledgePermission,
    KnowledgeResourceIdentity,
    PrincipalRef,
    RetrievalAccessContext,
)
from backend.app.services.knowledge_projection.retrievable.channel_store import (
    ExternalDocsTextChannelStore,
    KnowledgeEmbeddingChannelStore,
)
from backend.app.services.knowledge_projection.retrievable.document_adapter import (
    compile_document_projection,
)
from backend.app.services.knowledge_projection.retrievable.repository import (
    RetrievableKnowledgeProjectionRepository,
)
from backend.app.services.knowledge_projection.retrievable.write_contracts import (
    ExternalDocumentWrite,
    RetrievableProjectionWrite,
)


ConnectionFactory = Callable[[], Any]
Failpoint = Callable[[str], None]


class AuthorizedKnowledgeIndexStore(
    AuthorizedKnowledgeIndexReadMixin,
    AuthorizedKnowledgeIndexRevokeMixin,
    AuthorizedKnowledgeIndexGenerationMixin,
):
    """Own the only public ACL/resource/projection/external_docs write seam."""

    def __init__(
        self,
        connection_factory: ConnectionFactory,
        *,
        authorization_service: KnowledgeAuthorizationService | None = None,
        projection_repository: (
            RetrievableKnowledgeProjectionRepository | None
        ) = None,
        text_channel_store: KnowledgeEmbeddingChannelStore | None = None,
        failpoint: Failpoint | None = None,
    ) -> None:
        self._connection_factory = connection_factory
        self._authorization_service = (
            authorization_service or KnowledgeAuthorizationService()
        )
        self._projection_repository = (
            projection_repository or RetrievableKnowledgeProjectionRepository()
        )
        self._text_channel_store = (
            text_channel_store or ExternalDocsTextChannelStore()
        )
        self._failpoint = failpoint or (lambda _step: None)

    def replace_trusted_document_revision(
        self,
        *,
        user_id: str,
        workspace_id: str,
        document_id: str,
        revision_id: str,
        records: list[dict[str, Any]],
    ) -> AuthorizedIndexWriteResult:
        payload, documents = compile_document_projection(
            workspace_id=workspace_id,
            document_id=document_id,
            revision_id=revision_id,
            records=records,
        )
        context = RetrievalAccessContext.create(
            subject_user_id=user_id,
            tenant_id="local",
            principals=(PrincipalRef("user", user_id),),
            permissions=(
                KnowledgePermission(
                    "knowledge.project",
                    "workspace",
                    workspace_id,
                ),
            ),
        )
        identity = KnowledgeResourceIdentity(
            tenant_id="local",
            owner_capability_code=DOCUMENT_SOURCE_APP,
            source_kind="document",
            source_app=DOCUMENT_SOURCE_APP,
            source_id=document_id,
            source_ref=f"document:{document_id}",
            source_revision=revision_id,
            owner_scope_type="workspace",
            owner_scope_id=workspace_id,
            classification="private",
        )
        return self._replace_generation(
            access_context=context,
            identity=identity,
            payload=payload,
            documents=documents,
            trusted_document=True,
        )

    def replace_projection(
        self,
        *,
        access_context: RetrievalAccessContext,
        identity: KnowledgeResourceIdentity,
        payload: RetrievableProjectionWrite,
        documents: tuple[ExternalDocumentWrite, ...],
        acl_mutation: KnowledgeAclMutation | None = None,
    ) -> AuthorizedIndexWriteResult:
        """Commit one pack-neutral generation after server-verified admission."""

        return self._replace_generation(
            access_context=access_context,
            identity=identity,
            payload=payload,
            documents=documents,
            acl_mutation=acl_mutation,
            trusted_document=False,
        )


__all__ = [
    "AuthorizedIndexRevokeResult",
    "AuthorizedIndexWriteResult",
    "AuthorizedKnowledgeIndexStore",
    "DOCUMENT_SOURCE_APP",
]
