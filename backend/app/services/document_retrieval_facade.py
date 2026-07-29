"""Compatibility projection over the canonical authorization-aware reader."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.app.services.knowledge_authorization import (
    PrincipalRef,
    RetrievalAccessContext,
)
from backend.app.services.knowledge_retrieval import (
    AuthorizationAwareKnowledgeRetrievalFacade,
    KnowledgeRetrievalRequest,
)
from backend.app.services.vector_search import VectorSearchService


RRF_K = 60
DOCUMENT_SOURCE_APP = "document_ingestion"


def _source_label(metadata: Dict[str, Any]) -> str:
    return str(
        metadata.get("file_name")
        or metadata.get("document_id")
        or "document"
    )


class DocumentRetrievalFacade:
    """Preserve document response shape without retaining a second reader."""

    def __init__(
        self,
        vector_service: Optional[VectorSearchService] = None,
        connection_factory: Any = None,
        retrieval_facade: (
            AuthorizationAwareKnowledgeRetrievalFacade | None
        ) = None,
    ):
        if retrieval_facade is not None:
            self._retrieval_facade = retrieval_facade
        else:
            self._retrieval_facade = (
                AuthorizationAwareKnowledgeRetrievalFacade(
                    vector_service=vector_service or VectorSearchService(),
                )
            )

    async def search(
        self,
        *,
        query: str,
        user_id: str,
        workspace_id: str,
        top_k: int = 5,
        access_context: RetrievalAccessContext | None = None,
    ) -> List[Dict[str, Any]]:
        if not query.strip() or not user_id or not workspace_id:
            return []
        context = access_context or RetrievalAccessContext.create(
            subject_user_id=user_id,
            tenant_id="local",
            principals=(PrincipalRef("user", user_id),),
        )
        if context.subject_user_id != user_id:
            raise ValueError("document_retrieval_subject_mismatch")
        result = await self._retrieval_facade.search(
            KnowledgeRetrievalRequest(
                query=query,
                access_context=context,
                scope_type="workspace",
                scope_id=workspace_id,
                top_k=max(1, min(top_k, 20)),
                source_apps=(DOCUMENT_SOURCE_APP,),
                owner_capabilities=(DOCUMENT_SOURCE_APP,),
            )
        )
        projected: list[dict[str, Any]] = []
        for hit in result.hits:
            metadata = dict(hit.metadata)
            required = (
                "workspace_id",
                "document_id",
                "revision_id",
                "chunk_id",
                "node_ids",
                "source_locations",
            )
            if any(not metadata.get(key) for key in required):
                continue
            projected.append(
                {
                    "contract_version": "document_retrieval_contract.v1",
                    "citation": {
                        "workspace_id": metadata["workspace_id"],
                        "document_id": metadata["document_id"],
                        "revision_id": metadata["revision_id"],
                        "chunk_id": metadata["chunk_id"],
                        "node_ids": metadata["node_ids"],
                        "source_locations": metadata["source_locations"],
                        "schema_version": metadata.get(
                            "schema_version",
                            "document_schema.v1",
                        ),
                        "index_version": metadata.get("index_version"),
                    },
                    "retrievable_text": hit.content,
                    "score": hit.score,
                    "channels": list(hit.channels),
                    "source_label": _source_label(metadata),
                    "heading_path": metadata.get("heading_path") or [],
                }
            )
        return projected


__all__ = ["DocumentRetrievalFacade", "RRF_K"]
