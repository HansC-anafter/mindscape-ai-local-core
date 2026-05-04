"""Command-ledger projection helpers for meeting execution graphs."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

from pydantic import BaseModel, Field

from backend.app.models.meeting_command import MeetingCommandRecord


class CommandLedgerGraphProjection(BaseModel):
    """Command nodes plus lookup indexes used by graph assembly."""

    nodes: List[Dict[str, Any]] = Field(default_factory=list)
    plan_command_node_ids: Dict[str, str] = Field(default_factory=dict)
    action_plan_ids: List[str] = Field(default_factory=list)


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


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


def _status_value(value: Any, fallback: str = "accepted") -> str:
    if hasattr(value, "value"):
        return str(value.value)
    return _read_string(value, fallback)


def _ui_status_for_command(value: Any) -> str:
    status = _status_value(value).lower()
    if status == "drafted":
        return "pending"
    if status == "accepted":
        return "pending"
    if status == "running":
        return "running"
    if status == "completed":
        return "ready"
    if status == "failed":
        return "error"
    if status == "superseded":
        return "blocked"
    return "pending"


def _requested_action_payload(command: MeetingCommandRecord) -> Dict[str, Any]:
    requested_action = getattr(command, "requested_action", None)
    if hasattr(requested_action, "model_dump"):
        return requested_action.model_dump(exclude_none=True)
    return _as_dict(requested_action)


def project_command_ledger_graph(
    commands: Iterable[MeetingCommandRecord],
) -> CommandLedgerGraphProjection:
    """Project durable command rows into command-lane graph nodes."""

    projection = CommandLedgerGraphProjection()
    for command in commands:
        command_id = _read_string(getattr(command, "command_id", None))
        if not command_id:
            continue
        requested_action = _requested_action_payload(command)
        verb = _read_string(
            requested_action.get("verb")
            or requested_action.get("affordance_verb")
            or requested_action.get("playbook_code"),
            "command",
        )
        command_node_id = f"command-{_safe_id(command_id)}"
        metadata = _as_dict(getattr(command, "metadata", {}))
        meeting_orchestration = _as_dict(metadata.get("meeting_orchestration"))
        action_plan_id = _read_string(metadata.get("action_plan_id"))
        if action_plan_id:
            projection.plan_command_node_ids[action_plan_id] = command_node_id
            projection.action_plan_ids.append(action_plan_id)
        ledger_status = _status_value(getattr(command, "status", ""))
        projection.nodes.append(
            {
                "id": command_node_id,
                "eyebrow": "Command",
                "title": _read_string(getattr(command, "intent_text", ""), "Command"),
                "detail": f"{verb} · command {_short_id(command_id)}",
                "status": _ui_status_for_command(getattr(command, "status", "")),
                "kind": "command",
                "lane": "commands",
                "defaultInspector": "trace",
                "metadata": {
                    "command_id": command_id,
                    "client_draft_id": getattr(command, "client_draft_id", None),
                    "origin_surface": getattr(command, "origin_surface", None),
                    "actor": getattr(command, "actor", None),
                    "thread_id": getattr(command, "thread_id", None),
                    "context_objects": [
                        entry.model_dump(exclude_none=True)
                        if hasattr(entry, "model_dump")
                        else entry
                        for entry in list(getattr(command, "context_objects", []) or [])
                    ],
                    "requested_action": requested_action,
                    "write_mode": getattr(command, "write_mode", None),
                    "ledger_status": ledger_status,
                    "dispatch_status": metadata.get("dispatch_status"),
                    "dispatch_mode": metadata.get("dispatch_mode"),
                    "accepted_task_id": getattr(command, "accepted_task_id", None),
                    "meeting_orchestration": meeting_orchestration,
                    "meeting_orchestration_status": meeting_orchestration.get("status"),
                    "meeting_orchestration_error_code": meeting_orchestration.get("error_code"),
                    "task_ir_id": meeting_orchestration.get("task_ir_id"),
                    "artifact_landing_status": meeting_orchestration.get("artifact_landing_status"),
                    "review_state": meeting_orchestration.get("review_state"),
                    "review_reason": meeting_orchestration.get("review_reason"),
                    "recommended_actions": meeting_orchestration.get(
                        "recommended_actions"
                    ),
                    "producer_quality_gate": meeting_orchestration.get(
                        "producer_quality_gate"
                    ),
                    "request_contract_aol_metadata": meeting_orchestration.get(
                        "request_contract_aol_metadata"
                    ),
                    "updated_at": getattr(command, "updated_at", None),
                    "projection_source": "command_ledger",
                },
            }
        )
    return projection
