"""Host runtime ledger projection for meeting execution graphs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from backend.app.models.meeting_graph import (
    MeetingExecutionGraphEdge,
    MeetingExecutionGraphNode,
)
from backend.app.services.meeting_graph.cross_pack_evidence_ledger_projection import (
    project_cross_pack_evidence_ledger_graph,
)
from backend.app.services.meeting_graph.projection_utils import (
    _edge,
    _json_output,
    _read_string,
    _safe_id,
    _short_id,
)


@dataclass
class HostRuntimeLedgerGraphProjection:
    nodes: list[MeetingExecutionGraphNode] = field(default_factory=list)
    edges: list[MeetingExecutionGraphEdge] = field(default_factory=list)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _status_for_session(status: str) -> str:
    if status in {"failed", "bridge_unavailable", "bridge_disconnected"}:
        return "error"
    if status == "running":
        return "running"
    if status in {"interrupted", "closed"}:
        return "blocked"
    return "ready"


def _status_for_event(event_type: str, payload: Mapping[str, Any]) -> str:
    status = _read_string(payload.get("status")).lower()
    if event_type == "turn.failed" or status == "failed":
        return "error"
    if event_type in {"turn.started", "item.started", "tool.started"}:
        return "running"
    if event_type in {"session.interrupted", "approval.requested"}:
        return "blocked"
    return "ready"


def _lane_for_event(event_type: str) -> str:
    if event_type in {"assistant.message.completed", "turn.completed", "turn.failed"}:
        return "outputs"
    if event_type in {"artifact.provenance.recorded", "patch.proposed", "file.changed"}:
        return "artifacts"
    if event_type.startswith("approval."):
        return "commands"
    return "runs"


def _kind_for_event(event_type: str) -> str:
    if event_type == "assistant.message.completed":
        return "result"
    if event_type.startswith("tool."):
        return "tool_call"
    if event_type in {"artifact.provenance.recorded", "patch.proposed", "file.changed"}:
        return "artifact"
    if event_type.startswith("approval."):
        return "approval"
    return "event"


def _event_title(event_type: str, payload: Mapping[str, Any]) -> str:
    content = _read_string(payload.get("content") or payload.get("output_preview"))
    if content:
        return content.splitlines()[0][:120]
    reason = _read_string(payload.get("reason") or payload.get("error"))
    if reason:
        return f"{event_type}: {reason[:96]}"
    return event_type


def _timestamp(value: Any) -> str:
    if not value:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def project_host_runtime_ledger_graph(
    *,
    sessions: Iterable[Any],
    events_by_session: Mapping[str, Iterable[Any]],
) -> HostRuntimeLedgerGraphProjection:
    projection = HostRuntimeLedgerGraphProjection()

    for session in sessions:
        session_id = _read_string(getattr(session, "id", None))
        if not session_id:
            continue
        session_status = _read_string(getattr(session, "status", None), "ready")
        runtime_id = _read_string(getattr(session, "runtime_id", None), "runtime")
        runtime_surface = _read_string(getattr(session, "runtime_surface", None))
        session_metadata = _as_dict(getattr(session, "metadata", {}))
        session_node_id = f"host-session-{_safe_id(session_id)}"
        projection.nodes.append(
            MeetingExecutionGraphNode(
                id=session_node_id,
                eyebrow="Host Runtime",
                title=f"{runtime_id} session",
                detail=f"{session_status} · {_short_id(session_id)}",
                status=_status_for_session(session_status),
                kind="run",
                lane="runs",
                defaultInspector="trace",
                traceFilter=session_id,
                metadata={
                    "projection_source": "host_runtime_ledger",
                    "session_id": session_id,
                    "execution_id": getattr(session, "execution_id", None),
                    "runtime_surface": runtime_surface,
                    "runtime_id": runtime_id,
                    "bridge_id": getattr(session, "bridge_id", None),
                    "meeting_id": session_metadata.get("meeting_id"),
                    "graph_context_id": session_metadata.get("graph_context_id"),
                    "governance_trace_ref": getattr(
                        session,
                        "governance_trace_ref",
                        None,
                    ),
                    "updated_at": _timestamp(getattr(session, "updated_at", None)),
                },
            )
        )

        cross_pack_projection = project_cross_pack_evidence_ledger_graph(
            session_id=session_id,
            session_node_id=session_node_id,
            session_metadata=session_metadata,
        )
        projection.nodes.extend(cross_pack_projection.nodes)
        projection.edges.extend(cross_pack_projection.edges)

        previous_node_id = session_node_id
        for event in events_by_session.get(session_id, []):
            event_type = _read_string(getattr(event, "event_type", None), "event")
            payload = _as_dict(getattr(event, "payload", {}))
            seq = getattr(event, "seq", None)
            event_node_id = f"host-event-{_safe_id(session_id)}-{_safe_id(seq)}"
            projection.nodes.append(
                MeetingExecutionGraphNode(
                    id=event_node_id,
                    eyebrow=event_type,
                    title=_event_title(event_type, payload),
                    detail=" · ".join(
                        part
                        for part in (
                            f"seq {seq}" if seq is not None else "",
                            _read_string(getattr(event, "turn_id", None)),
                            _timestamp(getattr(event, "created_at", None)),
                        )
                        if part
                    ),
                    status=_status_for_event(event_type, payload),
                    kind=_kind_for_event(event_type),
                    lane=_lane_for_event(event_type),
                    output=_json_output(payload) if payload else None,
                    defaultInspector="trace",
                    traceFilter=f"{session_id}:{seq}" if seq is not None else session_id,
                    degraded=event_type == "turn.failed",
                    metadata={
                        "projection_source": "host_runtime_ledger",
                        "session_id": session_id,
                        "turn_id": getattr(event, "turn_id", None),
                        "seq": seq,
                        "event_type": event_type,
                        "item_id": getattr(event, "item_id", None),
                        "created_at": _timestamp(getattr(event, "created_at", None)),
                    },
                )
            )
            projection.edges.append(_edge(previous_node_id, event_node_id, "then"))
            previous_node_id = event_node_id

    return projection
