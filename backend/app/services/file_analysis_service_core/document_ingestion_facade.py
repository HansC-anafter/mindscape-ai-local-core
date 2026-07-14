"""Local Core host seam for the stateless document_ingestion compiler."""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from backend.app.services.document_chunk_index_store import DocumentChunkIndexStore
from backend.app.services.file_analysis_service_core.document_ingestion_artifact_store import (
    DocumentIngestionArtifactStore,
)
from backend.app.services.vector_search import VectorSearchService


logger = logging.getLogger(__name__)

SUPPORTED_DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".pptx"}
SUPPORTED_DOCUMENT_MEDIA_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}
MAX_INDEXED_CHUNKS = 128
EVENT_TEXT_PREVIEW_CHARACTERS = 4000


def _default_tool_executor() -> Any:
    from backend.app.shared.tool_executor import ToolExecutor

    return ToolExecutor()


def _media_type(file_name: str, supplied: Optional[str]) -> Optional[str]:
    if supplied:
        return supplied
    return {
        ".pdf": "application/pdf",
        ".docx": (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        ".pptx": (
            "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        ),
    }.get(Path(file_name).suffix.lower())


@dataclass(frozen=True)
class DocumentIngestionHostResult:
    summary: Dict[str, Any]
    file_info_override: Optional[Dict[str, Any]] = None


class DocumentIngestionHostFacade:
    """Compile, persist, then atomically project one bounded document revision."""

    def __init__(
        self,
        *,
        tool_executor: Any = None,
        artifact_store: Optional[DocumentIngestionArtifactStore] = None,
        vector_service: Optional[VectorSearchService] = None,
        index_store: Optional[DocumentChunkIndexStore] = None,
    ):
        self._tool_executor = tool_executor or _default_tool_executor()
        self._artifact_store = artifact_store or DocumentIngestionArtifactStore()
        self._vector_service = vector_service or VectorSearchService()
        self._index_store = index_store or DocumentChunkIndexStore(
            self._vector_service._get_connection
        )

    @staticmethod
    def supports(file_name: str, file_type: Optional[str] = None) -> bool:
        return (
            Path(file_name).suffix.lower() in SUPPORTED_DOCUMENT_EXTENSIONS
            or str(file_type or "").lower() in SUPPORTED_DOCUMENT_MEDIA_TYPES
        )

    async def compile_and_index(
        self,
        *,
        workspace_id: str,
        user_id: str,
        source_artifact_id: str,
        file_path: str,
        file_name: str,
        file_type: Optional[str],
        file_size: Optional[int],
        checksum: str,
    ) -> Optional[DocumentIngestionHostResult]:
        if not self.supports(file_name, file_type):
            return None
        if not file_path or not checksum or not Path(file_path).is_file():
            return DocumentIngestionHostResult(
                summary={
                    "state": "failed",
                    "index": {"state": "not_attempted", "indexed_chunks": 0},
                    "warnings": ["document_ingestion_source_unavailable"],
                }
            )

        artifact_path = self._artifact_store.path_for(file_path)
        try:
            compilation = await self._tool_executor.execute_tool(
                "document_ingestion.compile_document",
                file_path=file_path,
                workspace_id=workspace_id,
                source_artifact_id=source_artifact_id,
                checksum=checksum,
                schema_storage_key=str(artifact_path),
                media_type=_media_type(file_name, file_type),
                source_storage_key=file_path,
                allow_ocr=False,
            )
        except Exception as exc:
            logger.warning("Document compiler unavailable for %s: %s", file_name, exc)
            return DocumentIngestionHostResult(
                summary={
                    "state": "failed",
                    "index": {"state": "not_attempted", "indexed_chunks": 0},
                    "warnings": ["document_ingestion_compiler_unavailable"],
                }
            )

        schema = compilation.get("schema_artifact") or {}
        manifest = compilation.get("chunk_manifest") or {}
        chunks = manifest.get("chunks") or []
        try:
            pointer = self._artifact_store.write(
                file_path=file_path,
                compilation=compilation,
                file_name=file_name,
                workspace_id=workspace_id,
            )
        except Exception as exc:
            logger.warning("Document artifact write failed for %s: %s", file_name, exc)
            return DocumentIngestionHostResult(
                summary={
                    "state": "failed",
                    "index": {"state": "not_attempted", "indexed_chunks": 0},
                    "warnings": ["document_ingestion_artifact_write_failed"],
                },
                file_info_override={
                    "name": file_name,
                    "size": file_size or Path(file_path).stat().st_size,
                    "type": _media_type(file_name, file_type),
                    "detected_type": "document",
                    "text_content": str(
                        compilation.get("retrievable_preview") or ""
                    )[:EVENT_TEXT_PREVIEW_CHARACTERS],
                    "file_path": file_path,
                },
            )
        warnings = list(compilation.get("warnings") or [])
        index_result: Dict[str, Any] = {
            "state": "not_ready",
            "indexed_chunks": 0,
            "revision_id": schema.get("revision_id"),
            "embedding_model": None,
        }

        retrieval_ready = bool(manifest.get("retrieval_ready"))
        if compilation.get("state") == "ready" and retrieval_ready and chunks:
            if len(chunks) > MAX_INDEXED_CHUNKS:
                index_result["state"] = "limit_exceeded"
                warnings.append("document_index_chunk_limit_exceeded")
            else:
                index_result = await self._index_complete_revision(
                    user_id=user_id,
                    workspace_id=workspace_id,
                    file_name=file_name,
                    media_type=_media_type(file_name, file_type),
                    schema=schema,
                    chunks=chunks,
                )
                if index_result.get("state") == "failed":
                    warnings.append("document_index_projection_failed")

        preview = str(compilation.get("retrievable_preview") or "")[
            :EVENT_TEXT_PREVIEW_CHARACTERS
        ]
        summary = {
            "state": compilation.get("state", "degraded"),
            "document_id": schema.get("document_id"),
            "revision_id": schema.get("revision_id"),
            "checksum": schema.get("checksum"),
            "schema_version": schema.get("schema_version"),
            "pipeline_version": schema.get("pipeline_version"),
            "node_count": len(schema.get("nodes") or []),
            "chunk_count": len(chunks),
            "visual_candidate_count": int(
                compilation.get("visual_candidate_count") or 0
            ),
            "artifact": pointer.as_dict(),
            "index": index_result,
            "warnings": list(dict.fromkeys(warnings)),
            "retrievable_preview": preview,
        }
        file_info = {
            "name": file_name,
            "size": file_size or Path(file_path).stat().st_size,
            "type": _media_type(file_name, file_type),
            "detected_type": "document",
            "text_content": preview,
            "file_path": file_path,
        }
        return DocumentIngestionHostResult(summary=summary, file_info_override=file_info)

    async def _index_complete_revision(
        self,
        *,
        user_id: str,
        workspace_id: str,
        file_name: str,
        media_type: Optional[str],
        schema: Dict[str, Any],
        chunks: list[Dict[str, Any]],
    ) -> Dict[str, Any]:
        document_id = str(schema.get("document_id") or "")
        revision_id = str(schema.get("revision_id") or "")
        checksum = str(schema.get("checksum") or "")
        pipeline_version = str(schema.get("pipeline_version") or "")
        records = []
        embedding_model: Optional[str] = None
        source_dimension: Optional[int] = None
        try:
            reused = self._index_store.find_active_revision(
                user_id=user_id,
                workspace_id=workspace_id,
                document_id=document_id,
                checksum=checksum,
                pipeline_version=pipeline_version,
            )
            if reused:
                return reused.as_dict()
            for chunk in chunks:
                text = str(chunk.get("retrievable_text") or "")
                embedding, model = await self._vector_service._generate_embedding_with_model(
                    text, is_query=False
                )
                if not embedding or not model:
                    raise RuntimeError("document_embedding_unavailable")
                if embedding_model and model != embedding_model:
                    raise RuntimeError("document_embedding_model_changed_mid_revision")
                embedding_model = model
                source_dimension = len(embedding)
                chunk_id = str(chunk["chunk_id"])
                metadata = {
                    "workspace_id": workspace_id,
                    "document_id": document_id,
                    "revision_id": revision_id,
                    "checksum": checksum,
                    "chunk_id": chunk_id,
                    "node_ids": chunk.get("node_ids") or [],
                    "source_locations": chunk.get("source_locations") or [],
                    "heading_path": chunk.get("heading_path") or [],
                    "file_name": file_name,
                    "media_type": media_type,
                    "active": True,
                    "embedding_model": model,
                    "embedding_source_dimension": source_dimension,
                    "embedding_storage_dimension": 1536,
                    "schema_version": schema.get("schema_version"),
                    "pipeline_version": pipeline_version,
                    "index_version": "document-index.v1",
                }
                records.append(
                    {
                        "source_id": f"{document_id}:{revision_id}:{chunk_id}",
                        "title": file_name,
                        "content": text,
                        "embedding": embedding,
                        "metadata": metadata,
                    }
                )
            return self._index_store.replace_active_revision(
                user_id=user_id,
                workspace_id=workspace_id,
                document_id=document_id,
                revision_id=revision_id,
                records=records,
            ).as_dict()
        except Exception as exc:
            logger.warning("Document index projection failed for %s: %s", file_name, exc)
            return {
                "state": "failed",
                "indexed_chunks": 0,
                "revision_id": revision_id,
                "embedding_model": embedding_model,
            }


def build_event_analysis_projection(
    analysis_result: Dict[str, Any],
) -> Dict[str, Any]:
    """Return a bounded event projection; full document artifacts stay on disk."""
    projection = copy.deepcopy(analysis_result)
    file_info = projection.get("file_info")
    if isinstance(file_info, dict):
        for key in ("text_content", "extracted_text"):
            if isinstance(file_info.get(key), str):
                file_info[key] = file_info[key][:EVENT_TEXT_PREVIEW_CHARACTERS]
    document_summary = projection.get("document_ingestion")
    if isinstance(document_summary, dict):
        document_summary.pop("schema_artifact", None)
        document_summary.pop("chunk_manifest", None)
        if isinstance(document_summary.get("retrievable_preview"), str):
            document_summary["retrievable_preview"] = document_summary[
                "retrievable_preview"
            ][:EVENT_TEXT_PREVIEW_CHARACTERS]
    return projection


__all__ = [
    "DocumentIngestionHostFacade",
    "DocumentIngestionHostResult",
    "EVENT_TEXT_PREVIEW_CHARACTERS",
    "MAX_INDEXED_CHUNKS",
    "SUPPORTED_DOCUMENT_EXTENSIONS",
    "SUPPORTED_DOCUMENT_MEDIA_TYPES",
    "build_event_analysis_projection",
]
