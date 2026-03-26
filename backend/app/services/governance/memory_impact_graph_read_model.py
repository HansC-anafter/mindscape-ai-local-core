"""Workspace-scoped read model for task-centered memory impact graphs."""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, Iterable, List, Optional

from backend.app.models.meeting_decision import MeetingDecision
from backend.app.models.meeting_session import MeetingSession
from backend.app.services.governance.memory_impact_graph_contract import (
    MemoryImpactGraphEdge,
    MemoryImpactGraphFocus,
    MemoryImpactGraphNode,
    MemoryImpactGraphResponse,
    MemoryImpactPacketSummary,
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
        requested_execution_id = execution_id

        warnings: List[str] = []
        if not selected_memory_packet:
            warnings.append("selected_memory_packet_missing")
        if not explicit_trace:
            warnings.append("memory_impact_trace_missing")
        if not canonical_memory:
            warnings.append("canonical_memory_missing")

        nodes_by_id: Dict[str, MemoryImpactGraphNode] = {}
        edges_by_id: Dict[str, MemoryImpactGraphEdge] = {}

        def upsert_node(node: MemoryImpactGraphNode) -> None:
            existing = nodes_by_id.get(node.id)
            if existing is None:
                nodes_by_id[node.id] = node
                return
            if not existing.label and node.label:
                existing.label = node.label
            if not existing.subtitle and node.subtitle:
                existing.subtitle = node.subtitle
            if not existing.status and node.status:
                existing.status = node.status
            if node.metadata:
                existing.metadata.update(node.metadata)

        def add_edge(
            from_node_id: str,
            to_node_id: str,
            kind: str,
            *,
            provenance: str = "explicit",
            metadata: Optional[Dict[str, Any]] = None,
        ) -> None:
            edge_id = f"{kind}:{from_node_id}->{to_node_id}:{provenance}"
            if edge_id in edges_by_id:
                return
            edges_by_id[edge_id] = MemoryImpactGraphEdge(
                id=edge_id,
                from_node_id=from_node_id,
                to_node_id=to_node_id,
                kind=kind,
                provenance=provenance,
                metadata=dict(metadata or {}),
            )

        session_node_id = (
            explicit_trace.get("session_node_id") or f"meeting_session:{session.id}"
        )
        execution_ids = self._collect_execution_ids(session)
        if requested_execution_id and requested_execution_id not in execution_ids:
            warnings.append("requested_execution_id_not_linked_to_session")

        upsert_node(
            MemoryImpactGraphNode(
                id=session_node_id,
                type="session",
                label=f"Meeting Session {session.id[:8]}",
                subtitle=session.meeting_type,
                status=(
                    session.status.value
                    if hasattr(session.status, "value")
                    else str(session.status)
                ),
                metadata={
                    "workspace_id": session.workspace_id,
                    "project_id": session.project_id,
                    "thread_id": session.thread_id,
                    "round_count": session.round_count,
                },
            )
        )

        for node in self._build_selected_packet_nodes(
            workspace_id=workspace_id,
            selected_memory_packet=selected_memory_packet,
        ):
            upsert_node(node)

        if not selected_node_ids:
            selected_node_ids = [
                node_id
                for node_id in nodes_by_id
                if node_id != session_node_id
                and not node_id.startswith("execution:")
                and not node_id.startswith("meeting_decision:")
                and not node_id.startswith("action_item:")
                and not node_id.startswith("session_digest:")
                and not node_id.startswith("artifact:")
            ]

        for node_id in selected_node_ids:
            if node_id not in nodes_by_id:
                upsert_node(
                    MemoryImpactGraphNode(
                        id=node_id,
                        type="memory_item",
                        label=node_id,
                        metadata={"placeholder": True},
                    )
                )
            add_edge(session_node_id, node_id, "selected_for_context")

        for exec_id in execution_ids:
            execution_node_id = f"execution:{exec_id}"
            upsert_node(
                MemoryImpactGraphNode(
                    id=execution_node_id,
                    type="execution",
                    label=f"Execution {exec_id[:8]}",
                    subtitle="workspace task",
                    metadata={"execution_id": exec_id},
                )
            )
            add_edge(session_node_id, execution_node_id, "produced")

        decisions = self._safe_list_decisions(session.id)
        decision_ids = list(explicit_trace.get("meeting_decision_node_ids") or [])
        if not decision_ids and decisions:
            decision_ids = [f"meeting_decision:{decision.id}" for decision in decisions]

        for index, decision in enumerate(decisions):
            node_id = (
                decision_ids[index]
                if index < len(decision_ids)
                else f"meeting_decision:{decision.id}"
            )
            upsert_node(
                MemoryImpactGraphNode(
                    id=node_id,
                    type="decision",
                    label=self._truncate(decision.content, 120),
                    subtitle=decision.category,
                    status=decision.status,
                    metadata={
                        "decision_id": decision.id,
                        "source_action_item": dict(decision.source_action_item or {}),
                    },
                )
            )
            add_edge(session_node_id, node_id, "produced")

        action_item_node_ids = list(explicit_trace.get("action_item_node_ids") or [])
        for index, action_item in enumerate(list(getattr(session, "action_items", []) or [])):
            node_id = (
                action_item_node_ids[index]
                if index < len(action_item_node_ids)
                else f"action_item:{session.id}:{index}"
            )
            label = (
                str(action_item.get("title") or "").strip()
                or str(action_item.get("description") or "").strip()
                or f"Action Item {index + 1}"
            )
            subtitle = str(action_item.get("assigned_to") or "").strip() or None
            upsert_node(
                MemoryImpactGraphNode(
                    id=node_id,
                    type="action_item",
                    label=self._truncate(label, 120),
                    subtitle=subtitle,
                    status=str(action_item.get("landing_status") or "").strip() or None,
                    metadata=dict(action_item or {}),
                )
            )
            add_edge(session_node_id, node_id, "produced")

            action_execution_id = str(action_item.get("execution_id") or "").strip()
            if action_execution_id:
                execution_node_id = f"execution:{action_execution_id}"
                upsert_node(
                    MemoryImpactGraphNode(
                        id=execution_node_id,
                        type="execution",
                        label=f"Execution {action_execution_id[:8]}",
                        subtitle="workspace task",
                        metadata={"execution_id": action_execution_id},
                    )
                )
                add_edge(node_id, execution_node_id, "produced")

            for artifact_ref in self._collect_artifact_refs(action_item):
                artifact_node_id = f"artifact:{artifact_ref}"
                upsert_node(
                    MemoryImpactGraphNode(
                        id=artifact_node_id,
                        type="artifact",
                        label=self._truncate(artifact_ref.rsplit("/", 1)[-1], 120),
                        subtitle="artifact reference",
                        metadata={"artifact_ref": artifact_ref},
                    )
                )
                add_edge(node_id, artifact_node_id, "produced")

        canonical_memory_item_id = str(canonical_memory.get("memory_item_id") or "").strip()
        canonical_memory_node_id = str(
            explicit_trace.get("canonical_writeback_node_id") or ""
        ).strip()
        if canonical_memory_item_id:
            canonical_memory_node_id = (
                canonical_memory_node_id or f"memory_item:{canonical_memory_item_id}"
            )
            memory_item = self.memory_item_store.get(canonical_memory_item_id)
            upsert_node(
                MemoryImpactGraphNode(
                    id=canonical_memory_node_id,
                    type="memory_item",
                    label=self._truncate(
                        getattr(memory_item, "title", "") or "Canonical Memory",
                        120,
                    ),
                    subtitle=self._truncate(
                        getattr(memory_item, "summary", "")
                        or getattr(memory_item, "claim", "")
                        or "",
                        180,
                    )
                    or None,
                    status=str(canonical_memory.get("lifecycle_status") or "").strip()
                    or None,
                    metadata={
                        "memory_item_id": canonical_memory_item_id,
                        "verification_status": canonical_memory.get("verification_status"),
                        "writeback_run_id": canonical_memory.get("writeback_run_id"),
                    },
                )
            )
            add_edge(
                session_node_id,
                canonical_memory_node_id,
                "writes_back_to",
                metadata={"writeback_run_id": canonical_memory.get("writeback_run_id")},
            )

        digest_id = str(canonical_memory.get("digest_id") or "").strip()
        digest_node_id = str(explicit_trace.get("digest_node_id") or "").strip()
        if digest_id:
            digest_node_id = digest_node_id or f"session_digest:{digest_id}"
            upsert_node(
                MemoryImpactGraphNode(
                    id=digest_node_id,
                    type="digest",
                    label=f"Session Digest {digest_id[:8]}",
                    subtitle="meeting closure digest",
                    metadata={"digest_id": digest_id},
                )
            )
            add_edge(session_node_id, digest_node_id, "produced")
            if canonical_memory_node_id:
                add_edge(canonical_memory_node_id, digest_node_id, "derived_from")

        packet_summary = MemoryImpactPacketSummary(
            selected_node_count=len(selected_node_ids),
            route_sections=list(selected_memory_packet.get("route_plan") or []),
            counts_by_type=dict(Counter(node.type for node in nodes_by_id.values())),
            selection=dict(selected_memory_packet.get("selection") or {}),
        )
        focus = MemoryImpactGraphFocus(
            workspace_id=workspace_id,
            session_id=session.id,
            focus_node_id=session_node_id,
            project_id=session.project_id,
            thread_id=session.thread_id,
            execution_id=requested_execution_id,
            execution_ids=execution_ids,
        )
        return MemoryImpactGraphResponse(
            workspace_id=workspace_id,
            session_id=session.id,
            focus=focus,
            packet_summary=packet_summary,
            nodes=list(nodes_by_id.values()),
            edges=list(edges_by_id.values()),
            warnings=warnings,
        )

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
        execution_ids: List[str] = []
        seen: set[str] = set()

        for raw_id in list((getattr(session, "metadata", {}) or {}).get("execution_ids") or []):
            normalized = str(raw_id or "").strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                execution_ids.append(normalized)

        for action_item in list(getattr(session, "action_items", []) or []):
            normalized = str(action_item.get("execution_id") or "").strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                execution_ids.append(normalized)

        return execution_ids

    def _build_selected_packet_nodes(
        self,
        *,
        workspace_id: str,
        selected_memory_packet: Dict[str, Any],
    ) -> List[MemoryImpactGraphNode]:
        layers = dict(selected_memory_packet.get("layers") or {})
        nodes: List[MemoryImpactGraphNode] = []

        core = dict(layers.get("core") or {})
        if self._has_any(core.values()):
            nodes.append(
                MemoryImpactGraphNode(
                    id=f"workspace_core:{workspace_id}",
                    type="memory_item",
                    label="Workspace Core Memory",
                    subtitle=self._truncate(
                        str(core.get("brand_identity") or core.get("voice_and_tone") or ""),
                        180,
                    )
                    or None,
                    status="active",
                    metadata={"packet_layer": "core", **core},
                )
            )

        knowledge_layers = dict(layers.get("knowledge") or {})
        for bucket in ("verified", "candidates"):
            for item in list(knowledge_layers.get(bucket) or []):
                if not isinstance(item, dict):
                    continue
                node_id = f"knowledge:{item.get('id')}"
                nodes.append(
                    MemoryImpactGraphNode(
                        id=node_id,
                        type="knowledge",
                        label=self._truncate(str(item.get("content") or ""), 120)
                        or node_id,
                        subtitle=str(item.get("knowledge_type") or "").strip() or None,
                        status=str(item.get("status") or "").strip() or None,
                        metadata={"packet_layer": f"knowledge.{bucket}", **item},
                    )
                )

        goal_layers = dict(layers.get("goals") or {})
        for bucket in ("active", "pending"):
            for item in list(goal_layers.get(bucket) or []):
                if not isinstance(item, dict):
                    continue
                node_id = f"goal:{item.get('id')}"
                nodes.append(
                    MemoryImpactGraphNode(
                        id=node_id,
                        type="goal",
                        label=self._truncate(str(item.get("title") or ""), 120) or node_id,
                        subtitle=self._truncate(str(item.get("description") or ""), 180)
                        or None,
                        status=str(item.get("status") or "").strip() or None,
                        metadata={"packet_layer": f"goals.{bucket}", **item},
                    )
                )

        project = dict(layers.get("project") or {})
        project_id = str(project.get("project_id") or "").strip()
        if self._has_any(
            [
                project_id,
                list(project.get("decision_history") or []),
                list(project.get("key_conversations") or []),
                list(project.get("artifact_index") or []),
            ]
        ):
            subtitle = ""
            decisions = list(project.get("decision_history") or [])
            if decisions and isinstance(decisions[0], dict):
                subtitle = str(decisions[0].get("decision") or "").strip()
            elif project.get("key_conversations"):
                subtitle = str((project.get("key_conversations") or [None])[0] or "").strip()
            nodes.append(
                MemoryImpactGraphNode(
                    id=f"project_memory:{project_id or workspace_id}",
                    type="memory_item",
                    label="Project Memory",
                    subtitle=self._truncate(subtitle, 180) or None,
                    status="context",
                    metadata={"packet_layer": "project", **project},
                )
            )

        member = dict(layers.get("member") or {})
        user_id = str(member.get("user_id") or "").strip()
        if self._has_any(
            [
                user_id,
                list(member.get("skills") or []),
                dict(member.get("preferences") or {}),
                list(member.get("learnings") or []),
            ]
        ):
            subtitle = ""
            skills = list(member.get("skills") or [])
            if skills:
                subtitle = ", ".join(str(skill) for skill in skills[:3])
            elif member.get("preferences"):
                subtitle = ", ".join(
                    f"{key}={value}"
                    for key, value in list(dict(member.get("preferences") or {}).items())[:2]
                )
            nodes.append(
                MemoryImpactGraphNode(
                    id=f"member_memory:{workspace_id}:{user_id}",
                    type="memory_item",
                    label="Member Memory",
                    subtitle=self._truncate(subtitle, 180) or None,
                    status="context",
                    metadata={"packet_layer": "member", **member},
                )
            )

        for item in list(layers.get("episodic") or []):
            if not isinstance(item, dict):
                continue
            node_id = f"memory_item:{item.get('id')}"
            nodes.append(
                MemoryImpactGraphNode(
                    id=node_id,
                    type="memory_item",
                    label=self._truncate(
                        str(item.get("title") or item.get("claim") or item.get("summary") or ""),
                        120,
                    )
                    or node_id,
                    subtitle=self._truncate(
                        str(item.get("summary") or item.get("claim") or ""),
                        180,
                    )
                    or None,
                    status=str(item.get("lifecycle_status") or "").strip() or None,
                    metadata={"packet_layer": "episodic", **item},
                )
            )

        return nodes

    @staticmethod
    def _collect_artifact_refs(action_item: Dict[str, Any]) -> List[str]:
        refs: List[str] = []
        seen: set[str] = set()
        candidates: List[Any] = []
        candidates.extend(list(action_item.get("asset_refs") or []))
        for key in ("artifact_id", "artifact_path", "result_json_path", "summary_md_path"):
            candidates.append(action_item.get(key))

        for candidate in candidates:
            normalized = str(candidate or "").strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                refs.append(normalized)
        return refs

    @staticmethod
    def _truncate(value: str, limit: int) -> str:
        text = str(value or "").strip()
        if len(text) <= limit:
            return text
        return f"{text[: max(0, limit - 1)].rstrip()}…"

    @staticmethod
    def _has_any(values: Iterable[Any]) -> bool:
        return any(value for value in values)
