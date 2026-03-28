"""Refresh meeting/session evidence when terminal task facts arrive after close."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.app.models.memory_contract import MemoryEvidenceLink
from backend.app.services.stores.meeting_session_store import MeetingSessionStore
from backend.app.services.stores.postgres.artifacts_store import PostgresArtifactsStore
from backend.app.services.stores.postgres.memory_evidence_link_store import (
    MemoryEvidenceLinkStore,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class MeetingTerminalEvidenceRefreshService:
    """Backfill terminal execution facts onto closed meeting artifacts."""

    def __init__(
        self,
        *,
        meeting_session_store: Optional[MeetingSessionStore] = None,
        artifact_store: Optional[PostgresArtifactsStore] = None,
        evidence_link_store: Optional[MemoryEvidenceLinkStore] = None,
    ) -> None:
        self.meeting_session_store = meeting_session_store or MeetingSessionStore()
        self.artifact_store = artifact_store or PostgresArtifactsStore()
        self.evidence_link_store = evidence_link_store or MemoryEvidenceLinkStore()

    def refresh_for_task(self, task: Any) -> Dict[str, Any]:
        session_id = self._resolve_meeting_session_id(task)
        if not session_id:
            return {"refreshed": False, "reason": "no_meeting_session"}

        session = self.meeting_session_store.get_by_id(session_id)
        if session is None:
            return {"refreshed": False, "reason": "meeting_session_missing"}
        if getattr(session, "ended_at", None) is None:
            return {"refreshed": False, "reason": "meeting_session_not_closed"}

        artifact = self._resolve_artifact(task)
        updated_action_items, matched_action_items = self._sync_action_items(
            action_items=getattr(session, "action_items", []) or [],
            task=task,
            artifact=artifact,
        )

        updated_decisions = 0
        if matched_action_items:
            session.action_items = updated_action_items
            metadata = dict(getattr(session, "metadata", {}) or {})
            metadata["last_terminal_refresh"] = {
                "task_id": getattr(task, "id", None),
                "execution_id": self._execution_identity(task),
                "status": self._task_status(task),
                "artifact_id": getattr(artifact, "id", None),
                "refreshed_at": _utc_now_iso(),
            }
            session.metadata = metadata
            self.meeting_session_store.update(session)
            updated_decisions = self._sync_decisions(
                session_id=session_id,
                action_items=updated_action_items,
                task=task,
                artifact=artifact,
                memory_item_id=self._canonical_memory_item_id(session),
            )

        memory_item_id = self._canonical_memory_item_id(session)
        links_upserted = 0
        if memory_item_id:
            self.evidence_link_store.upsert(
                MemoryEvidenceLink.from_task_execution(memory_item_id, task)
            )
            links_upserted += 1
            if artifact is not None:
                self.evidence_link_store.upsert(
                    MemoryEvidenceLink.from_artifact_result(memory_item_id, artifact)
                )
                links_upserted += 1

        return {
            "refreshed": bool(matched_action_items or links_upserted),
            "session_id": session_id,
            "memory_item_id": memory_item_id,
            "matched_action_items": matched_action_items,
            "updated_decisions": updated_decisions,
            "links_upserted": links_upserted,
        }

    def _sync_action_items(
        self,
        *,
        action_items: List[Dict[str, Any]],
        task: Any,
        artifact: Any,
    ) -> tuple[List[Dict[str, Any]], int]:
        updated_items: List[Dict[str, Any]] = []
        matched = 0
        for action_item in action_items:
            item = copy.deepcopy(action_item)
            if self._action_item_matches_task(item, task):
                matched += 1
                self._stamp_task_facts(item, task)
                if artifact is not None:
                    self._stamp_artifact_facts(item, artifact)
            updated_items.append(item)
        return updated_items, matched

    def _sync_decisions(
        self,
        *,
        session_id: str,
        action_items: List[Dict[str, Any]],
        task: Any,
        artifact: Any,
        memory_item_id: Optional[str],
    ) -> int:
        updated_count = 0
        items_by_intent = {
            self._normalized(item.get("intent_id")): item
            for item in action_items
            if self._normalized(item.get("intent_id"))
        }
        items_by_phase = {
            self._normalized(item.get("source_phase_id")): item
            for item in action_items
            if self._normalized(item.get("source_phase_id"))
        }
        for decision in self.meeting_session_store.list_decisions_by_session(session_id):
            source_action_item = dict(getattr(decision, "source_action_item", {}) or {})
            target_item = None
            intent_id = self._normalized(source_action_item.get("intent_id"))
            phase_id = self._normalized(source_action_item.get("source_phase_id"))
            if intent_id:
                target_item = items_by_intent.get(intent_id)
            if target_item is None and phase_id:
                target_item = items_by_phase.get(phase_id)
            if target_item is None or not self._action_item_matches_task(target_item, task):
                continue

            decision.source_action_item = copy.deepcopy(target_item)
            if self._task_status(task) == "succeeded":
                decision.status = "resolved"
                decision.resolved_by_task_id = getattr(task, "id", None)
            elif decision.source_action_item.get("landing_status"):
                decision.status = "dispatched"

            self.meeting_session_store.update_decision(decision)
            updated_count += 1

            if memory_item_id:
                self.evidence_link_store.upsert(
                    MemoryEvidenceLink.from_meeting_decision(memory_item_id, decision)
                )

        return updated_count

    def _stamp_task_facts(self, action_item: Dict[str, Any], task: Any) -> None:
        execution_id = self._execution_identity(task)
        task_id = self._normalized(getattr(task, "id", None))
        source_phase_id = self._task_phase_id(task)
        source_intent_id = self._task_source_intent_id(task)
        completed_at = getattr(task, "completed_at", None)

        if task_id and not self._normalized(action_item.get("task_id")):
            action_item["task_id"] = task_id
        if execution_id and not self._normalized(action_item.get("execution_id")):
            action_item["execution_id"] = execution_id
        self._append_unique(action_item, "task_ids", task_id)
        self._append_unique(action_item, "execution_ids", execution_id)

        if source_phase_id and not self._normalized(action_item.get("source_phase_id")):
            action_item["source_phase_id"] = source_phase_id
        if source_intent_id and not self._normalized(
            action_item.get("source_intent_id")
        ):
            action_item["source_intent_id"] = source_intent_id

        action_item["task_status"] = self._task_status(task)
        action_item["task_error"] = getattr(task, "error", None)
        if completed_at is not None:
            action_item["task_completed_at"] = (
                completed_at.isoformat()
                if hasattr(completed_at, "isoformat")
                else str(completed_at)
            )
        action_item["terminal_refresh_at"] = _utc_now_iso()

    def _stamp_artifact_facts(self, action_item: Dict[str, Any], artifact: Any) -> None:
        action_item["artifact_id"] = getattr(artifact, "id", None)
        action_item["artifact_path"] = getattr(artifact, "storage_ref", None)
        self._append_unique(action_item, "asset_refs", getattr(artifact, "id", None))
        self._append_unique(
            action_item,
            "asset_refs",
            getattr(artifact, "storage_ref", None),
        )

        metadata = getattr(artifact, "metadata", None) or {}
        landing = metadata.get("landing") if isinstance(metadata, dict) else None
        if isinstance(landing, dict):
            for key in ("result_json_path", "summary_md_path"):
                value = landing.get(key)
                if value:
                    action_item[key] = value

    def _action_item_matches_task(self, action_item: Dict[str, Any], task: Any) -> bool:
        task_ids = {
            self._normalized(getattr(task, "id", None)),
            self._execution_identity(task),
        }
        task_ids.discard(None)

        action_ids = {
            self._normalized(action_item.get("task_id")),
            self._normalized(action_item.get("execution_id")),
        }
        action_ids.update(self._normalized_list(action_item.get("task_ids")))
        action_ids.update(self._normalized_list(action_item.get("execution_ids")))
        action_ids.discard(None)
        if task_ids & action_ids:
            return True

        source_phase_id = self._task_phase_id(task)
        if source_phase_id and source_phase_id == self._normalized(
            action_item.get("source_phase_id")
        ):
            return True

        source_intent_id = self._task_source_intent_id(task)
        if source_intent_id and source_intent_id == self._normalized(
            action_item.get("source_intent_id") or action_item.get("intent_id")
        ):
            return True

        return False

    @staticmethod
    def _canonical_memory_item_id(session: Any) -> Optional[str]:
        metadata = getattr(session, "metadata", {}) or {}
        return MeetingTerminalEvidenceRefreshService._normalized(
            metadata.get("canonical_memory_item_id")
        )

    @staticmethod
    def _resolve_meeting_session_id(task: Any) -> Optional[str]:
        direct = MeetingTerminalEvidenceRefreshService._normalized(
            getattr(task, "meeting_session_id", None)
        )
        if direct:
            return direct
        execution_context = getattr(task, "execution_context", None) or {}
        return (
            MeetingTerminalEvidenceRefreshService._normalized(
                execution_context.get("meeting_session_id")
            )
            or MeetingTerminalEvidenceRefreshService._normalized(
                (execution_context.get("inputs") or {}).get("meeting_session_id")
            )
        )

    @staticmethod
    def _task_phase_id(task: Any) -> Optional[str]:
        execution_context = getattr(task, "execution_context", None) or {}
        provenance = execution_context.get("ir_provenance") or {}
        return MeetingTerminalEvidenceRefreshService._normalized(
            execution_context.get("phase_id") or provenance.get("phase_id")
        )

    @staticmethod
    def _task_source_intent_id(task: Any) -> Optional[str]:
        execution_context = getattr(task, "execution_context", None) or {}
        provenance = execution_context.get("ir_provenance") or {}
        return MeetingTerminalEvidenceRefreshService._normalized(
            execution_context.get("source_intent_id")
            or provenance.get("source_intent_id")
        )

    @staticmethod
    def _task_status(task: Any) -> str:
        status = getattr(task, "status", None)
        return (
            status.value
            if hasattr(status, "value")
            else str(status or "").strip()
        )

    def _resolve_artifact(self, task: Any) -> Any:
        execution_id = self._execution_identity(task)
        if not execution_id:
            return None
        return self.artifact_store.get_by_execution_id(execution_id)

    @staticmethod
    def _execution_identity(task: Any) -> Optional[str]:
        return MeetingTerminalEvidenceRefreshService._normalized(
            getattr(task, "execution_id", None) or getattr(task, "id", None)
        )

    @staticmethod
    def _append_unique(action_item: Dict[str, Any], key: str, value: Optional[str]) -> None:
        normalized = MeetingTerminalEvidenceRefreshService._normalized(value)
        if not normalized:
            return
        values = [
            item
            for item in MeetingTerminalEvidenceRefreshService._normalized_list(
                action_item.get(key)
            )
            if item is not None
        ]
        if normalized not in values:
            values.append(normalized)
        action_item[key] = values

    @staticmethod
    def _normalized_list(values: Any) -> List[Optional[str]]:
        if not isinstance(values, list):
            return []
        return [MeetingTerminalEvidenceRefreshService._normalized(value) for value in values]

    @staticmethod
    def _normalized(value: Any) -> Optional[str]:
        text = str(value or "").strip()
        return text or None
