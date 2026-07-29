"""Deterministically verify synthesized claims against admitted citations."""

from __future__ import annotations

from typing import Any

from .contracts import GroundedAnswerClaim


class GroundedAnswerCitationVerifier:
    def verify(
        self,
        *,
        synthesis: dict[str, Any],
        citations: list[dict[str, Any]],
    ) -> tuple[GroundedAnswerClaim, ...]:
        allowlist = {
            str(item.get("citation_id") or ""): str(
                item.get("content_hash") or ""
            )
            for item in citations
            if isinstance(item, dict)
        }
        raw_claims = synthesis.get("claims")
        if not isinstance(raw_claims, list) or not raw_claims:
            raise ValueError("grounded_answer_claims_required")
        claims: list[GroundedAnswerClaim] = []
        for raw in raw_claims:
            if not isinstance(raw, dict):
                raise ValueError("grounded_answer_claim_shape_invalid")
            citation_ids = tuple(
                str(item).strip()
                for item in list(raw.get("citation_ids") or [])
                if str(item).strip()
            )
            if not citation_ids:
                raise ValueError(
                    "grounded_answer_factual_claim_citation_required"
                )
            if any(citation_id not in allowlist for citation_id in citation_ids):
                raise ValueError("grounded_answer_citation_not_admitted")
            claims.append(
                GroundedAnswerClaim(
                    text=str(raw.get("text") or "").strip(),
                    citation_ids=citation_ids,
                )
            )
        return tuple(claims)


__all__ = ["GroundedAnswerCitationVerifier"]
