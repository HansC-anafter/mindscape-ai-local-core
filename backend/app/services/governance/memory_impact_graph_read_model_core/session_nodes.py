"""Session node helpers for memory impact graph read models."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from backend.app.models.meeting_decision import MeetingDecision
from backend.app.models.meeting_session import MeetingSession
from backend.app.services.governance.memory_impact_graph_contract import (
    MemoryImpactGraphNode,
)


def build_session_node(session: MeetingSession, session_node_id: str) -> MemoryImpactGraphNode:
    return MemoryImpactGraphNode(
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


def build_execution_node(execution_id: str) -> MemoryImpactGraphNode:
    return MemoryImpactGraphNode(
        id=f"execution:{execution_id}",
        type="execution",
        label=f"Execution {execution_id[:8]}",
        subtitle="workspace task",
        metadata={"execution_id": execution_id},
    )


def build_decision_node(
    decision: MeetingDecision,
    *,
    node_id: str,
) -> MemoryImpactGraphNode:
    return MemoryImpactGraphNode(
        id=node_id,
        type="decision",
        label=truncate(decision.content, 120),
        subtitle=decision.category,
        status=decision.status,
        metadata={
            "decision_id": decision.id,
            "source_action_item": dict(decision.source_action_item or {}),
        },
    )


def build_action_item_node(
    action_item: Dict[str, Any],
    *,
    node_id: str,
    index: int,
) -> MemoryImpactGraphNode:
    label = (
        str(action_item.get("title") or "").strip()
        or str(action_item.get("description") or "").strip()
        or f"Action Item {index + 1}"
    )
    subtitle = str(action_item.get("assigned_to") or "").strip() or None
    return MemoryImpactGraphNode(
        id=node_id,
        type="action_item",
        label=truncate(label, 120),
        subtitle=subtitle,
        status=str(action_item.get("landing_status") or "").strip() or None,
        metadata=dict(action_item or {}),
    )


def build_artifact_node(artifact_ref: str) -> MemoryImpactGraphNode:
    return MemoryImpactGraphNode(
        id=f"artifact:{artifact_ref}",
        type="artifact",
        label=truncate(artifact_ref.rsplit("/", 1)[-1], 120),
        subtitle="artifact reference",
        metadata={"artifact_ref": artifact_ref},
    )


def build_canonical_memory_node(
    *,
    node_id: str,
    memory_item_id: str,
    memory_item: Optional[Any],
    canonical_memory: Dict[str, Any],
) -> MemoryImpactGraphNode:
    return MemoryImpactGraphNode(
        id=node_id,
        type="memory_item",
        label=truncate(
            getattr(memory_item, "title", "") or "Canonical Memory",
            120,
        ),
        subtitle=truncate(
            getattr(memory_item, "summary", "")
            or getattr(memory_item, "claim", "")
            or "",
            180,
        )
        or None,
        status=str(canonical_memory.get("lifecycle_status") or "").strip() or None,
        metadata={
            "memory_item_id": memory_item_id,
            "verification_status": canonical_memory.get("verification_status"),
            "writeback_run_id": canonical_memory.get("writeback_run_id"),
        },
    )


def build_digest_node(digest_id: str, digest_node_id: str) -> MemoryImpactGraphNode:
    return MemoryImpactGraphNode(
        id=digest_node_id,
        type="digest",
        label=f"Session Digest {digest_id[:8]}",
        subtitle="meeting closure digest",
        metadata={"digest_id": digest_id},
    )


def collect_execution_ids(session: MeetingSession) -> List[str]:
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


def collect_artifact_refs(action_item: Dict[str, Any]) -> List[str]:
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


def truncate(value: str, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 1)].rstrip()}…"


def has_any(values: Iterable[Any]) -> bool:
    return any(value for value in values)
