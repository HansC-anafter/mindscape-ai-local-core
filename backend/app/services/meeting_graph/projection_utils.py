"""Shared utilities for meeting graph projection services."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional

from backend.app.models.meeting_graph import (
    MeetingExecutionGraphEdge,
    MeetingExecutionGraphNode,
)


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _read_string(value: Any, fallback: str = "") -> str:
    return value if isinstance(value, str) and value.strip() else fallback


def _short_id(value: Any) -> str:
    raw = str(value or "")
    if len(raw) <= 18:
        return raw or "none"
    return f"{raw[:8]}...{raw[-6:]}"


def _safe_id(value: Any) -> str:
    raw = str(value or "none")
    return "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in raw)[:96]


def _json_output(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, indent=2, default=str)
    except Exception:
        return str(value)


def _edge(
    from_id: str,
    to_id: str,
    edge_type: str,
    label: Optional[str] = None,
) -> MeetingExecutionGraphEdge:
    return MeetingExecutionGraphEdge(
        id=f"edge-{_safe_id(from_id)}-{_safe_id(edge_type)}-{_safe_id(to_id)}",
        from_id=from_id,
        to_id=to_id,
        type=edge_type,
        label=label,
    )


def _object_ref_payload(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        try:
            return value.model_dump(exclude_none=True)
        except Exception:
            return {}
    return {}


def _relation_payload(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        try:
            return value.model_dump(exclude_none=True)
        except Exception:
            pass
    payload: Dict[str, Any] = {}
    for field in (
        "relation_id",
        "relation_kind",
        "source_ref",
        "target_ref",
        "source_role",
        "target_role",
        "provenance_type",
        "provenance_id",
        "meeting_id",
        "metadata",
    ):
        if hasattr(value, field):
            payload[field] = getattr(value, field)
    if payload:
        payload["source_ref"] = _object_ref_payload(payload.get("source_ref"))
        payload["target_ref"] = _object_ref_payload(payload.get("target_ref"))
        payload["metadata"] = _as_dict(payload.get("metadata"))
    return payload


def _node_ref_uri(node: MeetingExecutionGraphNode) -> str:
    ref = _as_dict(node.metadata.get("ref"))
    return _read_string(ref.get("uri"))


def _object_node_title(ref: Dict[str, Any]) -> str:
    object_kind = _read_string(ref.get("object_kind"), "object")
    object_id = _read_string(ref.get("object_id"), ref.get("uri"))
    return f"{object_kind} {_short_id(object_id)}"


def _object_node_lane(ref: Dict[str, Any], role: str = "") -> str:
    object_kind = _read_string(ref.get("object_kind"))
    if role == "output" or object_kind in {"generated_reels_asset"} or object_kind.endswith("_asset"):
        return "artifacts"
    return "context"


def _fallback_object_node(
    *,
    ref: Dict[str, Any],
    role: str = "",
    relation_id: str = "",
) -> MeetingExecutionGraphNode:
    uri = _read_string(ref.get("uri"), _read_string(ref.get("object_id"), "unknown"))
    lane = _object_node_lane(ref, role)
    return MeetingExecutionGraphNode(
        id=f"object-{_safe_id(uri)}",
        eyebrow=role or _read_string(ref.get("owner_pack"), "Object"),
        title=_object_node_title(ref),
        detail=uri,
        status="context" if lane == "context" else "ready",
        kind="object" if lane == "context" else "artifact",
        lane=lane,
        defaultInspector="object",
        degraded=not bool(_read_string(ref.get("uri"))),
        metadata={
            "ref": ref,
            "role": role or None,
            "relation_id": relation_id or None,
        },
    )


def _relation_node_id(payload: Dict[str, Any]) -> str:
    explicit = _read_string(payload.get("relation_id"))
    if explicit:
        return f"relation-{_safe_id(explicit)}"
    source_uri = _read_string(_as_dict(payload.get("source_ref")).get("uri"))
    target_uri = _read_string(_as_dict(payload.get("target_ref")).get("uri"))
    digest = hashlib.sha256(
        json.dumps(
            {
                "source_uri": source_uri,
                "relation_kind": _read_string(payload.get("relation_kind")),
                "target_uri": target_uri,
                "provenance_id": _read_string(payload.get("provenance_id")),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"relation-{digest}"


def _relation_action_plan_id(relation: Dict[str, Any]) -> str:
    metadata = _as_dict(relation.get("metadata"))
    provenance_type = _read_string(relation.get("provenance_type"))
    provenance_id = _read_string(relation.get("provenance_id"))
    if provenance_type in {"object_action_plan", "object_action_execution"} and provenance_id:
        return provenance_id
    return _read_string(metadata.get("action_plan_id"))


def _merge_plan_summary(summary: Dict[str, Any], relation: Dict[str, Any]) -> None:
    metadata = _as_dict(relation.get("metadata"))
    provenance_type = _read_string(relation.get("provenance_type"))
    status = _read_string(metadata.get("status"))
    instruction = _read_string(
        metadata.get("instruction")
        or metadata.get("meeting_command")
        or metadata.get("command")
    )
    affordance_verb = _read_string(
        metadata.get("affordance_verb")
        or metadata.get("verb")
        or _as_dict(metadata.get("selected_affordance")).get("verb")
    )
    if instruction and not summary.get("instruction"):
        summary["instruction"] = instruction
    if affordance_verb and not summary.get("affordance_verb"):
        summary["affordance_verb"] = affordance_verb
    if status and not summary.get("status"):
        summary["status"] = status
    if provenance_type == "object_action_execution":
        summary["has_execution"] = True
        if status:
            summary["execution_status"] = status
    summary.setdefault("relations", []).append(relation)
