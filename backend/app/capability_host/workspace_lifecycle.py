"""Public transaction-compatible workspace lifecycle contract for capabilities."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping

from sqlalchemy import text

try:  # Installed packs import the public ``app`` namespace.
    from app.services.workspace_event_lifecycle import (
        publish_committed_workspace_cloud_event as _publish_committed_event,
        validate_workspace_lifecycle_event,
        workspace_event_payload_checksum,
    )
except ModuleNotFoundError:  # Source tests import through ``backend.app``.
    from backend.app.services.workspace_event_lifecycle import (
        publish_committed_workspace_cloud_event as _publish_committed_event,
        validate_workspace_lifecycle_event,
        workspace_event_payload_checksum,
    )


WORKSPACE_EVENT_ID_MAX_LENGTH = 36
_REQUIRED_EXTENSIONS = (
    "aggregateid",
    "aggregateversion",
    "ownerref",
    "workspaceid",
    "payloadchecksum",
)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _json_object(value: Any, *, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"workspace_lifecycle_event_{field}_object_required")
    try:
        return json.loads(_canonical_json(dict(value)))
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"workspace_lifecycle_event_{field}_json_required"
        ) from exc


def _event_time(value: Any) -> str:
    if value in (None, ""):
        resolved = datetime.now(timezone.utc)
    elif isinstance(value, datetime):
        resolved = value
    elif isinstance(value, str):
        try:
            resolved = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("workspace_lifecycle_event_time_invalid") from exc
    else:
        raise ValueError("workspace_lifecycle_event_time_invalid")
    if resolved.tzinfo is None:
        resolved = resolved.replace(tzinfo=timezone.utc)
    return resolved.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def workspace_cloud_event_checksum(event: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(dict(event)).encode("utf-8")).hexdigest()


def normalize_workspace_cloud_event(event: Mapping[str, Any]) -> dict[str, Any]:
    normalized = _json_object(event, field="envelope")
    data = _json_object(normalized.get("data"), field="data")
    normalized["data"] = data
    for field in ("specversion", "id", "source", "type", *_REQUIRED_EXTENSIONS):
        if normalized.get(field) in (None, ""):
            raise ValueError(
                "workspace_lifecycle_event_required_attribute_missing"
            )
    event_id = str(normalized["id"]).strip()
    if not event_id or len(event_id) > WORKSPACE_EVENT_ID_MAX_LENGTH:
        raise ValueError("workspace_lifecycle_event_id_invalid")
    normalized["id"] = event_id
    normalized["source"] = str(normalized["source"]).strip()
    normalized["type"] = str(normalized["type"]).strip()
    normalized["workspaceid"] = str(normalized["workspaceid"]).strip()
    normalized["aggregateid"] = str(normalized["aggregateid"]).strip()
    normalized["ownerref"] = str(normalized["ownerref"]).strip()
    try:
        aggregate_version = int(normalized["aggregateversion"])
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "workspace_lifecycle_event_aggregate_version_invalid"
        ) from exc
    if isinstance(normalized["aggregateversion"], bool) or aggregate_version <= 0:
        raise ValueError("workspace_lifecycle_event_aggregate_version_invalid")
    normalized["aggregateversion"] = aggregate_version
    if normalized.get("time") not in (None, ""):
        normalized["time"] = _event_time(normalized["time"])
    else:
        normalized.pop("time", None)
    normalized.setdefault("datacontenttype", "application/json")
    if normalized["datacontenttype"] != "application/json":
        raise ValueError("workspace_lifecycle_event_content_type_invalid")
    expected_checksum = workspace_event_payload_checksum(data)
    if normalized["payloadchecksum"] != expected_checksum:
        raise ValueError("workspace_lifecycle_event_checksum_mismatch")
    validate_workspace_lifecycle_event(
        normalized,
        workspace_id=normalized["workspaceid"],
    )
    return normalized


def _storage_metadata(event: Mapping[str, Any]) -> dict[str, Any]:
    envelope = {key: value for key, value in event.items() if key != "data"}
    return {
        "workspace_cloud_event": envelope,
        "workspace_cloud_event_checksum": workspace_cloud_event_checksum(event),
    }


def _decode_json(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value


async def append_workspace_cloud_event(
    session: Any,
    event: Mapping[str, Any],
) -> dict[str, Any]:
    """Append through the caller transaction without owning commit or fan-out."""
    normalized = normalize_workspace_cloud_event(event)
    event_id = normalized["id"]
    workspace_id = normalized["workspaceid"]
    metadata = _storage_metadata(normalized)
    result = await session.execute(
        text(
            """
            INSERT INTO mind_events (
                id, timestamp, actor, channel, profile_id, project_id,
                workspace_id, thread_id, event_type, payload, entity_ids, metadata
            )
            SELECT
                :event_id, :occurred_at, 'system', 'capability_host',
                workspaces.owner_user_id, NULL, workspaces.id, NULL,
                'capability_event', :payload, '[]', :metadata
            FROM workspaces
            WHERE workspaces.id = :workspace_id
            ON CONFLICT (id) DO NOTHING
            RETURNING id
            """
        ),
        {
            "event_id": event_id,
            "occurred_at": (
                datetime.fromisoformat(normalized["time"].replace("Z", "+00:00"))
                if normalized.get("time")
                else datetime.now(timezone.utc)
            ),
            "workspace_id": workspace_id,
            "payload": _canonical_json(normalized["data"]),
            "metadata": _canonical_json(metadata),
        },
    )
    inserted_id = result.scalar_one_or_none()
    if inserted_id:
        status = "inserted"
    else:
        existing_result = await session.execute(
            text(
                """
                SELECT workspace_id, payload, metadata
                FROM mind_events
                WHERE id = :event_id
                """
            ),
            {"event_id": event_id},
        )
        row = existing_result.mappings().first()
        if row is None:
            raise ValueError("workspace_lifecycle_workspace_not_found")
        existing_metadata = _decode_json(row["metadata"])
        existing_payload = _decode_json(row["payload"])
        envelope = (
            existing_metadata.get("workspace_cloud_event")
            if isinstance(existing_metadata, dict)
            else None
        )
        if not isinstance(envelope, dict) or not isinstance(existing_payload, dict):
            raise ValueError("workspace_lifecycle_event_id_collision")
        existing_event = normalize_workspace_cloud_event(
            {**envelope, "data": existing_payload}
        )
        if (
            str(row["workspace_id"] or "") != workspace_id
            or workspace_cloud_event_checksum(existing_event)
            != workspace_cloud_event_checksum(normalized)
        ):
            raise ValueError("workspace_lifecycle_event_id_collision")
        status = "existing"
    return {
        "status": status,
        "event_id": event_id,
        "workspace_id": workspace_id,
        "payload_checksum": normalized["payloadchecksum"],
        "event_checksum": workspace_cloud_event_checksum(normalized),
    }


def publish_committed_workspace_cloud_event(event: Mapping[str, Any]) -> bool:
    """Fan out only after the caller has successfully committed its transaction."""
    return _publish_committed_event(normalize_workspace_cloud_event(event))


__all__ = [
    "WORKSPACE_EVENT_ID_MAX_LENGTH",
    "append_workspace_cloud_event",
    "normalize_workspace_cloud_event",
    "publish_committed_workspace_cloud_event",
    "workspace_cloud_event_checksum",
    "workspace_event_payload_checksum",
]
