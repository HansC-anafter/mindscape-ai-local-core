"""GovernanceDecision collector for governed-memory evidence expansion."""

from __future__ import annotations

import logging
from typing import Any, Optional

from backend.app.models.memory_contract import MemoryEvidenceLink
from backend.app.services.governance.governance_store import GovernanceStore
from backend.app.services.memory.writeback.evidence_collectors.base import (
    EvidenceCollectionResult,
    collect_unique_execution_ids,
)
from backend.app.services.stores.meeting_session_store import MeetingSessionStore
from backend.app.services.stores.postgres.memory_evidence_link_store import (
    MemoryEvidenceLinkStore,
)

logger = logging.getLogger(__name__)


class GovernanceDecisionEvidenceCollector:
    """Attach recorded governance approvals and rejections as evidence."""

    summary_key = "governance_decision"

    def __init__(
        self,
        *,
        evidence_link_store: MemoryEvidenceLinkStore,
        meeting_session_store: Optional[MeetingSessionStore] = None,
        governance_store: Optional[GovernanceStore] = None,
    ) -> None:
        self.evidence_link_store = evidence_link_store
        self.meeting_session_store = meeting_session_store or MeetingSessionStore()
        self.governance_store = governance_store or GovernanceStore()

    def collect(
        self,
        *,
        memory_item_id: str,
        session: Any,
    ) -> EvidenceCollectionResult:
        session_id = getattr(session, "id", "")
        workspace_id = getattr(session, "workspace_id", "")
        if not workspace_id:
            return EvidenceCollectionResult(summary_key=self.summary_key)

        try:
            decisions = self.meeting_session_store.list_decisions_by_session(session_id)
            execution_ids = collect_unique_execution_ids(decisions)

            found_count = 0
            created_count = 0
            for execution_id in execution_ids:
                governance_decisions = self.governance_store.list_decisions_for_execution(
                    workspace_id=workspace_id,
                    execution_id=execution_id,
                    limit=50,
                )
                found_count += len(governance_decisions)
                for decision in governance_decisions:
                    evidence_id = decision.get("decision_id")
                    if not isinstance(evidence_id, str) or not evidence_id:
                        continue
                    if self.evidence_link_store.exists(
                        memory_item_id=memory_item_id,
                        evidence_type="governance_decision",
                        evidence_id=evidence_id,
                        link_role="supports",
                    ):
                        continue
                    self.evidence_link_store.create(
                        MemoryEvidenceLink.from_governance_decision(
                            memory_item_id,
                            decision,
                        )
                    )
                    created_count += 1

            return EvidenceCollectionResult(
                summary_key=self.summary_key,
                found_count=found_count,
                created_count=created_count,
            )
        except Exception as exc:
            logger.warning(
                "Governance decision evidence attachment failed for %s: %s",
                session_id,
                exc,
            )
            return EvidenceCollectionResult(
                summary_key=self.summary_key,
                error=str(exc),
            )
