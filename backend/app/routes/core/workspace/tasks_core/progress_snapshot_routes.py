"""Workspace execution progress snapshot route cache layer."""

import asyncio
import logging
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from fastapi import Path as PathParam
from fastapi.encoders import jsonable_encoder

from backend.app.routes.core.read_executor import run_ui_read
from backend.app.services.runner_resources import (
    PROGRESS_SNAPSHOT_TTL_SECONDS,
    RedisTtlSnapshotStore,
    build_progress_snapshot_key,
    build_progress_last_known_snapshot_key,
    get_ttl_snapshot,
    set_ttl_snapshot,
)
from backend.app.services.workspace_execution.lifecycle_summary import (
    attach_lifecycle_summary_to_progress_snapshot,
)
from backend.app.services.stores.redis.runner_queue_store import RedisRunnerQueueStore

from .progress_snapshot import load_execution_progress_snapshot_payload
from .progress_snapshot_contract import (
    PROGRESS_LAST_KNOWN_TTL_SECONDS,
    fresh_snapshot,
    stale_snapshot,
)
from backend.app.database.recovery_backoff import classify_database_error
from backend.app.services.runtime_database_incident_gate import record_database_failure

router = APIRouter()
logger = logging.getLogger(__name__)
_PROGRESS_SNAPSHOT_CACHE_TTL_SECONDS = float(PROGRESS_SNAPSHOT_TTL_SECONDS)
_PROGRESS_SNAPSHOT_CACHE: dict[tuple[str, str], tuple[float, Dict[str, Any]]] = {}
_PROGRESS_SNAPSHOT_LAST_KNOWN: dict[tuple[str, str], Dict[str, Any]] = {}
_PROGRESS_SNAPSHOT_INFLIGHT: dict[tuple[str, str], asyncio.Task[Dict[str, Any]]] = {}
_PROGRESS_SNAPSHOT_CACHE_LOCK = asyncio.Lock()
_PROGRESS_SNAPSHOT_STORE = RedisTtlSnapshotStore(
    RedisRunnerQueueStore(pack_id="progress_snapshot")
)


def _load_execution_progress_snapshot_payload(
    workspace_id: str,
    execution_id: str,
) -> Dict[str, Any]:
    payload = load_execution_progress_snapshot_payload(workspace_id, execution_id)
    return attach_lifecycle_summary_to_progress_snapshot(payload)


async def _read_progress_snapshot_hot_cache(
    workspace_id: str,
    execution_id: str,
) -> Optional[Dict[str, Any]]:
    try:
        return await get_ttl_snapshot(
            _PROGRESS_SNAPSHOT_STORE,
            build_progress_snapshot_key(workspace_id, execution_id),
        )
    except Exception:
        return None


async def _write_progress_snapshot_hot_cache(
    workspace_id: str,
    execution_id: str,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    encoded_payload = jsonable_encoder(payload)
    if not isinstance(encoded_payload, dict):
        return payload
    try:
        await set_ttl_snapshot(
            _PROGRESS_SNAPSHOT_STORE,
            build_progress_snapshot_key(workspace_id, execution_id),
            encoded_payload,
            ttl_seconds=PROGRESS_SNAPSHOT_TTL_SECONDS,
        )
    except Exception:
        pass
    return encoded_payload


async def _read_progress_snapshot_last_known(
    workspace_id: str,
    execution_id: str,
) -> Optional[Dict[str, Any]]:
    try:
        cached = await get_ttl_snapshot(
            _PROGRESS_SNAPSHOT_STORE,
            build_progress_last_known_snapshot_key(workspace_id, execution_id),
        )
        if cached:
            return cached
    except Exception:
        pass
    return _PROGRESS_SNAPSHOT_LAST_KNOWN.get((workspace_id, execution_id))


async def _write_progress_snapshot_last_known(
    workspace_id: str,
    execution_id: str,
    payload: Dict[str, Any],
) -> None:
    cache_key = (workspace_id, execution_id)
    _PROGRESS_SNAPSHOT_LAST_KNOWN[cache_key] = payload
    try:
        await set_ttl_snapshot(
            _PROGRESS_SNAPSHOT_STORE,
            build_progress_last_known_snapshot_key(workspace_id, execution_id),
            payload,
            ttl_seconds=PROGRESS_LAST_KNOWN_TTL_SECONDS,
        )
    except Exception:
        pass


@router.get("/{workspace_id}/executions/{execution_id}/progress-snapshot")
async def get_execution_progress_snapshot(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    execution_id: str = PathParam(..., description="Execution ID"),
) -> Dict[str, Any]:
    """Return a lightweight progress snapshot for one execution."""
    cache_key = (workspace_id, execution_id)
    try:
        hot_cached = await _read_progress_snapshot_hot_cache(
            workspace_id,
            execution_id,
        )
        if hot_cached:
            return hot_cached

        now = time.monotonic()
        async with _PROGRESS_SNAPSHOT_CACHE_LOCK:
            cached = _PROGRESS_SNAPSHOT_CACHE.get(cache_key)
            if cached and now - cached[0] < _PROGRESS_SNAPSHOT_CACHE_TTL_SECONDS:
                return cached[1]

            task = _PROGRESS_SNAPSHOT_INFLIGHT.get(cache_key)
            if task is None:
                task = asyncio.create_task(
                    run_ui_read(
                        _load_execution_progress_snapshot_payload,
                        workspace_id,
                        execution_id,
                    )
                )
                _PROGRESS_SNAPSHOT_INFLIGHT[cache_key] = task

        payload = fresh_snapshot(await task)
        payload = await _write_progress_snapshot_hot_cache(
            workspace_id,
            execution_id,
            payload,
        )

        async with _PROGRESS_SNAPSHOT_CACHE_LOCK:
            if _PROGRESS_SNAPSHOT_INFLIGHT.get(cache_key) is task:
                _PROGRESS_SNAPSHOT_INFLIGHT.pop(cache_key, None)
            _PROGRESS_SNAPSHOT_CACHE[cache_key] = (time.monotonic(), payload)

        await _write_progress_snapshot_last_known(
            workspace_id,
            execution_id,
            payload,
        )

        return payload
    except HTTPException:
        async with _PROGRESS_SNAPSHOT_CACHE_LOCK:
            _PROGRESS_SNAPSHOT_INFLIGHT.pop(cache_key, None)
        raise
    except Exception as exc:
        async with _PROGRESS_SNAPSHOT_CACHE_LOCK:
            _PROGRESS_SNAPSHOT_INFLIGHT.pop(cache_key, None)
        classification = classify_database_error(exc)
        incident_id = None
        if classification.opens_incident:
            try:
                incident = record_database_failure(classification.code.value)
                incident_id = getattr(incident, "incident_id", None)
            except Exception:
                logger.exception("Failed to persist progress database incident")
        logger.error(
            "Progress snapshot refresh failed: execution_id=%s code=%s incident_id=%s",
            execution_id,
            classification.code.value,
            incident_id,
            exc_info=True,
        )
        last_known = await _read_progress_snapshot_last_known(
            workspace_id,
            execution_id,
        )
        if last_known:
            return stale_snapshot(
                last_known,
                degraded_reason="postgres_unavailable",
            )
        raise HTTPException(
            status_code=503,
            detail={
                "error_code": "runtime_database_unavailable",
                "retry_after_seconds": 30,
                "incident_id": incident_id,
            },
            headers={"Retry-After": "30"},
        )
