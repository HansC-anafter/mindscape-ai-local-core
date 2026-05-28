"""Redis projection for queue-ready task route identity."""

from __future__ import annotations

import json
from typing import Any

from backend.app.services.cache.redis_cache import get_cache_service

from . import route_gate


ROUTE_IDENTITY_TTL_SECONDS = 24 * 60 * 60
ROUTE_IDENTITY_KEY_PREFIX = "mindscape:host_resources:route_identity:"


def route_identity_key(task_id: str) -> str:
    return f"{ROUTE_IDENTITY_KEY_PREFIX}{str(task_id).strip()}"


def _ctx(task: Any) -> dict[str, Any]:
    ctx = getattr(task, "execution_context", None)
    return ctx if isinstance(ctx, dict) else {}


def build_route_identity_projection(task: Any) -> dict[str, Any]:
    ctx = _ctx(task)
    task_id = str(getattr(task, "id", None) or ctx.get("task_id") or "").strip()
    pack_id = str(getattr(task, "pack_id", None) or ctx.get("pack_id") or ctx.get("playbook_code") or "").strip() or None
    playbook_code = str(ctx.get("playbook_code") or pack_id or "").strip() or None
    status = getattr(task, "status", None)
    return {
        "task_id": task_id,
        "pack_id": pack_id,
        "playbook_code": playbook_code,
        "task_type": str(getattr(task, "task_type", None) or ctx.get("task_type") or "").strip() or None,
        "workspace_id": str(getattr(task, "workspace_id", None) or ctx.get("workspace_id") or "").strip() or None,
        "queue_shard": str(getattr(task, "queue_shard", None) or ctx.get("queue_shard") or "").strip() or None,
        "concurrency_key": str(getattr(task, "concurrency_key", None) or ctx.get("concurrency_key") or "").strip() or None,
        "blocked_reason": str(getattr(task, "blocked_reason", None) or ctx.get("blocked_reason") or "").strip() or None,
        "status": str(getattr(status, "value", status) or "").strip() or None,
        "route_identity": route_gate.task_route_identity(task),
    }


def normalize_route_identity_projection(
    task_id: str,
    projection: dict[str, Any] | None,
) -> dict[str, Any]:
    normalized = dict(projection or {})
    normalized.setdefault("task_id", str(task_id).strip())
    identity = normalized.get("route_identity")
    if not isinstance(identity, dict):
        identity = {
            "lane_id": normalized.get("lane_id"),
            "resource_groups": normalized.get("resource_groups") or [],
            "priority_class": normalized.get("priority_class") or "default",
            "resource_flavor": normalized.get("resource_flavor"),
        }
    normalized["route_identity"] = identity
    return normalized


def serialize_route_identity_projection(task_id: str, projection: dict[str, Any] | None) -> str:
    return json.dumps(
        normalize_route_identity_projection(task_id, projection),
        separators=(",", ":"),
        sort_keys=True,
    )


def decode_route_identity_projection(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode()
    if isinstance(raw, dict):
        return normalize_route_identity_projection(str(raw.get("task_id") or ""), raw)
    try:
        data = json.loads(str(raw))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    return normalize_route_identity_projection(str(data.get("task_id") or ""), data)


def write_route_identity_projection_sync(
    task_id: str,
    projection: dict[str, Any] | None,
    *,
    ttl_seconds: int = ROUTE_IDENTITY_TTL_SECONDS,
) -> bool:
    cache = get_cache_service()
    if not cache._ensure_connected() or not cache._client:
        return False
    cache._client.setex(
        route_identity_key(task_id),
        max(60, int(ttl_seconds or ROUTE_IDENTITY_TTL_SECONDS)),
        serialize_route_identity_projection(task_id, projection),
    )
    return True


async def write_route_identity_projection_async(
    client: Any,
    task_id: str,
    projection: dict[str, Any] | None,
    *,
    ttl_seconds: int = ROUTE_IDENTITY_TTL_SECONDS,
) -> bool:
    if not client:
        return False
    await client.setex(
        route_identity_key(task_id),
        max(60, int(ttl_seconds or ROUTE_IDENTITY_TTL_SECONDS)),
        serialize_route_identity_projection(task_id, projection),
    )
    return True


async def read_route_identity_projections(
    client: Any,
    task_ids: list[str],
) -> dict[str, dict[str, Any]]:
    normalized_ids = [str(task_id).strip() for task_id in task_ids if str(task_id).strip()]
    if not client or not normalized_ids:
        return {}
    raw_values = await client.mget([route_identity_key(task_id) for task_id in normalized_ids])
    result: dict[str, dict[str, Any]] = {}
    for task_id, raw in zip(normalized_ids, raw_values):
        projection = decode_route_identity_projection(raw)
        if projection is not None:
            result[task_id] = normalize_route_identity_projection(task_id, projection)
    return result


async def delete_route_identity_projection(client: Any, task_id: str) -> bool:
    if not client:
        return False
    await client.delete(route_identity_key(task_id))
    return True
