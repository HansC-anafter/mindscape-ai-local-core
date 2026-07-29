"""Bound and serialize tool results without exposing authorization principals."""

from __future__ import annotations

import json
from typing import Any

from backend.app.services.knowledge_retrieval.contracts import (
    KnowledgeRetrievalResult,
)

from .evidence_blocks import project_hit


MAX_RESULT_BYTES = 256 * 1024


def enforce_result_budget(payload: dict[str, Any]) -> dict[str, Any]:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    if len(encoded) > MAX_RESULT_BYTES:
        raise ValueError("knowledge_query_result_budget_exceeded")
    return payload


def project_search_result(
    result: KnowledgeRetrievalResult,
) -> dict[str, Any]:
    payload = {
        "contract_version": "knowledge_query.v1",
        "operation": "search",
        "requested_mode": result.requested_mode,
        "executed_mode": result.executed_mode,
        "evidence": [project_hit(hit) for hit in result.hits],
        "aggregates": [],
        "coverage": {
            "candidate_count": result.candidate_count,
            "authorized_result_count": result.final_authorized_count,
            "degraded_reasons": list(result.degraded_reasons),
            "graph_metrics": dict(result.graph_metrics or {}),
            "channel_coverage": dict(result.channel_coverage or {}),
        },
        "citations": [
            dict(hit.citation)
            for hit in result.hits
        ],
        "receipt": {
            "authorization_receipt_digest": (
                result.authorization_receipt_digest
            ),
            "transaction_count": result.transaction_count,
            "evidence_is_instruction": False,
            "fusion_revision": result.fusion_revision,
        },
    }
    return enforce_result_budget(payload)


__all__ = [
    "MAX_RESULT_BYTES",
    "enforce_result_budget",
    "project_search_result",
]
