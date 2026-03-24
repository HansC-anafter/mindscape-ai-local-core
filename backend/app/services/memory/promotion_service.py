"""Deterministic promotion lifecycle for canonical memory items."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.app.models.memory_contract import (
    MemoryEdge,
    MemoryEdgeType,
    MemoryItem,
    MemoryLifecycleStatus,
    MemoryUpdateMode,
    MemoryVerificationStatus,
    MemoryVersion,
)
from backend.app.models.personal_governance.goal_ledger import GoalLedgerEntry, GoalStatus
from backend.app.models.personal_governance.personal_knowledge import (
    PersonalKnowledge,
)
from backend.app.services.stores.postgres.goal_ledger_store import GoalLedgerStore
from backend.app.services.stores.postgres.memory_edge_store import MemoryEdgeStore
from backend.app.services.stores.postgres.memory_item_store import MemoryItemStore
from backend.app.services.stores.postgres.memory_version_store import MemoryVersionStore
from backend.app.services.stores.postgres.memory_writeback_run_store import (
    MemoryWritebackRunStore,
)
from backend.app.services.stores.postgres.personal_knowledge_store import (
    PersonalKnowledgeStore,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MemoryPromotionService:
    """Promotion lifecycle constrained to verify, stale, and supersede flows."""

    def __init__(
        self,
        *,
        run_store: Optional[MemoryWritebackRunStore] = None,
        memory_item_store: Optional[MemoryItemStore] = None,
        memory_version_store: Optional[MemoryVersionStore] = None,
        memory_edge_store: Optional[MemoryEdgeStore] = None,
        personal_knowledge_store: Optional[PersonalKnowledgeStore] = None,
        goal_ledger_store: Optional[GoalLedgerStore] = None,
    ) -> None:
        self.run_store = run_store or MemoryWritebackRunStore()
        self.memory_item_store = memory_item_store or MemoryItemStore()
        self.memory_version_store = memory_version_store or MemoryVersionStore()
        self.memory_edge_store = memory_edge_store or MemoryEdgeStore()
        self.personal_knowledge_store = (
            personal_knowledge_store or PersonalKnowledgeStore()
        )
        self.goal_ledger_store = goal_ledger_store or GoalLedgerStore()

    def verify_candidate(
        self,
        memory_item_id: str,
        *,
        related_knowledge_ids: Optional[List[str]] = None,
        related_goal_ids: Optional[List[str]] = None,
        reason: str = "",
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        run = self._get_or_create_run(
            transition="verify",
            memory_item_id=memory_item_id,
            idempotency_key=idempotency_key,
        )
        item = self._require_item(memory_item_id, run.id)

        if (
            item.lifecycle_status == MemoryLifecycleStatus.ACTIVE.value
            and item.verification_status == MemoryVerificationStatus.VERIFIED.value
        ):
            completed = self.run_store.mark_completed(
                run.id,
                summary={"memory_item_id": item.id, "noop": True, "transition": "verify"},
                update_mode_summary={MemoryUpdateMode.APPEND.value: 1},
                last_stage="completed",
            )
            return {"run": completed or run, "memory_item": item, "noop": True}

        if item.lifecycle_status != MemoryLifecycleStatus.CANDIDATE.value:
            raise ValueError(
                f"verify_candidate expects candidate memory item, got {item.lifecycle_status}"
            )

        resolved_knowledge_ids = self._resolve_related_knowledge_ids(
            memory_item_id, related_knowledge_ids
        )
        resolved_goal_ids = self._resolve_related_goal_ids(
            memory_item_id, related_goal_ids
        )

        now = _utc_now()
        item.lifecycle_status = MemoryLifecycleStatus.ACTIVE.value
        item.verification_status = MemoryVerificationStatus.VERIFIED.value
        item.last_confirmed_at = now
        item.updated_at = now
        item.update_mode = MemoryUpdateMode.APPEND.value
        self._append_transition_metadata(item, transition="verify", reason=reason)
        self.memory_item_store.update(item)
        self._create_state_version(item, run_id=run.id, update_mode=MemoryUpdateMode.APPEND.value)

        self._verify_related_knowledge(
            resolved_knowledge_ids, successor_memory_id=None
        )
        self._activate_related_goals(
            resolved_goal_ids, reason=reason or "memory_verified"
        )

        completed = self.run_store.mark_completed(
            run.id,
            summary={
                "memory_item_id": item.id,
                "transition": "verify",
                "related_knowledge_count": len(resolved_knowledge_ids),
                "related_goal_count": len(resolved_goal_ids),
            },
            update_mode_summary={MemoryUpdateMode.APPEND.value: 1},
            last_stage="completed",
        )
        return {"run": completed or run, "memory_item": item, "noop": False}

    def mark_stale(
        self,
        memory_item_id: str,
        *,
        related_knowledge_ids: Optional[List[str]] = None,
        related_goal_ids: Optional[List[str]] = None,
        reason: str = "",
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        run = self._get_or_create_run(
            transition="stale",
            memory_item_id=memory_item_id,
            idempotency_key=idempotency_key,
        )
        item = self._require_item(memory_item_id, run.id)

        if item.lifecycle_status == MemoryLifecycleStatus.STALE.value:
            completed = self.run_store.mark_completed(
                run.id,
                summary={"memory_item_id": item.id, "noop": True, "transition": "stale"},
                update_mode_summary={MemoryUpdateMode.APPEND.value: 1},
                last_stage="completed",
            )
            return {"run": completed or run, "memory_item": item, "noop": True}

        if item.lifecycle_status != MemoryLifecycleStatus.ACTIVE.value:
            raise ValueError(
                f"mark_stale expects active memory item, got {item.lifecycle_status}"
            )

        resolved_knowledge_ids = self._resolve_related_knowledge_ids(
            memory_item_id, related_knowledge_ids
        )
        resolved_goal_ids = self._resolve_related_goal_ids(
            memory_item_id, related_goal_ids
        )

        now = _utc_now()
        item.lifecycle_status = MemoryLifecycleStatus.STALE.value
        item.updated_at = now
        item.update_mode = MemoryUpdateMode.APPEND.value
        self._append_transition_metadata(item, transition="stale", reason=reason)
        self.memory_item_store.update(item)
        self._create_state_version(item, run_id=run.id, update_mode=MemoryUpdateMode.APPEND.value)

        self._stale_related_knowledge(resolved_knowledge_ids)
        self._stale_related_goals(resolved_goal_ids, reason=reason or "memory_stale")

        completed = self.run_store.mark_completed(
            run.id,
            summary={
                "memory_item_id": item.id,
                "transition": "stale",
                "related_knowledge_count": len(resolved_knowledge_ids),
                "related_goal_count": len(resolved_goal_ids),
            },
            update_mode_summary={MemoryUpdateMode.APPEND.value: 1},
            last_stage="completed",
        )
        return {"run": completed or run, "memory_item": item, "noop": False}

    def supersede_memory(
        self,
        memory_item_id: str,
        *,
        successor_title: Optional[str] = None,
        successor_claim: Optional[str] = None,
        successor_summary: Optional[str] = None,
        successor_memory_item_id: Optional[str] = None,
        related_knowledge_ids: Optional[List[str]] = None,
        related_goal_ids: Optional[List[str]] = None,
        reason: str = "",
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        run = self._get_or_create_run(
            transition="supersede",
            memory_item_id=memory_item_id,
            idempotency_key=idempotency_key
            or f"memory_promotion:supersede:{memory_item_id}:{successor_memory_item_id or successor_claim or successor_title or 'new'}",
        )
        item = self._require_item(memory_item_id, run.id)

        if item.lifecycle_status == MemoryLifecycleStatus.SUPERSEDED.value:
            completed = self.run_store.mark_completed(
                run.id,
                summary={"memory_item_id": item.id, "noop": True, "transition": "supersede"},
                update_mode_summary={MemoryUpdateMode.SUPERSEDE.value: 1},
                last_stage="completed",
            )
            return {"run": completed or run, "memory_item": item, "noop": True}

        if item.lifecycle_status != MemoryLifecycleStatus.ACTIVE.value:
            raise ValueError(
                f"supersede_memory expects active memory item, got {item.lifecycle_status}"
            )

        resolved_knowledge_ids = self._resolve_related_knowledge_ids(
            memory_item_id, related_knowledge_ids
        )
        resolved_goal_ids = self._resolve_related_goal_ids(
            memory_item_id, related_goal_ids
        )

        successor_item = self._resolve_successor_item(
            item,
            successor_memory_item_id=successor_memory_item_id,
            successor_title=successor_title,
            successor_claim=successor_claim,
            successor_summary=successor_summary,
            run_id=run.id,
            reason=reason,
        )

        now = _utc_now()
        item.lifecycle_status = MemoryLifecycleStatus.SUPERSEDED.value
        item.updated_at = now
        item.update_mode = MemoryUpdateMode.SUPERSEDE.value
        self._append_transition_metadata(
            item,
            transition="supersede",
            reason=reason,
            successor_memory_id=successor_item.id,
        )
        self.memory_item_store.update(item)
        self._create_state_version(
            item, run_id=run.id, update_mode=MemoryUpdateMode.SUPERSEDE.value
        )

        if not self.memory_edge_store.exists(
            from_memory_id=item.id,
            to_memory_id=successor_item.id,
            edge_type=MemoryEdgeType.SUPERSEDES.value,
        ):
            self.memory_edge_store.create(
                MemoryEdge.supersedes(
                    item.id,
                    successor_item.id,
                    reason=reason,
                    run_id=run.id,
                )
            )

        self._deprecate_related_knowledge(
            resolved_knowledge_ids, successor_memory_id=successor_item.id
        )
        self._deprecate_related_goals(
            resolved_goal_ids,
            reason=reason or f"superseded_by:{successor_item.id}",
        )

        completed = self.run_store.mark_completed(
            run.id,
            summary={
                "memory_item_id": item.id,
                "successor_memory_item_id": successor_item.id,
                "transition": "supersede",
                "related_knowledge_count": len(resolved_knowledge_ids),
                "related_goal_count": len(resolved_goal_ids),
            },
            update_mode_summary={MemoryUpdateMode.SUPERSEDE.value: 1},
            last_stage="completed",
        )
        return {
            "run": completed or run,
            "memory_item": item,
            "successor_memory_item": successor_item,
            "noop": False,
        }

    def _get_or_create_run(
        self, *, transition: str, memory_item_id: str, idempotency_key: Optional[str]
    ):
        run, _created = self.run_store.get_or_create(
            run_type=f"memory_promotion_{transition}",
            source_scope="memory_item",
            source_id=memory_item_id,
            idempotency_key=idempotency_key
            or f"memory_promotion:{transition}:{memory_item_id}",
            metadata={"transition": transition},
        )
        return run

    def _require_item(self, memory_item_id: str, run_id: str) -> MemoryItem:
        item = self.memory_item_store.get(memory_item_id)
        if item is None:
            self.run_store.mark_failed(
                run_id,
                error_detail=f"Memory item not found: {memory_item_id}",
                summary={"memory_item_id": memory_item_id},
                last_stage="failed",
            )
            raise ValueError(f"Memory item not found: {memory_item_id}")
        return item

    def _create_state_version(
        self, item: MemoryItem, *, run_id: str, update_mode: str
    ) -> MemoryVersion:
        version = MemoryVersion(
            memory_item_id=item.id,
            version_no=self.memory_version_store.get_next_version_no(item.id),
            update_mode=update_mode,
            claim_snapshot=item.claim,
            summary_snapshot=item.summary,
            metadata_snapshot=dict(item.metadata or {}),
            created_from_run_id=run_id,
        )
        self.memory_version_store.create(version)
        return version

    def _resolve_related_knowledge_ids(
        self, memory_item_id: str, explicit_ids: Optional[List[str]]
    ) -> List[str]:
        resolved = list(explicit_ids or [])
        if hasattr(self.personal_knowledge_store, "list_by_canonical_memory_item"):
            for entry in self.personal_knowledge_store.list_by_canonical_memory_item(
                memory_item_id
            ):
                if entry.id not in resolved:
                    resolved.append(entry.id)
        return resolved

    def _resolve_related_goal_ids(
        self, memory_item_id: str, explicit_ids: Optional[List[str]]
    ) -> List[str]:
        resolved = list(explicit_ids or [])
        if hasattr(self.goal_ledger_store, "list_by_canonical_memory_item"):
            for entry in self.goal_ledger_store.list_by_canonical_memory_item(
                memory_item_id
            ):
                if entry.id not in resolved:
                    resolved.append(entry.id)
        return resolved

    def _resolve_successor_item(
        self,
        item: MemoryItem,
        *,
        successor_memory_item_id: Optional[str],
        successor_title: Optional[str],
        successor_claim: Optional[str],
        successor_summary: Optional[str],
        run_id: str,
        reason: str,
    ) -> MemoryItem:
        if successor_memory_item_id:
            successor_item = self._require_item(successor_memory_item_id, run_id)
            if successor_item.supersedes_memory_id != item.id:
                successor_item.supersedes_memory_id = item.id
                successor_item.lifecycle_status = MemoryLifecycleStatus.ACTIVE.value
                successor_item.verification_status = MemoryVerificationStatus.VERIFIED.value
                successor_item.update_mode = MemoryUpdateMode.SUPERSEDE.value
                successor_item.updated_at = _utc_now()
                self._append_transition_metadata(
                    successor_item,
                    transition="successor_created",
                    reason=reason,
                    predecessor_memory_id=item.id,
                )
                self.memory_item_store.update(successor_item)
                self._create_state_version(
                    successor_item,
                    run_id=run_id,
                    update_mode=MemoryUpdateMode.SUPERSEDE.value,
                )
            return successor_item

        successor_item = MemoryItem(
            kind=item.kind,
            layer=item.layer,
            scope=item.scope,
            subject_type=item.subject_type,
            subject_id=item.subject_id,
            context_type=item.context_type,
            context_id=item.context_id,
            title=successor_title or item.title,
            claim=successor_claim or item.claim,
            summary=successor_summary or item.summary,
            salience=item.salience,
            confidence=item.confidence,
            verification_status=MemoryVerificationStatus.VERIFIED.value,
            lifecycle_status=MemoryLifecycleStatus.ACTIVE.value,
            valid_from=_utc_now(),
            observed_at=_utc_now(),
            update_mode=MemoryUpdateMode.SUPERSEDE.value,
            supersedes_memory_id=item.id,
            created_by_pipeline="memory_promotion_v1",
            created_from_run_id=run_id,
            metadata=dict(item.metadata or {}),
        )
        self._append_transition_metadata(
            successor_item,
            transition="successor_created",
            reason=reason,
            predecessor_memory_id=item.id,
        )
        self.memory_item_store.create(successor_item)
        self.memory_version_store.create(MemoryVersion.initial_from_item(successor_item))
        return successor_item

    def _append_transition_metadata(
        self,
        item: MemoryItem,
        *,
        transition: str,
        reason: str = "",
        successor_memory_id: Optional[str] = None,
        predecessor_memory_id: Optional[str] = None,
    ) -> None:
        history = list((item.metadata or {}).get("promotion_history", []) or [])
        entry: Dict[str, Any] = {"transition": transition, "at": _utc_now().isoformat()}
        if reason:
            entry["reason"] = reason
        if successor_memory_id:
            entry["successor_memory_id"] = successor_memory_id
            item.metadata["superseded_by_memory_id"] = successor_memory_id
        if predecessor_memory_id:
            entry["predecessor_memory_id"] = predecessor_memory_id
        history.append(entry)
        item.metadata["promotion_history"] = history

    def _verify_related_knowledge(
        self, knowledge_ids: List[str], *, successor_memory_id: Optional[str]
    ) -> None:
        for knowledge_id in knowledge_ids:
            entry = self.personal_knowledge_store.get(knowledge_id)
            if not entry:
                continue
            entry.mark_verified()
            if successor_memory_id:
                entry.metadata["successor_memory_id"] = successor_memory_id
            self.personal_knowledge_store.update(entry)

    def _stale_related_knowledge(self, knowledge_ids: List[str]) -> None:
        for knowledge_id in knowledge_ids:
            entry = self.personal_knowledge_store.get(knowledge_id)
            if not entry:
                continue
            entry.mark_stale()
            self.personal_knowledge_store.update(entry)

    def _deprecate_related_knowledge(
        self, knowledge_ids: List[str], *, successor_memory_id: str
    ) -> None:
        for knowledge_id in knowledge_ids:
            entry = self.personal_knowledge_store.get(knowledge_id)
            if not entry:
                continue
            entry.deprecate(reason=f"superseded_by:{successor_memory_id}")
            entry.metadata["superseded_by_memory_id"] = successor_memory_id
            self.personal_knowledge_store.update(entry)

    def _activate_related_goals(self, goal_ids: List[str], *, reason: str) -> None:
        for goal_id in goal_ids:
            entry = self.goal_ledger_store.get(goal_id)
            if not entry:
                continue
            if entry.status == GoalStatus.ACTIVE.value:
                continue
            goal_status = GoalStatus(entry.status)
            if entry.can_transition_to(GoalStatus.ACTIVE):
                entry.transition_to(GoalStatus.ACTIVE, reason=reason)
                self.goal_ledger_store.update(entry)
            elif goal_status == GoalStatus.PENDING_CONFIRMATION:
                entry.transition_to(GoalStatus.ACTIVE, reason=reason)
                self.goal_ledger_store.update(entry)

    def _stale_related_goals(self, goal_ids: List[str], *, reason: str) -> None:
        for goal_id in goal_ids:
            entry = self.goal_ledger_store.get(goal_id)
            if not entry:
                continue
            if entry.status == GoalStatus.STALE.value:
                continue
            if entry.can_transition_to(GoalStatus.STALE):
                entry.transition_to(GoalStatus.STALE, reason=reason)
                self.goal_ledger_store.update(entry)

    def _deprecate_related_goals(self, goal_ids: List[str], *, reason: str) -> None:
        for goal_id in goal_ids:
            entry = self.goal_ledger_store.get(goal_id)
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
            self.goal_ledger_store.update(entry)
