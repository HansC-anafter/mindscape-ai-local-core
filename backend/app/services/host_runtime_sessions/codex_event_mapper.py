"""Map host app-server events into Mindscape host runtime events."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .models import CANONICAL_EVENT_TYPES, TOKEN_DELTA_EVENT_TYPES


class MappedHostRuntimeEvent(BaseModel):
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    item_id: str | None = None
    persist: bool = True


def _raw_type(raw_event: dict[str, Any]) -> str:
    return str(
        raw_event.get("type")
        or raw_event.get("event")
        or raw_event.get("event_type")
        or ""
    ).strip()


def _payload(raw_event: dict[str, Any]) -> dict[str, Any]:
    payload = raw_event.get("payload")
    if isinstance(payload, dict):
        return dict(payload)
    return {
        key: value
        for key, value in raw_event.items()
        if key not in {"type", "event", "event_type"}
    }


def map_codex_app_server_event(raw_event: dict[str, Any]) -> MappedHostRuntimeEvent:
    """Translate a raw app-server event into the canonical Mindscape contract.

    The mapper is deliberately tolerant about upstream names so protocol churn
    is absorbed here instead of leaking into frontend components.
    """

    raw_type = _raw_type(raw_event)
    normalized = raw_type.lower().replace(":", ".").replace("/", ".")
    payload = _payload(raw_event)
    item_id = (
        payload.get("item_id")
        or payload.get("id")
        or raw_event.get("item_id")
        or raw_event.get("id")
    )

    event_type = "item.started"
    if normalized in CANONICAL_EVENT_TYPES:
        event_type = normalized
    elif "approval" in normalized and any(token in normalized for token in ("request", "requested")):
        event_type = "approval.requested"
    elif "approval" in normalized and "denied" in normalized:
        event_type = "approval.denied"
    elif "approval" in normalized and "approved" in normalized:
        event_type = "approval.approved"
    elif "patch" in normalized and any(token in normalized for token in ("proposed", "proposal")):
        event_type = "patch.proposed"
    elif "file" in normalized and any(token in normalized for token in ("changed", "change")):
        event_type = "file.changed"
    elif "tool" in normalized and any(token in normalized for token in ("delta", "output")):
        event_type = "tool.output.delta"
    elif "tool" in normalized and any(token in normalized for token in ("completed", "done", "finished")):
        event_type = "tool.completed"
    elif "tool" in normalized:
        event_type = "tool.started"
    elif any(token in normalized for token in ("message.completed", "assistant.completed")):
        event_type = "assistant.message.completed"
    elif any(token in normalized for token in ("delta", "output_text.delta", "assistant.delta")):
        event_type = "assistant.delta"
    elif any(token in normalized for token in ("turn.completed", "response.completed", "completed")):
        event_type = "turn.completed"
    elif any(token in normalized for token in ("turn.failed", "response.failed", "failed", "error")):
        event_type = "turn.failed"

    return MappedHostRuntimeEvent(
        event_type=event_type,
        payload={
            **payload,
            "raw_event_type": raw_type,
        },
        item_id=str(item_id) if item_id else None,
        persist=event_type not in TOKEN_DELTA_EVENT_TYPES,
    )
