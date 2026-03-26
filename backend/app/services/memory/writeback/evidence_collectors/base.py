"""Shared collector primitives for governed-memory evidence expansion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, List


@dataclass
class EvidenceCollectionResult:
    """Normalized result from a single evidence collector run."""

    summary_key: str
    found_count: int = 0
    created_count: int = 0
    error: str | None = None

    def to_summary(self) -> dict[str, Any]:
        return {
            f"{self.summary_key}_count": self.found_count,
            f"{self.summary_key}_links_created": self.created_count,
            f"{self.summary_key}_error": self.error,
        }


def merge_collection_summaries(
    results: Iterable[EvidenceCollectionResult],
) -> dict[str, Any]:
    """Merge collector summaries into a single run summary payload."""

    summary: dict[str, Any] = {}
    for result in results:
        summary.update(result.to_summary())
    return summary


def collect_unique_execution_ids(decisions: Iterable[Any]) -> List[str]:
    """Collect stable execution IDs from meeting decisions."""

    execution_ids: List[str] = []
    seen_execution_ids: set[str] = set()
    for decision in decisions:
        source_action_item = getattr(decision, "source_action_item", None) or {}
        execution_id = source_action_item.get("execution_id")
        if not isinstance(execution_id, str):
            continue
        normalized = execution_id.strip()
        if not normalized or normalized in seen_execution_ids:
            continue
        seen_execution_ids.add(normalized)
        execution_ids.append(normalized)
    return execution_ids
