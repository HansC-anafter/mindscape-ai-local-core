"""Physical embedding-channel stores under the authorized caller transaction."""

from __future__ import annotations

import json
from typing import Any, Protocol

from backend.app.services.knowledge_authorization.write_contracts import (
    KnowledgeResourceBinding,
)

from .write_contracts import ExternalDocumentWrite


class KnowledgeEmbeddingChannelStore(Protocol):
    def replace_generation(
        self,
        cursor: Any,
        *,
        subject_user_id: str,
        source_app: str,
        binding: KnowledgeResourceBinding,
        projection_revision_id: str,
        documents: tuple[ExternalDocumentWrite, ...],
    ) -> int: ...


class ExternalDocsTextChannelStore:
    """The one writer leaf for the existing external_docs text channel."""

    def replace_generation(
        self,
        cursor: Any,
        *,
        subject_user_id: str,
        source_app: str,
        binding: KnowledgeResourceBinding,
        projection_revision_id: str,
        documents: tuple[ExternalDocumentWrite, ...],
    ) -> int:
        cursor.execute(
            "DELETE FROM external_docs WHERE knowledge_resource_id = %s",
            (binding.knowledge_resource_id,),
        )
        if documents:
            cursor.executemany(
                """
                INSERT INTO external_docs (
                    user_id, source_app, source_id, doc_type, title,
                    content, embedding, metadata,
                    knowledge_resource_id, security_label_id,
                    projection_revision_id, created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s::vector, %s::jsonb,
                    %s, %s, %s, NOW(), NOW()
                )
                """,
                [
                    (
                        subject_user_id,
                        source_app,
                        document.source_id,
                        document.doc_type,
                        document.title,
                        document.content,
                        str(list(document.embedding)),
                        json.dumps(
                            document.metadata,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                        binding.knowledge_resource_id,
                        binding.security_label_id,
                        projection_revision_id,
                    )
                    for document in documents
                ],
            )
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM external_docs
            WHERE projection_revision_id = %s
              AND knowledge_resource_id = %s
              AND security_label_id = %s
            """,
            (
                projection_revision_id,
                binding.knowledge_resource_id,
                binding.security_label_id,
            ),
        )
        row = cursor.fetchone()
        return int(row[0]) if row is not None else -1


__all__ = [
    "ExternalDocsTextChannelStore",
    "KnowledgeEmbeddingChannelStore",
]
