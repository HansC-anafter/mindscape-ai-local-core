"""Canonical active-revision projection into the existing external_docs table."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional


DOCUMENT_SOURCE_APP = "document_ingestion"
EXTERNAL_DOCS_VECTOR_DIMENSION = 1536
ConnectionFactory = Callable[[], Any]


def fit_external_docs_embedding(embedding: Iterable[float]) -> List[float]:
    """Zero-pad shorter vectors; cosine distance is preserved by zero padding."""
    values = [float(value) for value in embedding]
    if len(values) > EXTERNAL_DOCS_VECTOR_DIMENSION:
        raise ValueError(
            "document_embedding_dimension_exceeds_external_docs:"
            f"{len(values)}:{EXTERNAL_DOCS_VECTOR_DIMENSION}"
        )
    if not values:
        raise ValueError("document_embedding_is_empty")
    return values + [0.0] * (EXTERNAL_DOCS_VECTOR_DIMENSION - len(values))


@dataclass(frozen=True)
class DocumentIndexWriteResult:
    state: str
    indexed_chunks: int
    revision_id: str
    embedding_model: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state,
            "indexed_chunks": self.indexed_chunks,
            "revision_id": self.revision_id,
            "embedding_model": self.embedding_model,
        }


class DocumentChunkIndexStore:
    """Write only document_ingestion rows through one short transaction."""

    def __init__(self, connection_factory: ConnectionFactory):
        self._connection_factory = connection_factory

    def find_active_revision(
        self,
        *,
        user_id: str,
        workspace_id: str,
        document_id: str,
        checksum: str,
        pipeline_version: str,
    ) -> Optional[DocumentIndexWriteResult]:
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            metadata_filter = json.dumps(
                {
                    "workspace_id": workspace_id,
                    "document_id": document_id,
                    "checksum": checksum,
                    "pipeline_version": pipeline_version,
                    "active": True,
                }
            )
            cursor.execute(
                """
                SELECT
                    metadata->>'revision_id' AS revision_id,
                    metadata->>'embedding_model' AS embedding_model,
                    COUNT(*) AS chunk_count
                FROM external_docs
                WHERE user_id = %s
                  AND source_app = %s
                  AND metadata @> %s::jsonb
                GROUP BY metadata->>'revision_id', metadata->>'embedding_model'
                LIMIT 1
                """,
                (user_id, DOCUMENT_SOURCE_APP, metadata_filter),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return DocumentIndexWriteResult(
                state="reused",
                indexed_chunks=int(row[2]),
                revision_id=str(row[0]),
                embedding_model=str(row[1]) if row[1] else None,
            )
        finally:
            connection.close()

    def replace_active_revision(
        self,
        *,
        user_id: str,
        workspace_id: str,
        document_id: str,
        revision_id: str,
        records: List[Dict[str, Any]],
    ) -> DocumentIndexWriteResult:
        if not records:
            raise ValueError("document_index_requires_complete_records")
        models = {str(record.get("metadata", {}).get("embedding_model") or "") for record in records}
        if len(models) != 1 or "" in models:
            raise ValueError("document_index_requires_one_embedding_model")

        prepared = []
        for record in records:
            metadata = dict(record["metadata"])
            if (
                metadata.get("workspace_id") != workspace_id
                or metadata.get("document_id") != document_id
                or metadata.get("revision_id") != revision_id
                or metadata.get("active") is not True
            ):
                raise ValueError("document_index_record_identity_mismatch")
            prepared.append(
                (
                    user_id,
                    DOCUMENT_SOURCE_APP,
                    str(record["source_id"]),
                    "document_chunk",
                    str(record["title"]),
                    str(record["content"]),
                    str(fit_external_docs_embedding(record["embedding"])),
                    json.dumps(metadata),
                )
            )

        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            identity_filter = json.dumps(
                {"workspace_id": workspace_id, "document_id": document_id}
            )
            cursor.execute(
                """
                DELETE FROM external_docs
                WHERE user_id = %s
                  AND source_app = %s
                  AND metadata @> %s::jsonb
                """,
                (user_id, DOCUMENT_SOURCE_APP, identity_filter),
            )
            cursor.executemany(
                """
                INSERT INTO external_docs (
                    user_id, source_app, source_id, doc_type, title,
                    content, embedding, metadata, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s::vector, %s::jsonb, NOW(), NOW())
                """,
                prepared,
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

        return DocumentIndexWriteResult(
            state="indexed",
            indexed_chunks=len(prepared),
            revision_id=revision_id,
            embedding_model=next(iter(models)),
        )


__all__ = [
    "DOCUMENT_SOURCE_APP",
    "DocumentChunkIndexStore",
    "DocumentIndexWriteResult",
    "EXTERNAL_DOCS_VECTOR_DIMENSION",
    "fit_external_docs_embedding",
]
