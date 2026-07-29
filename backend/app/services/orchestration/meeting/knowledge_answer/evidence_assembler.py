"""Deduplicate bounded tool evidence before answer synthesis."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable


def canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class GroundedEvidenceAssembler:
    MAX_EVIDENCE = 48
    MAX_CONTENT_CHARS = 32768

    @staticmethod
    def _compact_evidence_ref(item: dict[str, Any]) -> dict[str, Any]:
        citation = item.get("citation")
        citation_ref = dict(citation) if isinstance(citation, dict) else {}
        return {
            "citation": citation_ref,
            "source_kind": item.get("source_kind"),
            "source_id": item.get("source_id"),
            "title": str(item.get("title") or "")[:512],
            "modality": item.get("modality"),
        }

    def assemble(
        self,
        results: Iterable[dict[str, Any]],
    ) -> dict[str, Any]:
        evidence: list[dict[str, Any]] = []
        citations: list[dict[str, Any]] = []
        coverage: list[dict[str, Any]] = []
        admission_hashes: list[str] = []
        seen_citations: set[tuple[str, str]] = set()
        for result in results:
            snapshot_hash = str(
                result.get("_meeting_admission_snapshot_hash") or ""
            )
            if snapshot_hash:
                admission_hashes.append(snapshot_hash)
            if isinstance(result.get("coverage"), dict):
                coverage.append(dict(result["coverage"]))
            for item in list(result.get("evidence") or []):
                if not isinstance(item, dict):
                    continue
                citation = item.get("citation")
                if not isinstance(citation, dict):
                    continue
                key = (
                    str(citation.get("citation_id") or ""),
                    str(citation.get("content_hash") or ""),
                )
                if not all(key) or key in seen_citations:
                    continue
                seen_citations.add(key)
                bounded = dict(item)
                bounded["content"] = str(
                    bounded.get("content") or ""
                )[: self.MAX_CONTENT_CHARS]
                evidence.append(bounded)
                citations.append(dict(citation))
                if len(evidence) >= self.MAX_EVIDENCE:
                    break
            if len(evidence) >= self.MAX_EVIDENCE:
                break
        return {
            "evidence": evidence,
            "evidence_refs": [
                self._compact_evidence_ref(item) for item in evidence
            ],
            "citations": citations,
            "coverage": coverage,
            "admission_snapshot_hashes": sorted(set(admission_hashes)),
            "evidence_digest": canonical_digest(
                {
                    "citations": citations,
                    "content_hashes": [
                        item.get("citation", {}).get("content_hash")
                        for item in evidence
                    ],
                }
            ),
        }


__all__ = ["GroundedEvidenceAssembler", "canonical_digest"]
