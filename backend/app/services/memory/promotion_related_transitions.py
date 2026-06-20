"""Related surface transition helpers for memory promotion flows."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from backend.app.models.personal_governance.goal_ledger import GoalStatus
from backend.app.services.stores.postgres.goal_ledger_store import GoalLedgerStore
from backend.app.services.stores.postgres.personal_knowledge_store import (
    PersonalKnowledgeStore,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def verify_related_knowledge(
    personal_knowledge_store: PersonalKnowledgeStore,
    knowledge_ids: List[str],
    *,
    successor_memory_id: Optional[str],
) -> None:
    for knowledge_id in knowledge_ids:
        entry = personal_knowledge_store.get(knowledge_id)
        if not entry:
            continue
        entry.mark_verified()
        if successor_memory_id:
            entry.metadata["successor_memory_id"] = successor_memory_id
        personal_knowledge_store.update(entry)


def stale_related_knowledge(
    personal_knowledge_store: PersonalKnowledgeStore,
    knowledge_ids: List[str],
) -> None:
    for knowledge_id in knowledge_ids:
        entry = personal_knowledge_store.get(knowledge_id)
        if not entry:
            continue
        entry.mark_stale()
        personal_knowledge_store.update(entry)


def deprecate_related_knowledge(
    personal_knowledge_store: PersonalKnowledgeStore,
    knowledge_ids: List[str],
    *,
    successor_memory_id: str,
) -> None:
    for knowledge_id in knowledge_ids:
        entry = personal_knowledge_store.get(knowledge_id)
        if not entry:
            continue
        entry.deprecate(reason=f"superseded_by:{successor_memory_id}")
        entry.metadata["superseded_by_memory_id"] = successor_memory_id
        personal_knowledge_store.update(entry)


def activate_related_goals(
    goal_ledger_store: GoalLedgerStore,
    goal_ids: List[str],
    *,
    reason: str,
) -> None:
    for goal_id in goal_ids:
        entry = goal_ledger_store.get(goal_id)
        if not entry:
            continue
        if entry.status == GoalStatus.ACTIVE.value:
            continue
        goal_status = GoalStatus(entry.status)
        if entry.can_transition_to(GoalStatus.ACTIVE):
            entry.transition_to(GoalStatus.ACTIVE, reason=reason)
            goal_ledger_store.update(entry)
        elif goal_status == GoalStatus.PENDING_CONFIRMATION:
            entry.transition_to(GoalStatus.ACTIVE, reason=reason)
            goal_ledger_store.update(entry)


def stale_related_goals(
    goal_ledger_store: GoalLedgerStore,
    goal_ids: List[str],
    *,
    reason: str,
) -> None:
    for goal_id in goal_ids:
        entry = goal_ledger_store.get(goal_id)
        if not entry:
            continue
        if entry.status == GoalStatus.STALE.value:
            continue
        if entry.can_transition_to(GoalStatus.STALE):
            entry.transition_to(GoalStatus.STALE, reason=reason)
            goal_ledger_store.update(entry)


def deprecate_related_goals(
    goal_ledger_store: GoalLedgerStore,
    goal_ids: List[str],
    *,
    reason: str,
) -> None:
    for goal_id in goal_ids:
        entry = goal_ledger_store.get(goal_id)
        if not entry:
            continue
        if entry.status == GoalStatus.DEPRECATED.value:
            continue
        target = GoalStatus.DEPRECATED
        if entry.can_transition_to(target):
            entry.transition_to(target, reason=reason)
        else:
            entry.metadata.setdefault("transition_log", []).append(
                {
                    "from": entry.status,
                    "to": target.value,
                    "reason": reason,
                    "at": _utc_now().isoformat(),
                }
            )
            entry.status = target.value
        goal_ledger_store.update(entry)
