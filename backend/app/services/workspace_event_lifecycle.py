"""Committed workspace event to bounded CloudEvents Redis fan-out mapping."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict

from backend.app.services.cache.redis_cache import get_cache_service


logger = logging.getLogger(__name__)
MAX_WORKSPACE_EVENT_BYTES = 150_000
WORKSPACE_EVENT_DATASCHEMA = "mindscape.workspace.mind_event.v1"


def workspace_event_channel(workspace_id: str) -> str:
    return f"workspace:{workspace_id}:events:v1"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _enum_value(value: Any) -> str:
    return _text(value.value if hasattr(value, "value") else value)


def _event_time(value: Any) -> str:
    if not isinstance(value, datetime):
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


def _payload_checksum(payload: Dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def serialize_mind_event_cloud_event(event: Any) -> Dict[str, Any]:
    workspace_id = _text(getattr(event, "workspace_id", ""))
    event_id = _text(getattr(event, "id", ""))
    event_type = _enum_value(getattr(event, "event_type", "unknown"))
    metadata = getattr(event, "metadata", {})
    metadata = dict(metadata) if isinstance(metadata, dict) else {}
    aggregate_id = (
        _text(metadata.get("aggregate_id"))
        or _text(getattr(event, "thread_id", ""))
        or event_id
    )
    try:
        aggregate_version = max(int(metadata.get("aggregate_version") or 1), 1)
    except (TypeError, ValueError):
        aggregate_version = 1
    domain_data = {
        "id": event_id,
        "event_type": event_type,
        "timestamp": _event_time(getattr(event, "timestamp", None)),
        "actor": _enum_value(getattr(event, "actor", "system")),
        "channel": _text(getattr(event, "channel", "")),
        "workspace_id": workspace_id,
        "project_id": getattr(event, "project_id", None),
        "profile_id": getattr(event, "profile_id", None),
        "thread_id": getattr(event, "thread_id", None),
        "payload": getattr(event, "payload", {})
        if isinstance(getattr(event, "payload", {}), dict)
        else {},
        "entity_ids": getattr(event, "entity_ids", [])
        if isinstance(getattr(event, "entity_ids", []), list)
        else [],
        "metadata": metadata,
    }
    checksum = _payload_checksum(domain_data)
    source = f"mindscape://local-core/workspace/{workspace_id}/mind-events"
    return {
        "specversion": "1.0",
        "id": event_id,
        "source": source,
        "type": f"mindscape.workspace.{event_type}.v1",
        "subject": f"mind_event:{event_id}",
        "time": domain_data["timestamp"],
        "datacontenttype": "application/json",
        "dataschema": WORKSPACE_EVENT_DATASCHEMA,
        "aggregateid": aggregate_id,
        "aggregateversion": aggregate_version,
        "causationid": _text(metadata.get("causation_id")),
        "correlationid": _text(metadata.get("correlation_id")),
        "ownerref": source,
        "workspaceid": workspace_id,
        "payloadchecksum": checksum,
        "data": domain_data,
    }


def validate_workspace_lifecycle_event(
    payload: Any,
    *,
    workspace_id: str,
) -> Dict[str, Any]:
    event = dict(payload) if isinstance(payload, dict) else {}
    required = ("specversion", "id", "source", "type", "workspaceid", "data")
    if any(not event.get(field) for field in required):
        raise ValueError("workspace_lifecycle_event_required_attribute_missing")
    if event.get("specversion") != "1.0":
        raise ValueError("workspace_lifecycle_event_specversion_unsupported")
    if event.get("workspaceid") != workspace_id:
        raise ValueError("workspace_lifecycle_event_workspace_mismatch")
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    if event.get("payloadchecksum") != _payload_checksum(data):
        raise ValueError("workspace_lifecycle_event_checksum_mismatch")
    encoded = json.dumps(event, ensure_ascii=False, default=str).encode("utf-8")
    if len(encoded) >= MAX_WORKSPACE_EVENT_BYTES:
        raise ValueError("workspace_lifecycle_event_payload_too_large")
    return event


def publish_committed_workspace_event(event: Any) -> bool:
    workspace_id = _text(getattr(event, "workspace_id", ""))
    if not workspace_id:
        return False
    try:
        payload = serialize_mind_event_cloud_event(event)
        validate_workspace_lifecycle_event(payload, workspace_id=workspace_id)
    except (TypeError, ValueError) as exc:
        logger.warning(
            "Committed workspace event is not eligible for live fan-out "
            "workspace=%s event=%s reason=%s",
            workspace_id[:8],
            _text(getattr(event, "id", ""))[:8],
            exc,
        )
        return False
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    published = get_cache_service().publish(
        workspace_event_channel(workspace_id),
        encoded,
    )
    if not published:
        logger.warning(
            "Committed workspace event fan-out unavailable workspace=%s event=%s",
            workspace_id[:8],
            _text(getattr(event, "id", ""))[:8],
        )
    return published


__all__ = [
    "MAX_WORKSPACE_EVENT_BYTES",
    "publish_committed_workspace_event",
    "serialize_mind_event_cloud_event",
    "validate_workspace_lifecycle_event",
    "workspace_event_channel",
]
