"""Registry for governed-memory evidence collectors."""

from __future__ import annotations

from typing import Any, Iterable, Protocol

from .base import EvidenceCollectionResult


class EvidenceCollector(Protocol):
    """Collector protocol for session-scoped evidence expansion."""

    summary_key: str

    def collect(
        self,
        *,
        memory_item_id: str,
        session: Any,
    ) -> EvidenceCollectionResult:
        """Collect and attach evidence for a canonical memory item."""


class EvidenceCollectorRegistry:
    """Run a sequence of evidence collectors against a closed meeting session."""

    def __init__(self, collectors: Iterable[EvidenceCollector]):
        self.collectors = list(collectors)

    def collect(
        self,
        *,
        memory_item_id: str,
        session: Any,
    ) -> list[EvidenceCollectionResult]:
        return [
            collector.collect(memory_item_id=memory_item_id, session=session)
            for collector in self.collectors
        ]
