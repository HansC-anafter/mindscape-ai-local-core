"""Workspace-scoped read model for task-centered memory impact graphs."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from backend.app.models.meeting_decision import MeetingDecision
from backend.app.models.meeting_session import MeetingSession
from backend.app.services.governance.memory_impact_graph_contract import (
    MemoryImpactGraphNode,
    MemoryImpactGraphResponse,
)
from backend.app.services.governance.memory_impact_graph_read_model_core.graph_builder import (
    build_memory_impact_graph,
)
from backend.app.services.governance.memory_impact_graph_read_model_core.packet_nodes import (
    build_selected_packet_nodes,
)
from backend.app.services.governance.memory_impact_graph_read_model_core.session_nodes import (
    collect_artifact_refs,
    collect_execution_ids,
    has_any,
    truncate,
)
from backend.app.services.stores.meeting_session_store import MeetingSessionStore
from backend.app.services.stores.postgres.memory_item_store import MemoryItemStore


class MemoryImpactGraphReadModel:
    """Build a minimal operator-facing graph from persisted session trace metadata."""

    def __init__(
        self,
        *,
        meeting_session_store: Optional[MeetingSessionStore] = None,
        memory_item_store: Optional[MemoryItemStore] = None,
    ) -> None:
        self.meeting_session_store = meeting_session_store or MeetingSessionStore()
        self.memory_item_store = memory_item_store or MemoryItemStore()

    def build_for_workspace(
        self,
        workspace_id: str,
        *,
        session_id: Optional[str] = None,
        execution_id: Optional[str] = None,
        thread_id: Optional[str] = None,
    ) -> MemoryImpactGraphResponse:
        session = self._resolve_session(
            workspace_id=workspace_id,
            session_id=session_id,
            execution_id=execution_id,
            thread_id=thread_id,
        )
        if session is None:
            raise LookupError("Memory impact graph session not found")

        metadata = dict(getattr(session, "metadata", {}) or {})
        selected_memory_packet = dict(metadata.get("selected_memory_packet") or {})
        selected_node_ids = list(metadata.get("selected_memory_packet_node_ids") or [])
        memory_impact_trace = dict(metadata.get("memory_impact_trace") or {})
        explicit_trace = dict(memory_impact_trace.get("explicit") or {})
        canonical_memory = dict(metadata.get("canonical_memory") or {})

        warnings: List[str] = []
        if not selected_memory_packet:
            warnings.append("selected_memory_packet_missing")
        if not explicit_trace:
            warnings.append("memory_impact_trace_missing")
        if not canonical_memory:
            warnings.append("canonical_memory_missing")

        execution_ids = collect_execution_ids(session)
        decisions = self._safe_list_decisions(session.id)
        canonical_memory_item = self._load_canonical_memory_item(canonical_memory)
        return build_memory_impact_graph(
            workspace_id=workspace_id,
            session=session,
            selected_memory_packet=selected_memory_packet,
            selected_node_ids=selected_node_ids,
            explicit_trace=explicit_trace,
            canonical_memory=canonical_memory,
            requested_execution_id=execution_id,
            execution_ids=execution_ids,
            decisions=decisions,
            canonical_memory_item=canonical_memory_item,
            warnings=warnings,
        )

    def _load_canonical_memory_item(
        self,
        canonical_memory: Dict[str, Any],
    ) -> Optional[Any]:
        canonical_memory_item_id = str(canonical_memory.get("memory_item_id") or "").strip()
        if not canonical_memory_item_id:
            return None
        return self.memory_item_store.get(canonical_memory_item_id)

    def _resolve_session(
        self,
        *,
        workspace_id: str,
        session_id: Optional[str],
        execution_id: Optional[str],
        thread_id: Optional[str],
    ) -> Optional[MeetingSession]:
        if session_id:
            session = self.meeting_session_store.get_by_id(session_id)
            if session and session.workspace_id == workspace_id:
                return session
            return None

        sessions = list(
            self.meeting_session_store.list_by_workspace(workspace_id, None, 100, 0)
        )

        if execution_id:
            for session in sessions:
                if execution_id in self._collect_execution_ids(session):
                    return session
                for action_item in list(getattr(session, "action_items", []) or []):
                    if str(action_item.get("execution_id") or "").strip() == execution_id:
                        return session
            return None

        if thread_id:
            for session in sessions:
                if getattr(session, "thread_id", None) == thread_id:
                    return session
            return None

        return sessions[0] if sessions else None

    def _safe_list_decisions(self, session_id: str) -> List[MeetingDecision]:
        try:
            return list(self.meeting_session_store.list_decisions_by_session(session_id))
        except Exception:
            return []

    @staticmethod
    def _collect_execution_ids(session: MeetingSession) -> List[str]:
        return collect_execution_ids(session)

    def _build_selected_packet_nodes(
        self,
        *,
        workspace_id: str,
        selected_memory_packet: Dict[str, Any],
    ) -> List[MemoryImpactGraphNode]:
        return build_selected_packet_nodes(
            workspace_id=workspace_id,
            selected_memory_packet=selected_memory_packet,
        )

    @staticmethod
    def _collect_artifact_refs(action_item: Dict[str, Any]) -> List[str]:
        return collect_artifact_refs(action_item)

    @staticmethod
    def _truncate(value: str, limit: int) -> str:
        return truncate(value, limit)

    @staticmethod
    def _has_any(values: Iterable[Any]) -> bool:
        return has_any(values)
