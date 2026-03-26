"""StageResult collector for governed-memory evidence expansion."""

from __future__ import annotations

import logging
from typing import Any, Optional

from backend.app.models.memory_contract import MemoryEvidenceLink
from backend.app.services.memory.writeback.evidence_collectors.base import (
    EvidenceCollectionResult,
    collect_unique_execution_ids,
)
from backend.app.services.stores.meeting_session_store import MeetingSessionStore
from backend.app.services.stores.postgres.memory_evidence_link_store import (
    MemoryEvidenceLinkStore,
)
from backend.app.services.stores.stage_results_store import StageResultsStore

logger = logging.getLogger(__name__)


class StageResultEvidenceCollector:
    """Attach stage-level execution outcomes as supporting evidence."""

    summary_key = "stage_result"

    def __init__(
        self,
        *,
        evidence_link_store: MemoryEvidenceLinkStore,
        meeting_session_store: Optional[MeetingSessionStore] = None,
        stage_results_store: Optional[StageResultsStore] = None,
    ) -> None:
        self.evidence_link_store = evidence_link_store
        self.meeting_session_store = meeting_session_store or MeetingSessionStore()
        self.stage_results_store = stage_results_store or StageResultsStore()

    def collect(
        self,
        *,
        memory_item_id: str,
        session: Any,
    ) -> EvidenceCollectionResult:
        session_id = getattr(session, "id", "")
        try:
            decisions = self.meeting_session_store.list_decisions_by_session(session_id)
            execution_ids = collect_unique_execution_ids(decisions)

            found_count = 0
            created_count = 0
            for execution_id in execution_ids:
                stage_results = self._select_relevant_stage_results(execution_id)
                found_count += len(stage_results)
                for stage_result in stage_results:
                    if self.evidence_link_store.exists(
                        memory_item_id=memory_item_id,
                        evidence_type="stage_result",
                        evidence_id=stage_result.id,
                        link_role="supports",
                    ):
                        continue
                    self.evidence_link_store.create(
                        MemoryEvidenceLink.from_stage_result(memory_item_id, stage_result)
                    )
                    created_count += 1

            return EvidenceCollectionResult(
                summary_key=self.summary_key,
                found_count=found_count,
                created_count=created_count,
            )
        except Exception as exc:
            logger.warning(
                "Stage result evidence attachment failed for %s: %s",
                session_id,
                exc,
            )
            return EvidenceCollectionResult(
                summary_key=self.summary_key,
                error=str(exc),
            )

    def _select_relevant_stage_results(self, execution_id: str) -> list[Any]:
        stage_results = self.stage_results_store.list_stage_results(
            execution_id=execution_id,
            limit=20,
        )
        preferred = [
            stage_result
            for stage_result in stage_results
            if getattr(stage_result, "preview", None)
            or getattr(stage_result, "requires_review", False)
            or getattr(stage_result, "artifact_id", None)
        ]
        if preferred:
            return preferred
        return stage_results[:1]
