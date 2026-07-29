"""Shared final-authorization and response helpers for retrieval facades."""

from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any

from .contracts import AuthorizedKnowledgeHit


class AuthorizationAwareKnowledgeRetrievalHelpersMixin:
    async def _final_authorize_rows(
        self,
        *,
        context,
        scope_type: str,
        scope_id: str,
        rows: list[dict[str, Any]],
    ) -> dict[str, int]:
        return await asyncio.to_thread(
            self._store.final_authorize,
            context=context,
            scope_type=scope_type,
            scope_id=scope_id,
            expected_bindings=(
                (
                    str(row["knowledge_resource_id"]),
                    int(row["authz_revision"]),
                )
                for row in rows
            ),
        )

    @staticmethod
    def _row_is_final_authorized(
        row: dict[str, Any],
        final: dict[str, int],
    ) -> bool:
        return final.get(str(row["knowledge_resource_id"])) == int(
            row["authz_revision"]
        )

    @staticmethod
    def _operation_receipt(
        principal_set_hash: str,
        scope_type: str,
        scope_id: str,
        rows: list[dict[str, Any]],
        final: dict[str, int],
    ) -> str:
        return hashlib.sha256(
            json.dumps(
                {
                    "principal_set_hash": principal_set_hash,
                    "scope": [scope_type, scope_id],
                    "candidate_bindings": sorted(
                        {
                            (
                                str(row["knowledge_resource_id"]),
                                int(row["authz_revision"]),
                            )
                            for row in rows
                        }
                    ),
                    "final_bindings": sorted(final.items()),
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _build_hit(
        row: dict[str, Any],
        *,
        score: float,
        channels: tuple[str, ...],
    ) -> AuthorizedKnowledgeHit:
        metadata = dict(row.get("metadata") or {})
        citation = {
            "citation_id": f"external_doc:{row['id']}",
            "knowledge_resource_id": str(row["knowledge_resource_id"]),
            "security_label_id": str(row["security_label_id"]),
            "projection_revision_id": (
                str(row["projection_revision_id"])
                if row.get("projection_revision_id")
                else None
            ),
            "source_app": str(row["source_app"]),
            "source_id": str(row["source_id"]),
            "source_ref": str(row.get("source_ref") or ""),
            "source_revision": str(metadata.get("revision_id") or ""),
            "content_hash": hashlib.sha256(
                str(row.get("content") or "").encode("utf-8")
            ).hexdigest(),
            "chunk_id": metadata.get("chunk_id"),
            "node_ids": metadata.get("node_ids") or [],
            "source_locations": metadata.get("source_locations") or [],
        }
        return AuthorizedKnowledgeHit(
            knowledge_resource_id=str(row["knowledge_resource_id"]),
            security_label_id=str(row["security_label_id"]),
            authz_revision=int(row["authz_revision"]),
            projection_revision_id=(
                str(row["projection_revision_id"])
                if row.get("projection_revision_id")
                else None
            ),
            source_app=str(row["source_app"]),
            source_id=str(row["source_id"]),
            content=str(row.get("content") or ""),
            metadata=metadata,
            score=max(0.0, score),
            channels=channels,
            citation=citation,
        )


__all__ = ["AuthorizationAwareKnowledgeRetrievalHelpersMixin"]
