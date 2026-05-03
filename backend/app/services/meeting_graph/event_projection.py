"""Meeting event projection helpers for execution graphs."""

from __future__ import annotations

from typing import Any, Dict, Iterable

from backend.app.models.meeting_graph import (
    MeetingExecutionGraphNode,
    MeetingExecutionGraphResponse,
)
from backend.app.services.meeting_graph.projection_utils import (
    _edge,
    _json_output,
    _read_string,
    _safe_id,
)


def _event_type_value(event: Any) -> str:
    event_type = getattr(event, "event_type", "")
    return event_type.value if hasattr(event_type, "value") else str(event_type or "")


def _event_actor_value(event: Any) -> str:
    actor = getattr(event, "actor", "")
    return actor.value if hasattr(actor, "value") else str(actor or "")


def _event_payload(event: Any) -> Dict[str, Any]:
    payload = getattr(event, "payload", None)
    return payload if isinstance(payload, dict) else {}


def _event_runtime_node(event: Any) -> MeetingExecutionGraphNode:
    event_id = _read_string(getattr(event, "id", None), "event")
    event_type = _event_type_value(event)
    actor = _event_actor_value(event)
    payload = _event_payload(event)
    stage = _read_string(payload.get("stage"))
    agent_id = _read_string(payload.get("agent_id"))
    message = _read_string(
        payload.get("message")
        or payload.get("meeting_command")
        or payload.get("content")
        or stage
        or event_type,
        event_type or actor or "event",
    )

    if actor == "user":
        lane = "commands"
        kind = "command"
        eyebrow = "Command"
        status = "ready"
    elif stage:
        lane = "runs"
        kind = "run"
        eyebrow = "Runtime"
        status = "ready" if stage in {"agent_completed", "completed"} else "running"
    elif actor == "assistant":
        lane = "outputs"
        kind = "result"
        eyebrow = agent_id or "Assistant"
        status = "ready"
    else:
        lane = "runs"
        kind = "event"
        eyebrow = actor or event_type or "Event"
        status = "ready"

    detail_parts = [part for part in (stage, event_type, agent_id) if part]
    timestamp = getattr(event, "timestamp", None)
    if timestamp:
        try:
            detail_parts.append(timestamp.isoformat())
        except Exception:
            detail_parts.append(str(timestamp))

    return MeetingExecutionGraphNode(
        id=f"event-{_safe_id(event_id)}",
        eyebrow=eyebrow,
        title=message[:120],
        detail=" · ".join(detail_parts),
        status=status,
        kind=kind,
        lane=lane,
        output=_json_output(payload) if payload else None,
        defaultInspector="trace",
        traceFilter=event_id,
        metadata={
            "event_id": event_id,
            "event_type": event_type,
            "actor": actor,
            "payload": payload,
            "projection_source": "mind_events",
        },
    )


def merge_meeting_event_runtime_projection(
    response: MeetingExecutionGraphResponse,
    events: Iterable[Any],
) -> MeetingExecutionGraphResponse:
    seen_nodes = {node.id for node in response.nodes}
    seen_edges = {edge.id for edge in response.edges}
    previous_node_id = ""

    for event in events:
        node = _event_runtime_node(event)
        if node.id not in seen_nodes:
            response.nodes.append(node)
            seen_nodes.add(node.id)
        if previous_node_id:
            edge = _edge(previous_node_id, node.id, "then")
            if edge.id not in seen_edges:
                response.edges.append(edge)
                seen_edges.add(edge.id)
        previous_node_id = node.id

    return response
