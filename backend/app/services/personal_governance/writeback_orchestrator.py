"""
WritebackOrchestrator — Route meta meeting outputs through writeback policy.

ADR-001 v2 Phase 3: Writeback Orchestrator.

Processes a closed MetaMeetingSession, classifying each output and routing
it to the correct target (goal_ledger, personal_knowledge, dispatch_task,
review_history) per the Writeback Policy Spec routing table.

Lifecycle: MetaMeetingSession CLOSED → WRITEBACK_PENDING → ARCHIVED
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from backend.app.models.personal_governance.goal_ledger import GoalLedgerEntry
from backend.app.models.personal_governance.meta_meeting_session import (
    MetaMeetingSession,
)
from backend.app.models.personal_governance.personal_knowledge import (
    PersonalKnowledge,
)
from backend.app.models.personal_governance.writeback_receipt import WritebackReceipt
from backend.app.services.stores.postgres.goal_ledger_store import GoalLedgerStore
from backend.app.services.stores.postgres.meta_meeting_session_store import (
    MetaMeetingSessionStore,
)
from backend.app.services.stores.postgres.personal_knowledge_store import (
    PersonalKnowledgeStore,
)

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Routing table: category → handler
# ---------------------------------------------------------------------------

#  Category       | Condition                        | Target
#  action         | has workspace_target             | dispatch_task
#  action         | no workspace_target              | meta_personal_task (record)
#  decision       | goal pattern + conf ≥ 0.7        | goal_ledger (pending_confirmation)
#  decision       | preference/principle              | personal_knowledge (candidate)
#  decision       | tactical only                     | review_history (record)
#  blocker        | —                                 | review_history + flag
#  insight        | has goal anchor                   | personal_knowledge (candidate)
#  insight        | no anchor                         | review_history (record)


class WritebackOrchestrator:
    """Process MetaMeetingSession outputs through writeback policy routing."""

    def __init__(self):
        self.pk_store = PersonalKnowledgeStore()
        self.gl_store = GoalLedgerStore()
        self.session_store = MetaMeetingSessionStore()

    async def process_session(self, session: MetaMeetingSession) -> Dict[str, Any]:
        """Process all outputs of a closed MetaMeetingSession.

        Transitions: CLOSED → WRITEBACK_PENDING → ARCHIVED/WRITEBACK_FAILED.
        """
        if session.status.value != "closed":
            raise ValueError(
                f"Session {session.id} is {session.status.value}, expected closed"
            )

        # Transition to WRITEBACK_PENDING
        session.begin_writeback()
        self.session_store.update(session)

        summary = {
            "goals_created": 0,
            "knowledge_created": 0,
            "dispatched": 0,
            "recorded": 0,
            "skipped": 0,
            "errors": 0,
        }
        receipt_ids: List[str] = []

        try:
            # Process action items
            for item in session.action_items:
                receipt = self._route_action(item, session)
                if receipt:
                    receipt_ids.append(receipt.id)
                    self._persist_receipt(receipt)
                    if receipt.status == "completed":
                        if receipt.target_table == "dispatch_task":
                            summary["dispatched"] += 1
                        else:
                            summary["recorded"] += 1

            # Process decisions
            for decision in session.decisions:
                receipt = self._route_decision(decision, session)
                if receipt:
                    receipt_ids.append(receipt.id)
                    self._persist_receipt(receipt)
                    if receipt.status == "completed":
                        if receipt.target_table == "goal_ledger":
                            summary["goals_created"] += 1
                        elif receipt.target_table == "personal_knowledge":
                            summary["knowledge_created"] += 1
                        else:
                            summary["recorded"] += 1
                    elif receipt.status.startswith("skipped"):
                        summary["skipped"] += 1

            # Complete writeback
            session.complete_writeback(summary, receipt_ids)
            self.session_store.update(session)

            logger.info("Writeback complete for session %s: %s", session.id, summary)
            return {"session_id": session.id, "status": "archived", **summary}

        except Exception as exc:
            summary["errors"] += 1
            session.fail_writeback(str(exc))
            self.session_store.update(session)
            logger.error("Writeback failed for session %s: %s", session.id, exc)
            return {"session_id": session.id, "status": "writeback_failed", **summary}

    # -----------------------------------------------------------------
    # Routing handlers
    # -----------------------------------------------------------------

    def _route_action(
        self, item: Dict[str, Any], session: MetaMeetingSession
    ) -> Optional[WritebackReceipt]:
        """Route an action item per writeback policy.

        action + workspace_target → dispatch_task
        action + no target → meta_personal_task (record only)
        """
        try:
            workspace_target = item.get("workspace_target") or item.get("workspace_id")

            if workspace_target:
                # Dispatch to target workspace
                # Phase 3: record intent to dispatch; actual dispatch deferred
                return WritebackReceipt(
                    meta_session_id=session.id,
                    source_decision_id=item.get("id", str(uuid.uuid4())),
                    target_table="dispatch_task",
                    target_id="",  # filled by dispatcher
                    writeback_type="dispatch",
                    status="completed",
                    metadata={
                        "workspace_target": workspace_target,
                        "title": item.get("title", ""),
                        "priority": item.get("priority", "medium"),
                    },
                )
            else:
                # Personal task — record for review
                return WritebackReceipt(
                    meta_session_id=session.id,
                    source_decision_id=item.get("id", str(uuid.uuid4())),
                    target_table="review_history",
                    target_id="",
                    writeback_type="record",
                    status="completed",
                    metadata={
                        "title": item.get("title", ""),
                        "purpose": item.get("purpose", ""),
                    },
                )
        except Exception as exc:
            logger.warning("Failed to route action item: %s", exc)
            return None

    def _route_decision(
        self, decision: Dict[str, Any], session: MetaMeetingSession
    ) -> Optional[WritebackReceipt]:
        """Route a decision per writeback policy.

        decision + goal pattern + conf ≥ 0.7 → goal_ledger
        decision + preference/principle → personal_knowledge
        decision + tactical → review_history
        blocker → review_history + flag
        insight + anchor → personal_knowledge
        insight + no anchor → review_history
        """
        try:
            category = decision.get("category", "decision")
            content = decision.get("content", "")
            confidence = decision.get("confidence", 0.5)
            scope = decision.get("scope", "tactical")

            # Blocker → review_history + flag
            if category == "blocker":
                return WritebackReceipt(
                    meta_session_id=session.id,
                    source_decision_id=decision.get("id", str(uuid.uuid4())),
                    target_table="review_history",
                    target_id="",
                    writeback_type="record",
                    status="completed",
                    metadata={
                        "flagged_for_next_review": True,
                        "content": content[:200],
                    },
                )

            # Goal-level decision → goal_ledger
            if scope == "goal-level" and confidence >= 0.7:
                return self._write_goal(decision, session)

            # Preference/principle → personal_knowledge
            if scope in ("preference", "principle") or category == "insight":
                return self._write_knowledge(decision, session)

            # Tactical → review_history (record only)
            return WritebackReceipt(
                meta_session_id=session.id,
                source_decision_id=decision.get("id", str(uuid.uuid4())),
                target_table="review_history",
                target_id="",
                writeback_type="record",
                status="completed",
                metadata={"scope": scope, "content": content[:200]},
            )

        except Exception as exc:
            logger.warning("Failed to route decision: %s", exc)
            return None

    # -----------------------------------------------------------------
    # Write handlers (with writeback policy enforcement)
    # -----------------------------------------------------------------

    def _write_goal(
        self, decision: Dict[str, Any], session: MetaMeetingSession
    ) -> WritebackReceipt:
        """Write to goal_ledger with cooldown enforcement."""
        content = decision.get("content", "")
        title = decision.get("title") or content[:80]
        confidence = decision.get("confidence", 0.7)

        # Check 7-day cooldown on similar goals
        existing = self.gl_store.list_by_owner(session.owner_profile_id, limit=50)
        for g in existing:
            if title.lower() in g.title.lower() or g.title.lower() in title.lower():
                if g.last_updated_at and (_utc_now() - g.last_updated_at) < timedelta(
                    days=7
                ):
                    return WritebackReceipt(
                        meta_session_id=session.id,
                        source_decision_id=decision.get("id", ""),
                        target_table="goal_ledger",
                        target_id=g.id,
                        writeback_type="cooldown_skip",
                        status="skipped_cooldown",
                    )

        # Count active goals written in this session
        session_goals = sum(
            1
            for ai in session.action_items
            if ai.get("_writeback_target") == "goal_ledger"
        )
        if session_goals >= 3:
            return WritebackReceipt(
                meta_session_id=session.id,
                source_decision_id=decision.get("id", ""),
                target_table="goal_ledger",
                target_id="",
                writeback_type="session_cap_skip",
                status="skipped_cooldown",
            )

        # Create pending_confirmation goal
        entry = GoalLedgerEntry(
            owner_profile_id=session.owner_profile_id,
            title=title,
            description=decision.get("description", content),
            status="pending_confirmation",
            horizon=decision.get("horizon", "open-ended"),
            source_digest_ids=session.digest_ids[:5],
            metadata={
                "meta_session_id": session.id,
                "confidence": confidence,
            },
        )
        self.gl_store.create(entry)

        return WritebackReceipt(
            meta_session_id=session.id,
            source_decision_id=decision.get("id", ""),
            target_table="goal_ledger",
            target_id=entry.id,
            writeback_type="pending_confirmation",
            status="completed",
        )

    def _write_knowledge(
        self, decision: Dict[str, Any], session: MetaMeetingSession
    ) -> WritebackReceipt:
        """Write to personal_knowledge with dedup and throttle."""
        content = decision.get("content", "")
        confidence = decision.get("confidence", 0.5)
        knowledge_type = decision.get("scope", "preference")
        if knowledge_type not in (
            "goal",
            "preference",
            "principle",
            "value",
            "pattern",
            "skill",
            "context",
        ):
            knowledge_type = "preference"

        # Dedup check
        existing = self.pk_store.find_similar_content(session.owner_profile_id, content)
        if existing:
            return WritebackReceipt(
                meta_session_id=session.id,
                source_decision_id=decision.get("id", ""),
                target_table="personal_knowledge",
                target_id=existing.id,
                writeback_type="dedup_skip",
                status="skipped_dedup",
            )

        # Create candidate
        entry = PersonalKnowledge(
            owner_profile_id=session.owner_profile_id,
            knowledge_type=knowledge_type,
            content=content,
            status="candidate",
            confidence=confidence,
            source_evidence=[{"meta_session_id": session.id}],
            source_workspace_ids=[],
            valid_scope="global",
            metadata={"meta_session_id": session.id},
        )
        self.pk_store.create(entry)

        return WritebackReceipt(
            meta_session_id=session.id,
            source_decision_id=decision.get("id", ""),
            target_table="personal_knowledge",
            target_id=entry.id,
            writeback_type="candidate",
            status="completed",
        )

    # -----------------------------------------------------------------
    # Receipt persistence
    # -----------------------------------------------------------------

    def _persist_receipt(self, receipt: WritebackReceipt) -> None:
        """Persist a WritebackReceipt to the audit table."""
        try:
            from sqlalchemy import text

            base = self  # reuse PostgresStoreBase
            with base.transaction() as conn:
                conn.execute(
                    text(
                        """
                        INSERT INTO writeback_receipts
                        (id, meta_session_id, source_decision_id, target_table,
                         target_id, writeback_type, status, created_at, metadata)
                        VALUES (:id, :msid, :sdid, :tt, :tid, :wt, :st, now(), :meta)
                    """
                    ),
                    {
                        "id": receipt.id,
                        "msid": receipt.meta_session_id,
                        "sdid": receipt.source_decision_id,
                        "tt": receipt.target_table,
                        "tid": receipt.target_id,
                        "wt": receipt.writeback_type,
                        "st": receipt.status,
                        "meta": self.serialize_json(
                            receipt.metadata if hasattr(receipt, "metadata") else {}
                        ),
                    },
                )
        except Exception as exc:
            logger.warning(
                "Failed to persist writeback receipt %s: %s", receipt.id, exc
            )
