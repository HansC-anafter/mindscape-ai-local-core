"""PostgreSQL-backed dynamic host resource lanes."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from backend.app.services.stores.postgres_base import PostgresStoreBase

logger = logging.getLogger(__name__)

LANE_ID_PREFIX = "runner:"
DEFAULT_DYNAMIC_LANE_ID = "runner:vision_mlx_high"
DEFAULT_DYNAMIC_QUEUE_SHARD = "vision_mlx_high"
DEFAULT_MAX_CONCURRENCY = 1
LANE_REQUIRED_FIELDS = (
    "lane_id",
    "capability_scope",
    "label",
    "kind",
    "queue_shard",
    "runner_profile",
    "resource_class",
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _clean_string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _clean_required_string(payload: dict[str, Any], key: str) -> str:
    value = _clean_string(payload.get(key))
    if not value:
        raise ValueError(f"{key}_required")
    return value


def _clean_int(value: Any, *, default: int, minimum: int = 0) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(minimum, parsed)


def _clean_json_object(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _normalize_lane_payload(payload: dict[str, Any], *, partial: bool = False) -> dict[str, Any]:
    source = dict(payload or {})
    normalized: dict[str, Any] = {}
    for key in LANE_REQUIRED_FIELDS:
        if key in source or not partial:
            normalized[key] = _clean_required_string(source, key)
    if "workspace_id" in source or not partial:
        normalized["workspace_id"] = _clean_string(source.get("workspace_id"))
    if "priority_class" in source or not partial:
        normalized["priority_class"] = _clean_string(source.get("priority_class")) or "default"
    if "resource_flavor" in source or not partial:
        normalized["resource_flavor"] = _clean_string(source.get("resource_flavor"))
    if "max_concurrency" in source or not partial:
        normalized["max_concurrency"] = _clean_int(
            source.get("max_concurrency"),
            default=DEFAULT_MAX_CONCURRENCY,
            minimum=1,
        )
    if "desired_worker_count" in source or not partial:
        normalized["desired_worker_count"] = _clean_int(
            source.get("desired_worker_count"),
            default=0,
            minimum=0,
        )
    if "model_profile" in source or not partial:
        normalized["model_profile"] = _clean_json_object(source.get("model_profile"))
    if "state" in source or not partial:
        normalized["state"] = _clean_string(source.get("state")) or "available"
    if "metadata" in source or not partial:
        normalized["metadata"] = _clean_json_object(source.get("metadata"))
    if (
        normalized.get("desired_worker_count") is not None
        and normalized.get("max_concurrency") is not None
        and normalized["desired_worker_count"] > normalized["max_concurrency"]
    ):
        raise ValueError("desired_worker_count_exceeds_max_concurrency")
    return normalized


def _row_to_lane(row: Any, store: PostgresStoreBase | None = None) -> dict[str, Any]:
    mapping = dict(row._mapping) if hasattr(row, "_mapping") else dict(row or {})
    helper = store or PostgresStoreBase("core")
    model_profile = helper.deserialize_json(mapping.get("model_profile"), default={})
    metadata = helper.deserialize_json(mapping.get("metadata"), default={})
    lane = {
        "lane_id": mapping.get("lane_id"),
        "workspace_id": mapping.get("workspace_id"),
        "capability_scope": mapping.get("capability_scope"),
        "label": mapping.get("label"),
        "kind": mapping.get("kind"),
        "queue_shard": mapping.get("queue_shard"),
        "runner_profile": mapping.get("runner_profile"),
        "resource_class": mapping.get("resource_class"),
        "priority_class": mapping.get("priority_class") or "default",
        "resource_flavor": mapping.get("resource_flavor"),
        "max_concurrency": _clean_int(mapping.get("max_concurrency"), default=1, minimum=1),
        "desired_worker_count": _clean_int(
            mapping.get("desired_worker_count"),
            default=0,
            minimum=0,
        ),
        "model_profile": model_profile,
        "state": mapping.get("state") or "available",
        "metadata": metadata,
        "created_at": mapping.get("created_at").isoformat()
        if hasattr(mapping.get("created_at"), "isoformat")
        else mapping.get("created_at"),
        "updated_at": mapping.get("updated_at").isoformat()
        if hasattr(mapping.get("updated_at"), "isoformat")
        else mapping.get("updated_at"),
    }
    requirements = dict(metadata.get("requirements") or {})
    requirements.setdefault("memory_mb", 0)
    requirements.setdefault("memory_source", "dynamic_lane_config")
    requirements.setdefault("cpu_weight", 1)
    requirements.setdefault("exclusive_groups", [lane["queue_shard"]])
    if lane.get("resource_flavor"):
        requirements.setdefault("resource_flavor", lane["resource_flavor"])
    lane["requirements"] = requirements
    return lane


class HostResourceDynamicLaneStore(PostgresStoreBase):
    """Durable store for workspace and capability-scoped host resource lanes."""

    def list_lanes(self) -> list[dict[str, Any]]:
        try:
            with self.get_connection() as conn:
                rows = conn.execute(
                    text(
                        """
                        SELECT *
                        FROM host_resource_lanes
                        ORDER BY capability_scope, workspace_id NULLS FIRST, lane_id
                        """
                    )
                ).fetchall()
        except Exception as exc:
            logger.debug("Dynamic host resource lanes unavailable: %s", exc)
            return []
        return [_row_to_lane(row, self) for row in rows]

    def get_lane(self, lane_id: str) -> dict[str, Any] | None:
        normalized_lane_id = _clean_string(lane_id)
        if not normalized_lane_id:
            return None
        try:
            with self.get_connection() as conn:
                row = conn.execute(
                    text("SELECT * FROM host_resource_lanes WHERE lane_id = :lane_id"),
                    {"lane_id": normalized_lane_id},
                ).fetchone()
        except Exception as exc:
            logger.debug("Dynamic host resource lane lookup unavailable: %s", exc)
            return None
        return _row_to_lane(row, self) if row else None

    def create_lane(self, payload: dict[str, Any]) -> dict[str, Any]:
        lane = _normalize_lane_payload(payload)
        now = _utc_now()
        lane["created_at"] = now
        lane["updated_at"] = now
        with self.transaction() as conn:
            row = conn.execute(
                text(
                    """
                    INSERT INTO host_resource_lanes (
                        lane_id, workspace_id, capability_scope, label, kind,
                        queue_shard, runner_profile, resource_class, priority_class,
                        resource_flavor, max_concurrency, desired_worker_count,
                        model_profile, state, metadata, created_at, updated_at
                    ) VALUES (
                        :lane_id, :workspace_id, :capability_scope, :label, :kind,
                        :queue_shard, :runner_profile, :resource_class, :priority_class,
                        :resource_flavor, :max_concurrency, :desired_worker_count,
                        CAST(:model_profile AS JSONB), :state, CAST(:metadata AS JSONB),
                        :created_at, :updated_at
                    )
                    ON CONFLICT (lane_id) DO NOTHING
                    RETURNING *
                    """
                ),
                {
                    **lane,
                    "model_profile": self.serialize_json(lane["model_profile"]),
                    "metadata": self.serialize_json(lane["metadata"]),
                },
            ).fetchone()
        if not row:
            raise ValueError("duplicate_lane_id")
        return _row_to_lane(row, self)

    def update_lane(self, lane_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        normalized_lane_id = _clean_string(lane_id)
        if not normalized_lane_id:
            raise ValueError("lane_id_required")
        updates = _normalize_lane_payload(payload, partial=True)
        if not updates:
            return self.get_lane(normalized_lane_id)
        set_fragments: list[str] = []
        params: dict[str, Any] = {
            "lane_id": normalized_lane_id,
            "updated_at": _utc_now(),
        }
        for key, value in updates.items():
            if key == "lane_id":
                continue
            if key in {"model_profile", "metadata"}:
                set_fragments.append(f"{key} = CAST(:{key} AS JSONB)")
                params[key] = self.serialize_json(value)
            else:
                set_fragments.append(f"{key} = :{key}")
                params[key] = value
        set_fragments.append("updated_at = :updated_at")
        with self.transaction() as conn:
            row = conn.execute(
                text(
                    f"""
                    UPDATE host_resource_lanes
                    SET {", ".join(set_fragments)}
                    WHERE lane_id = :lane_id
                    RETURNING *
                    """
                ),
                params,
            ).fetchone()
        return _row_to_lane(row, self) if row else None

    def list_queue_shards(self) -> list[str]:
        shards: list[str] = []
        for lane in self.list_lanes():
            shard = _clean_string(lane.get("queue_shard"))
            if shard and shard not in shards:
                shards.append(shard)
        return shards


def _store() -> HostResourceDynamicLaneStore:
    return HostResourceDynamicLaneStore("core")


def list_dynamic_lanes() -> list[dict[str, Any]]:
    return _store().list_lanes()


def get_dynamic_lane(lane_id: str) -> dict[str, Any] | None:
    return _store().get_lane(lane_id)


def create_dynamic_lane(payload: dict[str, Any]) -> dict[str, Any]:
    return _store().create_lane(payload)


def update_dynamic_lane(lane_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    return _store().update_lane(lane_id, payload)


def list_dynamic_queue_shards() -> list[str]:
    return _store().list_queue_shards()
