"""IntentLog collector for governed-memory evidence expansion."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Optional

from backend.app.models.memory_contract import MemoryEvidenceLink
from backend.app.services.memory.writeback.evidence_collectors.base import (
    EvidenceCollectionResult,
)
from backend.app.services.stores.postgres.intent_logs_store import (
    PostgresIntentLogsStore,
)
from backend.app.services.stores.postgres.memory_evidence_link_store import (
    MemoryEvidenceLinkStore,
)

logger = logging.getLogger(__name__)


class IntentLogEvidenceCollector:
    """Attach routing and user-override intent logs as supporting evidence."""

    summary_key = "intent_log"

    def __init__(
        self,
        *,
        evidence_link_store: MemoryEvidenceLinkStore,
        intent_log_store: Optional[PostgresIntentLogsStore] = None,
    ) -> None:
        self.evidence_link_store = evidence_link_store
        self.intent_log_store = intent_log_store or PostgresIntentLogsStore()

    def collect(
        self,
        *,
        memory_item_id: str,
        session: Any,
    ) -> EvidenceCollectionResult:
        workspace_id = getattr(session, "workspace_id", None)
        session_started_at = getattr(session, "started_at", None)
        session_ended_at = getattr(session, "ended_at", None) or session_started_at

        if not workspace_id or session_started_at is None or session_ended_at is None:
            return EvidenceCollectionResult(summary_key=self.summary_key)

        try:
            start_time = session_started_at - timedelta(minutes=30)
            end_time = session_ended_at + timedelta(minutes=5)
            logs = self.intent_log_store.list_intent_logs(
                workspace_id=workspace_id,
                project_id=getattr(session, "project_id", None),
                start_time=start_time,
                end_time=end_time,
                limit=20,
            )
            relevant_logs = [
                intent_log
                for intent_log in logs
                if self._has_relevant_decision(intent_log)
            ][:3]

            created_count = 0
            for intent_log in relevant_logs:
                if self.evidence_link_store.exists(
                    memory_item_id=memory_item_id,
                    evidence_type="intent_log",
                    evidence_id=intent_log.id,
                    link_role="supports",
                ):
                    continue
                self.evidence_link_store.create(
                    MemoryEvidenceLink.from_intent_log(memory_item_id, intent_log)
                )
                created_count += 1

            return EvidenceCollectionResult(
                summary_key=self.summary_key,
                found_count=len(relevant_logs),
                created_count=created_count,
            )
        except Exception as exc:
            logger.warning(
                "Intent log evidence attachment failed for %s: %s",
                getattr(session, "id", ""),
                exc,
            )
            return EvidenceCollectionResult(
                summary_key=self.summary_key,
                error=str(exc),
            )

    @staticmethod
    def _has_relevant_decision(intent_log: Any) -> bool:
        final_decision = getattr(intent_log, "final_decision", None) or {}
        if not isinstance(final_decision, dict) or not final_decision:
            return False

        selected_playbook_code = final_decision.get("selected_playbook_code")
        resolution_strategy = final_decision.get("resolution_strategy")
        requires_user_approval = final_decision.get("requires_user_approval")
        user_override = getattr(intent_log, "user_override", None)

        return any(
            (
                isinstance(selected_playbook_code, str) and selected_playbook_code.strip(),
                isinstance(resolution_strategy, str) and resolution_strategy.strip(),
                requires_user_approval is True,
                bool(user_override),
            )
        )
