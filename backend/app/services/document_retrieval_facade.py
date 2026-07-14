"""Workspace-prefiltered hybrid retrieval facade for canonical document chunks."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from psycopg2.extras import RealDictCursor

from backend.app.services.document_chunk_index_store import (
    DOCUMENT_SOURCE_APP,
    fit_external_docs_embedding,
)
from backend.app.services.vector_search import VectorSearchService


RRF_K = 60


def _source_label(metadata: Dict[str, Any]) -> str:
    return str(metadata.get("file_name") or metadata.get("document_id") or "document")


def _build_hit(row: Dict[str, Any], channels: List[str], score: float) -> Dict[str, Any] | None:
    metadata = row.get("metadata") or {}
    required = (
        "workspace_id",
        "document_id",
        "revision_id",
        "chunk_id",
        "node_ids",
        "source_locations",
    )
    if any(not metadata.get(key) for key in required):
        return None
    return {
        "contract_version": "document_retrieval_contract.v1",
        "citation": {
            "workspace_id": metadata["workspace_id"],
            "document_id": metadata["document_id"],
            "revision_id": metadata["revision_id"],
            "chunk_id": metadata["chunk_id"],
            "node_ids": metadata["node_ids"],
            "source_locations": metadata["source_locations"],
            "schema_version": metadata.get("schema_version", "document_schema.v1"),
            "index_version": metadata.get("index_version"),
        },
        "retrievable_text": str(row.get("content") or ""),
        "score": max(0.0, score),
        "channels": channels,
        "source_label": _source_label(metadata),
        "heading_path": metadata.get("heading_path") or [],
    }


class DocumentRetrievalFacade:
    """Run keyword and vector candidates over the same prefiltered corpus."""

    def __init__(
        self,
        vector_service: Optional[VectorSearchService] = None,
        connection_factory: Any = None,
    ):
        self._vector_service = vector_service or VectorSearchService()
        self._connection_factory = connection_factory or self._vector_service._get_connection

    async def search(
        self,
        *,
        query: str,
        user_id: str,
        workspace_id: str,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        if not query.strip() or not user_id or not workspace_id:
            return []
        bounded_top_k = max(1, min(top_k, 20))
        candidate_limit = bounded_top_k * 3
        try:
            embedding, model_name = (
                await self._vector_service._generate_embedding_with_model(
                    query, is_query=True
                )
            )
        except Exception:
            embedding, model_name = None, None
        fitted_embedding = fit_external_docs_embedding(embedding) if embedding else None
        metadata_filter = json.dumps({"workspace_id": workspace_id, "active": True})

        connection = self._connection_factory()
        try:
            cursor = connection.cursor(cursor_factory=RealDictCursor)
            vector_rows: List[Dict[str, Any]] = []
            if fitted_embedding and model_name:
                cursor.execute(
                    """
                    SELECT *, 1 - (embedding <=> %s::vector) AS vector_score
                    FROM external_docs
                    WHERE user_id = %s
                      AND source_app = %s
                      AND metadata @> %s::jsonb
                      AND metadata->>'embedding_model' = %s
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (
                        str(fitted_embedding),
                        user_id,
                        DOCUMENT_SOURCE_APP,
                        metadata_filter,
                        model_name,
                        str(fitted_embedding),
                        candidate_limit,
                    ),
                )
                vector_rows = [dict(row) for row in cursor.fetchall()]

            cursor.execute(
                """
                SELECT *, ts_rank_cd(
                    to_tsvector('simple', COALESCE(content, '')),
                    websearch_to_tsquery('simple', %s)
                ) AS keyword_score
                FROM external_docs
                WHERE user_id = %s
                  AND source_app = %s
                  AND metadata @> %s::jsonb
                  AND to_tsvector('simple', COALESCE(content, ''))
                      @@ websearch_to_tsquery('simple', %s)
                ORDER BY keyword_score DESC
                LIMIT %s
                """,
                (
                    query,
                    user_id,
                    DOCUMENT_SOURCE_APP,
                    metadata_filter,
                    query,
                    candidate_limit,
                ),
            )
            keyword_rows = [dict(row) for row in cursor.fetchall()]
        finally:
            connection.close()

        ranked: Dict[str, Dict[str, Any]] = {}
        for channel, rows in (("text_vector", vector_rows), ("keyword", keyword_rows)):
            for rank, row in enumerate(rows, start=1):
                identity = str(row.get("id") or row.get("source_id"))
                entry = ranked.setdefault(identity, {"row": row, "score": 0.0, "channels": []})
                entry["score"] += 1.0 / (RRF_K + rank)
                if channel not in entry["channels"]:
                    entry["channels"].append(channel)

        hits = []
        for entry in sorted(ranked.values(), key=lambda item: item["score"], reverse=True):
            hit = _build_hit(entry["row"], entry["channels"], entry["score"])
            if hit:
                hits.append(hit)
            if len(hits) >= bounded_top_k:
                break
        return hits


__all__ = ["DocumentRetrievalFacade", "RRF_K"]
