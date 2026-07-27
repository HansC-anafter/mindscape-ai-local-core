"""Typed bounded evidence blocks; retrieved content is always untrusted."""

from __future__ import annotations

from typing import Any

from backend.app.services.knowledge_retrieval.contracts import (
    AuthorizedKnowledgeHit,
)


def project_hit(hit: AuthorizedKnowledgeHit) -> dict[str, Any]:
    metadata = dict(hit.metadata)
    media_type = str(metadata.get("media_type") or "")
    block_kind = "text_excerpt"
    if media_type.startswith("image/"):
        block_kind = "image_ref"
    elif media_type.startswith("video/"):
        block_kind = "video_ref"
    elif media_type.startswith("audio/"):
        block_kind = "audio_ref"
    return {
        "kind": block_kind,
        "trust": "untrusted_evidence",
        "content": hit.content[:32768],
        "owner_pointer": (
            metadata.get("owner_asset_ref")
            or hit.citation.get("source_ref")
        ),
        "anchor": (
            metadata.get("anchor")
            or {
                "chunk_id": metadata.get("chunk_id"),
                "source_locations": metadata.get("source_locations") or [],
            }
        ),
        "channels": list(hit.channels),
        "score": hit.score,
        "citation": dict(hit.citation),
    }


__all__ = ["project_hit"]
