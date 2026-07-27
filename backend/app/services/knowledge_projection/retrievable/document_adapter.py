"""Host-owned document records compiled into the neutral projection writer."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Mapping

from .text_compatibility import (
    EXTERNAL_DOCS_VECTOR_DIMENSION,
    fit_external_docs_embedding,
)

from .write_contracts import (
    ExternalDocumentWrite,
    ProjectionChannelWrite,
    ProjectionEvidenceWrite,
    RetrievableProjectionWrite,
)


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def compile_document_projection(
    *,
    workspace_id: str,
    document_id: str,
    revision_id: str,
    records: Iterable[Mapping[str, Any]],
) -> tuple[RetrievableProjectionWrite, tuple[ExternalDocumentWrite, ...]]:
    prepared_documents: list[ExternalDocumentWrite] = []
    evidence_units: list[ProjectionEvidenceWrite] = []
    channels: list[ProjectionChannelWrite] = []
    canonical_records: list[dict[str, Any]] = []
    embedding_model: str | None = None
    checksum: str | None = None

    for source_record in records:
        metadata = dict(source_record["metadata"])
        if (
            metadata.get("workspace_id") != workspace_id
            or metadata.get("document_id") != document_id
            or metadata.get("revision_id") != revision_id
            or metadata.get("active") is not True
        ):
            raise ValueError("document_index_record_identity_mismatch")
        model = str(metadata.get("embedding_model") or "")
        if not model:
            raise ValueError("document_index_requires_one_embedding_model")
        if embedding_model is not None and model != embedding_model:
            raise ValueError("document_index_requires_one_embedding_model")
        embedding_model = model
        record_checksum = str(metadata.get("checksum") or "")
        if checksum is not None and record_checksum and record_checksum != checksum:
            raise ValueError("document_index_requires_one_checksum")
        checksum = checksum or record_checksum or None
        content = str(source_record["content"])
        source_id = str(source_record["source_id"])
        unit_key = str(metadata.get("chunk_id") or source_id)
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        fitted = tuple(fit_external_docs_embedding(source_record["embedding"]))
        prepared_documents.append(
            ExternalDocumentWrite(
                source_id=source_id,
                doc_type="document_chunk",
                title=str(source_record.get("title") or ""),
                content=content,
                embedding=fitted,
                metadata=metadata,
            )
        )
        evidence_units.append(
            ProjectionEvidenceWrite(
                unit_key=unit_key,
                unit_kind="text_span",
                owner_asset_ref=f"document:{document_id}",
                content_hash=content_hash,
                media_type=(
                    str(metadata["media_type"]) if metadata.get("media_type") else None
                ),
                anchor={
                    "kind": "text_span",
                    "start": 0,
                    "end": max(1, len(content)),
                },
            )
        )
        channels.append(
            ProjectionChannelWrite(
                unit_key=unit_key,
                channel_id="text.external_docs",
                modality="text",
                profile_revision=(
                    f"text.external_docs.{EXTERNAL_DOCS_VECTOR_DIMENSION}.{model}"
                ),
                model_revision=model,
                dimension=EXTERNAL_DOCS_VECTOR_DIMENSION,
                calibration_revision=None,
                index_revision="external_docs.compatibility.v2",
                required=True,
                state="active",
                row_count=1,
                byte_count=len(fitted) * 4,
                physical_store_ref="public.external_docs",
            )
        )
        canonical_records.append(
            {
                "source_id": source_id,
                "content_hash": content_hash,
                "metadata": metadata,
            }
        )

    if not prepared_documents or embedding_model is None:
        raise ValueError("document_index_requires_complete_records")
    content_hash = checksum if checksum and len(checksum) == 64 else _canonical_hash(
        canonical_records
    )
    projection_hash = _canonical_hash(
        {
            "source_instance_id": document_id,
            "source_revision": revision_id,
            "content_hash": content_hash,
            "records": canonical_records,
            "projector_revision": "document-index.v2",
        }
    )
    payload = RetrievableProjectionWrite(
        source_instance_id=document_id,
        source_revision=revision_id,
        content_hash=content_hash,
        descriptor_id="document",
        descriptor_revision="document-ingestion.1.0.0",
        projector_revision="document-index.v2",
        facet_schema_revision="document-facets.v1",
        embedding_profile_revision=(
            f"text.external_docs.{EXTERNAL_DOCS_VECTOR_DIMENSION}.{embedding_model}"
        ),
        projection_hash=projection_hash,
        evidence_units=tuple(evidence_units),
        channels=tuple(channels),
    )
    return payload, tuple(prepared_documents)


__all__ = ["compile_document_projection"]
