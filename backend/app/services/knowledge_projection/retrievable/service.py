"""Validate and commit one complete retrievable projection generation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional
from backend.app.services.knowledge_authorization import (
    KnowledgeAclMutation,
    KnowledgeResourceIdentity,
    RetrievalAccessContext,
)
from backend.app.services.vector_search import VectorSearchService

from .write_contracts import ExternalDocumentWrite, RetrievableProjectionWrite


if TYPE_CHECKING:
    from backend.app.services.authorized_knowledge_index_store import (
        AuthorizedIndexWriteResult,
        AuthorizedKnowledgeIndexStore,
    )


class RetrievableKnowledgeProjectionService:
    """Pack-neutral projection facade over the single authorized writer."""

    def __init__(
        self,
        writer: Optional["AuthorizedKnowledgeIndexStore"] = None,
    ) -> None:
        self._writer = writer

    def project_retrievable(
        self,
        *,
        access_context: RetrievalAccessContext,
        identity: KnowledgeResourceIdentity,
        payload: RetrievableProjectionWrite,
        documents: tuple[ExternalDocumentWrite, ...] = (),
        acl_mutation: KnowledgeAclMutation | None = None,
    ) -> "AuthorizedIndexWriteResult":
        if payload.source_instance_id != identity.source_id:
            raise ValueError("knowledge_projection_source_instance_mismatch")
        if payload.source_revision != identity.source_revision:
            raise ValueError("knowledge_projection_source_revision_mismatch")
        writer = self._writer
        if writer is None:
            from backend.app.services.authorized_knowledge_index_store import (
                AuthorizedKnowledgeIndexStore,
            )

            writer = AuthorizedKnowledgeIndexStore(
                VectorSearchService()._get_connection
            )
        return writer.replace_projection(
            access_context=access_context,
            identity=identity,
            payload=payload,
            documents=documents,
            acl_mutation=acl_mutation,
        )

    def revoke_retrievable(
        self,
        *,
        access_context: RetrievalAccessContext,
        identity: KnowledgeResourceIdentity,
    ):
        writer = self._writer
        if writer is None:
            from backend.app.services.authorized_knowledge_index_store import (
                AuthorizedKnowledgeIndexStore,
            )

            writer = AuthorizedKnowledgeIndexStore(
                VectorSearchService()._get_connection
            )
        return writer.revoke_projection(
            access_context=access_context,
            identity=identity,
        )


__all__ = ["RetrievableKnowledgeProjectionService"]
