"""Compatibility facade for the canonical authorization-aware index writer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from backend.app.services.authorized_knowledge_index_store import (
    AuthorizedKnowledgeIndexStore,
    DOCUMENT_SOURCE_APP,
)
from backend.app.services.knowledge_projection.retrievable.text_compatibility import (
    EXTERNAL_DOCS_VECTOR_DIMENSION,
    fit_external_docs_embedding,
)


@dataclass(frozen=True)
class DocumentIndexWriteResult:
    state: str
    indexed_chunks: int
    revision_id: str
    embedding_model: Optional[str] = None
    knowledge_resource_id: Optional[str] = None
    security_label_id: Optional[str] = None
    projection_revision_id: Optional[str] = None
    authz_revision: Optional[int] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state,
            "indexed_chunks": self.indexed_chunks,
            "revision_id": self.revision_id,
            "embedding_model": self.embedding_model,
            "knowledge_resource_id": self.knowledge_resource_id,
            "security_label_id": self.security_label_id,
            "projection_revision_id": self.projection_revision_id,
            "authz_revision": self.authz_revision,
        }


class DocumentChunkIndexStore:
    """Thin legacy seam; all reads/writes delegate to the canonical store."""

    def __init__(self, connection_factory, *, authorized_store=None):
        self._authorized_store = authorized_store or AuthorizedKnowledgeIndexStore(
            connection_factory
        )

    def find_active_revision(
        self,
        *,
        user_id: str,
        workspace_id: str,
        document_id: str,
        checksum: str,
        pipeline_version: str,
    ) -> Optional[DocumentIndexWriteResult]:
        result = self._authorized_store.find_active_document_revision(
            user_id=user_id,
            workspace_id=workspace_id,
            document_id=document_id,
            checksum=checksum,
            pipeline_version=pipeline_version,
        )
        return self._adapt(result) if result else None

    def replace_active_revision(
        self,
        *,
        user_id: str,
        workspace_id: str,
        document_id: str,
        revision_id: str,
        records: List[Dict[str, Any]],
    ) -> DocumentIndexWriteResult:
        result = self._authorized_store.replace_trusted_document_revision(
            user_id=user_id,
            workspace_id=workspace_id,
            document_id=document_id,
            revision_id=revision_id,
            records=records,
        )
        return self._adapt(result)

    @staticmethod
    def _adapt(result) -> DocumentIndexWriteResult:
        return DocumentIndexWriteResult(
            state=result.state,
            indexed_chunks=result.indexed_chunks,
            revision_id=result.revision_id,
            embedding_model=result.embedding_model,
            knowledge_resource_id=result.knowledge_resource_id,
            security_label_id=result.security_label_id,
            projection_revision_id=result.projection_revision_id,
            authz_revision=result.authz_revision,
        )


__all__ = [
    "DOCUMENT_SOURCE_APP",
    "DocumentChunkIndexStore",
    "DocumentIndexWriteResult",
    "EXTERNAL_DOCS_VECTOR_DIMENSION",
    "fit_external_docs_embedding",
]
