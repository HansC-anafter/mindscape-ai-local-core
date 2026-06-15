"""Runner reaper — cleans up stale tasks and orphaned locks."""

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import text

from backend.app.models.workspace import Task, TaskStatus
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.stores.tasks_store import TasksStore
from backend.app.services.stores.redis.runner_queue_store import RedisRunnerQueueStore
from backend.app.services.task_admission_service import (
    ADMISSION_DEFERRED_REASON,
    TASK_ADMISSION_SERVICE,
)
from backend.app.services.runner_resources import (
    RESOURCE_WAIT_REASON,
    ResourceRequirements,
    resource_lease_keys_from_context,
)
from backend.app.services.runner_live_state import RunnerLiveStateStore
from backend.app.services.host_resources.workspace_quota_admission import (
    WORKSPACE_ALLOCATION_DISABLED_REASON,
    WORKSPACE_ALLOCATION_REQUIRED_REASON,
    WORKSPACE_QUOTA_EXHAUSTED_REASON,
    decide_workspace_quota_admission_for_task,
)
from backend.app.services.host_resources.route_identity_projection import (
    build_route_identity_projection,
    read_route_identity_projections,
)

from backend.app.runner.concurrency import _resolve_lock_keys
from backend.app.runner.database_backoff import is_database_recovery_error
from backend.app.runner.lifecycle_hooks import _invoke_on_fail_hook_sync
from backend.app.runner.redis_transport_repair import (
    TERMINAL_TASK_STATUSES,
    normalize_task_id as _normalize_transport_task_id,
    reconcile_transport_membership,
    recycle_visibility_timeout_item,
    resolve_transport_queue_store,
    task_is_runnable_pending,
)
from backend.app.runner.utils import _env_int, _parse_utc_iso, _utc_now

logger = logging.getLogger(__name__)

_CONCURRENCY_LOCKED_REASON = "concurrency_locked"
_DEPENDENCY_HOLD_REASON = "dependency_hold"
_RESOURCE_WAIT_REASON = RESOURCE_WAIT_REASON
_WORKSPACE_QUOTA_EXHAUSTED_REASON = WORKSPACE_QUOTA_EXHAUSTED_REASON
_WORKSPACE_ALLOCATION_REQUIRED_REASON = WORKSPACE_ALLOCATION_REQUIRED_REASON
_WORKSPACE_ALLOCATION_DISABLED_REASON = WORKSPACE_ALLOCATION_DISABLED_REASON
_WORKSPACE_QUOTA_RELEASE_REASONS = frozenset(
    {
        _WORKSPACE_QUOTA_EXHAUSTED_REASON,
        _WORKSPACE_ALLOCATION_REQUIRED_REASON,
        _WORKSPACE_ALLOCATION_DISABLED_REASON,
    }
)
_BROWSER_LOCAL_QUEUE_SHARD = "browser_local"
_BROWSER_PEER_FRONTIER_LANES = frozenset(
    {
        "ig_batch_pin_references",
        "ig_pin_post_detail",
    }
)


def _task_runner_id(task: Task, ctx: dict[str, Any]) -> Optional[str]:
    runner_id = getattr(task, "runner_id", None)
    if isinstance(runner_id, str) and runner_id.strip():
        return runner_id.strip()
    raw_runner_id = ctx.get("runner_id")
    if isinstance(raw_runner_id, str) and raw_runner_id.strip():
        return raw_runner_id.strip()
    return None


def _task_heartbeat_at(task: Task, ctx: dict[str, Any]) -> Optional[datetime]:
    heartbeat_at = getattr(task, "heartbeat_at", None)
    if isinstance(heartbeat_at, datetime):
        return heartbeat_at
    return _parse_utc_iso(ctx.get("heartbeat_at"))


def _live_task_heartbeat_at(
    task_id: str,
    live_state_store: Optional[RunnerLiveStateStore] = None,
) -> Optional[datetime]:
    try:
        live_state = live_state_store or RunnerLiveStateStore()
        payload = live_state.get_task_heartbeat(task_id)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return _parse_utc_iso(payload.get("heartbeat_at"))


def _effective_task_heartbeat_at(
    task: Task,
    ctx: dict[str, Any],
    live_state_store: Optional[RunnerLiveStateStore] = None,
) -> Optional[datetime]:
    live_heartbeat_at = _live_task_heartbeat_at(task.id, live_state_store)
    if live_heartbeat_at is not None:
        return live_heartbeat_at
    return _task_heartbeat_at(task, ctx)


def _heartbeat_log_value(heartbeat_at: Optional[datetime], ctx: dict[str, Any]) -> Any:
    if isinstance(heartbeat_at, datetime):
        return heartbeat_at.isoformat()
    return ctx.get("heartbeat_at")


def _blocked_release_limit(ready_target: int, ready_depth: int) -> int:
    capacity_limit = max(0, ready_target - ready_depth)
    floor_limit = max(
        0,
        _env_int("LOCAL_CORE_RUNNER_BLOCKED_RELEASE_MINIMUM", 4),
    )
    return max(capacity_limit, floor_limit)


def _browser_peer_frontier_refill_limit() -> int:
    return max(0, _env_int("LOCAL_CORE_RUNNER_BROWSER_PEER_REFILL_LIMIT", 4))


def _resource_wait_keys_from_context(ctx: dict[str, Any]) -> list[str]:
    keys = resource_lease_keys_from_context(ctx)
    admission = ctx.get("resource_admission")
    if isinstance(admission, dict):
        for field_name in ("resource_keys", "lease_keys"):
            raw_keys = admission.get(field_name)
            if isinstance(raw_keys, list):
                keys.extend(str(key).strip() for key in raw_keys if str(key).strip())
        raw_key = admission.get("resource_key")
        if isinstance(raw_key, str) and raw_key.strip():
            keys.append(raw_key.strip())
    return list(dict.fromkeys(keys))


def _resource_wait_requirements_from_context(ctx: dict[str, Any]) -> Optional[ResourceRequirements]:
    admission = ctx.get("resource_admission")
    if not isinstance(admission, dict):
        return None
    raw_requirements = admission.get("requirements")
    if not isinstance(raw_requirements, dict):
        return None
    try:
        base = ResourceRequirements()
        return ResourceRequirements(
            browser_contexts=int(raw_requirements.get("browser_contexts") or base.browser_contexts),
            ig_profile_lock=raw_requirements.get("ig_profile_lock") or base.ig_profile_lock,
            cpu_weight=int(raw_requirements.get("cpu_weight") or base.cpu_weight),
            memory_mb=int(raw_requirements.get("memory_mb") or base.memory_mb),
            vision_lane=raw_requirements.get("vision_lane") or base.vision_lane,
            llm_lane=raw_requirements.get("llm_lane") or base.llm_lane,
            db_write_budget=raw_requirements.get("db_write_budget") or base.db_write_budget,
            expected_duration_class=raw_requirements.get("expected_duration_class") or base.expected_duration_class,
        )
    except Exception:
        return None


def _host_resource_wait_still_blocked(ctx: dict[str, Any]) -> Optional[Any]:
    requirements = _resource_wait_requirements_from_context(ctx)
    if requirements is None:
        return None
    try:
        from backend.app.services.host_resources import evaluate_runner_requirements

        advice = evaluate_runner_requirements(requirements)
        if advice is not None and not bool(getattr(advice, "allow", False)):
            return advice
    except Exception:
        return None
    return None


def _workspace_quota_payload(decision: Any) -> dict[str, Any]:
    to_dict = getattr(decision, "to_dict", None)
    if callable(to_dict):
        try:
            payload = to_dict()
            if isinstance(payload, dict):
                return payload
        except Exception:
            return {}
    payload: dict[str, Any] = {
        "allow": getattr(decision, "allow", None),
        "reason": getattr(decision, "reason", None),
        "active_count": getattr(decision, "active_count", None),
        "max_parallel_task_claims": getattr(decision, "max_parallel_task_claims", None),
    }
    allocation = getattr(decision, "allocation", None)
    if isinstance(allocation, dict):
        payload["allocation"] = allocation
    return {key: value for key, value in payload.items() if value is not None}


def _workspace_quota_allocation(decision: Any, payload: dict[str, Any]) -> dict[str, Any]:
    allocation = getattr(decision, "allocation", None)
    if isinstance(allocation, dict):
        return allocation
    payload_allocation = payload.get("allocation")
    return payload_allocation if isinstance(payload_allocation, dict) else {}


def _workspace_quota_task_selectors(allocation: dict[str, Any]) -> list[str]:
    metadata = allocation.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    selectors = metadata.get("task_selectors")
    if not isinstance(selectors, list):
        return []
    return [
        normalized
        for normalized in (str(selector).strip() for selector in selectors)
        if normalized
    ]


def _workspace_quota_release_key(task: Task, allocation: dict[str, Any]) -> str:
    allocation_id = str(allocation.get("allocation_id") or "").strip()
    if allocation_id:
        return allocation_id
    workspace_id = str(getattr(task, "workspace_id", "") or "").strip()
    queue_shard = str(getattr(task, "queue_shard", "") or "").strip()
    task_family = str(allocation.get("task_family") or "").strip()
    return f"{workspace_id}:{queue_shard}:{task_family}"


def _workspace_quota_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _is_stale_started_task(task: Task, threshold: datetime) -> bool:
    started_at = getattr(task, "started_at", None)
    return bool(started_at and started_at <= threshold)


def _emit_run_state_changed_for_task(
    task: Task,
    *,
    previous_state: str,
    new_state: str,
    reason: str,
) -> None:
    """Emit the workspace lifecycle event when reaper owns a terminal transition."""
    try:
        from backend.app.services.playbook_runner import _build_run_state_changed_event

        ctx = task.execution_context if isinstance(task.execution_context, dict) else {}
        inputs = None
        if isinstance(task.params, dict) and task.params:
            inputs = task.params
        elif isinstance(ctx.get("inputs"), dict):
            inputs = ctx.get("inputs")
        elif isinstance(task.params, dict):
            inputs = task.params
        event_inputs = inputs if isinstance(inputs, dict) else {}
        playbook_code = (
            event_inputs.get("playbook_code")
            or (ctx.get("playbook_code") if isinstance(ctx, dict) else None)
            or task.pack_id
            or ""
        )
        event = _build_run_state_changed_event(
            profile_id=(
                getattr(task, "profile_id", None)
                or (ctx.get("profile_id") if isinstance(ctx, dict) else None)
                or "default-user"
            ),
            project_id=task.project_id,
            workspace_id=task.workspace_id,
            execution_id=task.execution_id or str(task.id),
            previous_state=previous_state,
            new_state=new_state,
            reason=reason,
            playbook_code=playbook_code,
            inputs=inputs,
        )
        MindscapeStore().create_event(event)
    except Exception as emit_error:
        logger.warning(
            "Failed to emit %s RUN_STATE_CHANGED event for stale task %s (%s): %s",
            new_state,
            task.id,
            task.execution_id,
            emit_error,
        )


def _normalize_task_id(raw_value: object) -> str:
    return _normalize_transport_task_id(raw_value)


def _watchdog_pack_allowlist() -> set[str]:
    raw_value = str(
        os.getenv(
            "LOCAL_CORE_RUNNER_NO_PROGRESS_WATCHDOG_PACKS",
            "",
        )
        or ""
    )
    items = {item.strip() for item in raw_value.split(",") if item.strip()}
    return items


def _extract_artifact_semantic_progress_at(
    artifact: Any,
    *,
    expected_source: Optional[str],
) -> Optional[Any]:
    if artifact is None:
        return None

    metadata = getattr(artifact, "metadata", None)
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except Exception:
            metadata = None
    if isinstance(metadata, dict):
        source = str(metadata.get("source") or "").strip().lower()
        expected = str(expected_source or "").strip().lower()
        if expected and source != expected:
            return None

    content = getattr(artifact, "content", None)
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except Exception:
            content = None
    if not isinstance(content, dict):
        return None

    progress = content.get("progress") if isinstance(content.get("progress"), dict) else {}
    content_meta = content.get("metadata") if isinstance(content.get("metadata"), dict) else {}
    return (
        _parse_utc_iso(progress.get("semantic_progress_at"))
        or _parse_utc_iso(content_meta.get("semantic_progress_at"))
    )


def _normalize_watchdog_timestamp(value: Any) -> Optional[Any]:
    if value is None:
        return None
    if getattr(value, "tzinfo", None) is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _latest_watchdog_timestamp(*values: Any) -> Optional[Any]:
    latest = None
    for value in values:
        normalized = _normalize_watchdog_timestamp(value)
        if normalized is None:
            continue
        if latest is None or normalized > latest:
            latest = normalized
    return latest


def _resolve_watchdog_progress_updated_at(
    *,
    task: Any,
    execution: Any,
    execution_id: str,
    artifacts_store: Optional[Any],
    watchdog_policy: dict[str, Any],
) -> Optional[Any]:
    progress_updated_at = _latest_watchdog_timestamp(
        getattr(execution, "updated_at", None),
        getattr(execution, "created_at", None),
        getattr(task, "started_at", None),
        getattr(task, "created_at", None),
    )

    artifact_progress_source = str(
        watchdog_policy.get("artifact_progress_source") or ""
    ).strip()
    if not artifact_progress_source:
        return progress_updated_at
    if artifacts_store is None:
        return progress_updated_at

    try:
        artifact = artifacts_store.get_by_execution_id(execution_id)
    except Exception:
        return progress_updated_at

    semantic_progress_at = _extract_artifact_semantic_progress_at(
        artifact,
        expected_source=artifact_progress_source,
    )
    if semantic_progress_at is None:
        return progress_updated_at
    return _latest_watchdog_timestamp(progress_updated_at, semantic_progress_at)


def _watchdog_policy_from_context(ctx: dict[str, Any]) -> dict[str, Any]:
    raw_policy = ctx.get("no_progress_watchdog")
    if isinstance(raw_policy, dict):
        return dict(raw_policy)
    return {}


def _watchdog_policy_enabled(policy: dict[str, Any]) -> bool:
    value = policy.get("enabled")
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "off"}
    return bool(value)


def _request_watchdog_abort_for_no_progress_tasks(
    tasks_store: TasksStore,
    *,
    watcher_id: str,
    execution_store: Optional[Any] = None,
    artifacts_store: Optional[Any] = None,
) -> int:
    watchdog_seconds = _env_int("LOCAL_CORE_RUNNER_NO_PROGRESS_WATCHDOG_SECONDS", 900)
    if watchdog_seconds <= 0:
        return 0

    allowed_packs = _watchdog_pack_allowlist()

    try:
        running = tasks_store.list_running_playbook_execution_tasks(
            workspace_id=None, limit=500
        )
    except Exception as e:
        logger.warning("Runner no-progress watchdog scan failed: %s", e)
        return 0

    if execution_store is None:
        from backend.app.services.stores.postgres.remaining_stores import (
            PostgresPlaybookExecutionsStore,
        )

        execution_store = PostgresPlaybookExecutionsStore()

    now = _utc_now()
    stale_seconds = _env_int("LOCAL_CORE_RUNNER_STALE_TASK_SECONDS", 180)
    fresh_heartbeat_threshold = now - timedelta(seconds=max(stale_seconds, 60))
    progress_threshold = now - timedelta(seconds=watchdog_seconds)
    requested = 0

    for task in running:
        try:
            ctx = task.execution_context if isinstance(task.execution_context, dict) else {}
            watchdog_policy = _watchdog_policy_from_context(ctx)
            pack_id = str(task.pack_id or "").strip()
            if not (
                _watchdog_policy_enabled(watchdog_policy)
                or pack_id in allowed_packs
            ):
                continue
            if ctx.get("execution_mode") not in (None, "runner"):
                continue
            if ctx.get("watchdog_abort_requested_at"):
                continue
            if isinstance(ctx.get("watchdog_abort"), dict) and ctx["watchdog_abort"].get("requested_at"):
                continue

            heartbeat_at = _task_heartbeat_at(task, ctx)
            if not heartbeat_at or heartbeat_at <= fresh_heartbeat_threshold:
                continue

            try:
                current_step_index = int(ctx.get("current_step_index") or 0)
            except (TypeError, ValueError):
                current_step_index = 0
            if current_step_index > 0:
                continue

            execution_id = str(task.execution_id or task.id or "").strip()
            if not execution_id:
                continue
            execution = execution_store.get_execution(execution_id)
            if execution is None:
                continue

            phase = str(getattr(execution, "phase", "") or "").strip().lower()
            if phase not in ("", "queue"):
                continue

            if (
                artifacts_store is None
                and watchdog_policy.get("artifact_progress_source")
            ):
                from backend.app.services.stores.postgres.artifacts_store import (
                    PostgresArtifactsStore,
                )

                artifacts_store = PostgresArtifactsStore()

            progress_updated_at = _resolve_watchdog_progress_updated_at(
                task=task,
                execution=execution,
                execution_id=execution_id,
                artifacts_store=artifacts_store,
                watchdog_policy=watchdog_policy,
            )
            if progress_updated_at is None:
                continue
            if progress_updated_at > progress_threshold:
                continue

            reason = (
                "Runner no-progress watchdog tripped after "
                f"{watchdog_seconds}s (playbook={task.pack_id}, phase={phase or 'unknown'}, "
                f"current_step_index={current_step_index}, heartbeat_at={_heartbeat_log_value(heartbeat_at, ctx)}, "
                f"execution_updated_at={progress_updated_at.isoformat()})"
            )
            now_iso = now.isoformat()
            ctx2 = dict(ctx)
            ctx2["watchdog_abort_requested_at"] = now_iso
            ctx2["watchdog_abort_reason"] = reason
            ctx2["watchdog_abort"] = {
                "requested_at": now_iso,
                "reason": reason,
                "watcher_id": watcher_id,
                "threshold_seconds": watchdog_seconds,
                "phase": phase,
                "current_step_index": current_step_index,
                "heartbeat_at": _heartbeat_log_value(heartbeat_at, ctx),
                "execution_updated_at": progress_updated_at.isoformat(),
            }
            tasks_store.update_task(task.id, execution_context=ctx2)
            requested += 1
            logger.warning(
                "Requested watchdog abort for stalled runner task task_id=%s playbook=%s execution_id=%s",
                task.id,
                task.pack_id,
                execution_id,
            )
        except Exception as e:
            logger.warning(
                "Runner no-progress watchdog failed for task %s: %s",
                getattr(task, "id", "?"),
                e,
            )

    return requested


async def _mark_frontier_ready(
    tasks_store: TasksStore,
    task_ids: list[str],
    *,
    queue_shard: str,
) -> None:
    """Mirror Redis ready-enqueue into DB scheduler fields for observability."""
    if not task_ids:
        return

    enqueued_at = _utc_now()
    for task_id in task_ids:
        try:
            await asyncio.to_thread(
                tasks_store.update_task,
                task_id,
                blocked_reason=None,
                blocked_payload=None,
                queue_shard=queue_shard,
                frontier_state="ready",
                frontier_enqueued_at=enqueued_at,
                next_eligible_at=enqueued_at,
                return_updated=False,
            )
        except Exception as e:
            logger.warning(
                f"[Bridge] Failed to mirror ready frontier state for task {task_id}: {e}"
            )


async def _queued_transport_task_ids(
    queue_family: list[RedisRunnerQueueStore],
) -> list[str]:
    queued: list[str] = []
    for queue_store in queue_family:
        queue_client = await queue_store._get_client()
        if not queue_client:
            continue
        pending_members = await queue_client.lrange(queue_store.q_pending, 0, -1)
        temp_members = await queue_client.lrange(queue_store.q_temp, 0, -1)
        processing_members = await queue_client.zrange(queue_store.q_processing, 0, -1)
        delayed_members = await queue_client.zrange(queue_store.q_delayed, 0, -1)
        queued.extend(_normalize_task_id(task_id) for task_id in pending_members)
        queued.extend(_normalize_task_id(task_id) for task_id in temp_members)
        queued.extend(_normalize_task_id(task_id) for task_id in processing_members)
        queued.extend(_normalize_task_id(task_id) for task_id in delayed_members)
    return list(dict.fromkeys(queued))


def _browser_lane_key_from_task(task: Task) -> Optional[str]:
    try:
        from backend.app.runner.browser_fair_candidate_scheduler import (
            normalize_browser_lane_key,
        )

        ctx = task.execution_context if isinstance(task.execution_context, dict) else {}
        return normalize_browser_lane_key(
            getattr(task, "pack_id", None),
            ctx.get("playbook_code"),
        )
    except Exception:
        return None


async def _queued_browser_peer_lanes(
    client: Any,
    queued_task_ids: list[str],
) -> set[str]:
    if not queued_task_ids:
        return set()
    try:
        from backend.app.runner.browser_fair_candidate_scheduler import (
            normalize_browser_lane_key,
        )

        scan_limit = max(
            1,
            _env_int("LOCAL_CORE_RUNNER_BROWSER_PEER_SCAN_LIMIT", 512),
        )
        projections = await read_route_identity_projections(
            client,
            queued_task_ids[:scan_limit],
        )
        lanes: set[str] = set()
        for projection in projections.values():
            lane_key = normalize_browser_lane_key(
                projection.get("pack_id"),
                projection.get("playbook_code"),
            )
            if lane_key in _BROWSER_PEER_FRONTIER_LANES:
                lanes.add(lane_key)
        return lanes
    except Exception:
        return set()


async def _refill_browser_peer_frontier(
    tasks_store: TasksStore,
    redis_queue: RedisRunnerQueueStore,
    *,
    all_queues: Optional[list[RedisRunnerQueueStore]] = None,
) -> int:
    """Keep browser peer playbooks visible even when the hot queue is full."""
    if redis_queue.pack_id != _BROWSER_LOCAL_QUEUE_SHARD:
        return 0

    refill_limit = _browser_peer_frontier_refill_limit()
    if refill_limit <= 0:
        return 0

    client = await redis_queue._get_client()
    if not client:
        return 0

    queue_family = all_queues or [redis_queue]
    queued_task_ids = await _queued_transport_task_ids(queue_family)
    queued_task_id_set = set(queued_task_ids)
    queued_lanes = await _queued_browser_peer_lanes(client, queued_task_ids)
    if _BROWSER_PEER_FRONTIER_LANES.issubset(queued_lanes):
        return 0

    candidate_limit = max(refill_limit * 8, refill_limit)
    pending_tasks = await asyncio.to_thread(
        tasks_store.list_runnable_playbook_execution_tasks,
        None,
        candidate_limit,
        redis_queue.pack_id,
    )

    selected_tasks: list[Task] = []
    selected_lanes: set[str] = set()
    for task in pending_tasks:
        task_id = str(getattr(task, "id", "") or "").strip()
        if not task_id or task_id in queued_task_id_set:
            continue
        lane_key = _browser_lane_key_from_task(task)
        if lane_key not in _BROWSER_PEER_FRONTIER_LANES:
            continue
        if lane_key in queued_lanes or lane_key in selected_lanes:
            continue
        selected_tasks.append(task)
        selected_lanes.add(lane_key)
        if len(selected_tasks) >= refill_limit:
            break

    if not selected_tasks:
        return 0

    for task in selected_tasks:
        await redis_queue.enqueue_task(
            str(task.id),
            route_identity=build_route_identity_projection(task),
        )

    await _mark_frontier_ready(
        tasks_store,
        [str(task.id) for task in selected_tasks],
        queue_shard=redis_queue.pack_id,
    )
    logger.warning(
        "[Bridge] Refilled browser peer frontier with %d task(s) lanes=%s.",
        len(selected_tasks),
        ",".join(sorted(selected_lanes)),
    )
    return len(selected_tasks)


def _force_release_lock(
    task_ctx: dict,
    pack_id: str,
    redis_queue: Optional[RedisRunnerQueueStore],
    persisted_concurrency_key: Optional[str] = None,
    event_loop: Optional[asyncio.AbstractEventLoop] = None,
) -> None:
    """Force-delete the concurrency lock for a reaped task.

    The owning runner is dead, so we can't use compare-and-delete.
    We just DEL the key directly.
    Called from sync code inside an async event loop.
    """
    if not redis_queue:
        return
    lock_keys = _resolve_lock_keys(
        task_ctx,
        pack_id,
        persisted_concurrency_key=persisted_concurrency_key,
    )
    if not lock_keys:
        return
    try:
        loop = event_loop
        if loop is None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
        if loop is None or not loop.is_running():
            logger.warning(
                "[Reaper] No running event loop available to release lock(s) %s",
                lock_keys,
            )
            return
        for lock_key in lock_keys:
            asyncio.run_coroutine_threadsafe(
                _async_force_release(redis_queue, lock_key),
                loop,
            )
    except Exception as e:
        logger.warning(f"[Reaper] Failed to schedule lock release for {lock_keys}: {e}")


async def _async_force_release(
    redis_queue: RedisRunnerQueueStore, lock_key: str
) -> None:
    """Async helper to force-delete a lock key."""
    try:
        client = await redis_queue._get_client()
        if client:
            deleted = await client.delete(lock_key)
            if deleted:
                logger.info(f"[Reaper] Force-released lock {lock_key}")
    except Exception as e:
        logger.warning(f"[Reaper] Failed to force-release lock {lock_key}: {e}")


def _resolve_transport_queue_store(
    redis_queue: RedisRunnerQueueStore,
    queue_shard: Optional[str],
) -> RedisRunnerQueueStore:
    return resolve_transport_queue_store(redis_queue, queue_shard)


async def _async_reconcile_transport_membership(
    redis_queue: RedisRunnerQueueStore,
    *,
    task_id: str,
    queue_shard: Optional[str],
    reenqueue_pending: bool,
) -> None:
    target_queue = _resolve_transport_queue_store(redis_queue, queue_shard)
    if target_queue is not redis_queue:
        await reconcile_transport_membership(
            redis_queue,
            task_id=task_id,
            reenqueue_pending=False,
        )
    await reconcile_transport_membership(
        target_queue,
        task_id=task_id,
        reenqueue_pending=reenqueue_pending,
    )


async def _recycle_visibility_timeout_item(
    *,
    tasks_store: TasksStore,
    redis_queue: RedisRunnerQueueStore,
    client: Any,
    task_id: str,
    now_dt: datetime,
    stale_limit: datetime,
) -> str:
    return await recycle_visibility_timeout_item(
        tasks_store=tasks_store,
        redis_queue=redis_queue,
        task_id=task_id,
        now_dt=now_dt,
        stale_limit=stale_limit,
        effective_heartbeat_at=_effective_task_heartbeat_at,
        reconcile_membership=_async_reconcile_transport_membership,
    )


async def _reconcile_temp_transport_items(
    tasks_store: TasksStore,
    redis_queue: RedisRunnerQueueStore,
    client: Any,
    *,
    scan_limit: int,
) -> int:
    if scan_limit <= 0:
        return 0
    temp_items = await client.lrange(redis_queue.q_temp, 0, max(0, scan_limit - 1))
    repaired = 0
    for raw_task_id in temp_items:
        task_id = _normalize_task_id(raw_task_id).strip()
        if not task_id:
            continue
        task = await asyncio.to_thread(tasks_store.get_task, task_id)
        if not task:
            await _async_reconcile_transport_membership(
                redis_queue,
                task_id=task_id,
                queue_shard=redis_queue.pack_id,
                reenqueue_pending=False,
            )
            repaired += 1
            continue
        status = getattr(task, "status", None)
        if status in TERMINAL_TASK_STATUSES or status == TaskStatus.RUNNING:
            await _async_reconcile_transport_membership(
                redis_queue,
                task_id=task_id,
                queue_shard=getattr(task, "queue_shard", None),
                reenqueue_pending=False,
            )
            repaired += 1
            continue
        await _async_reconcile_transport_membership(
            redis_queue,
            task_id=task_id,
            queue_shard=getattr(task, "queue_shard", None),
            reenqueue_pending=task_is_runnable_pending(task),
        )
        repaired += 1
    return repaired


async def _scrub_processing_terminal_items(
    tasks_store: TasksStore,
    redis_queue: RedisRunnerQueueStore,
    client: Any,
    *,
    skip_task_ids: set[str],
    scan_limit: int,
) -> int:
    if scan_limit <= 0:
        return 0
    processing_items = await client.zrange(
        redis_queue.q_processing,
        0,
        max(0, scan_limit - 1),
    )
    repaired = 0
    for raw_task_id in processing_items:
        task_id = _normalize_task_id(raw_task_id).strip()
        if not task_id or task_id in skip_task_ids:
            continue
        task = await asyncio.to_thread(tasks_store.get_task, task_id)
        if not task:
            await _async_reconcile_transport_membership(
                redis_queue,
                task_id=task_id,
                queue_shard=redis_queue.pack_id,
                reenqueue_pending=False,
            )
            repaired += 1
            continue
        status = getattr(task, "status", None)
        if status in TERMINAL_TASK_STATUSES or (
            status == TaskStatus.PENDING and not task_is_runnable_pending(task)
        ):
            await _async_reconcile_transport_membership(
                redis_queue,
                task_id=task_id,
                queue_shard=getattr(task, "queue_shard", None),
                reenqueue_pending=False,
            )
            repaired += 1
    return repaired


def _requeue_stale_queued_task(
    tasks_store: TasksStore,
    task: Task,
    ctx: dict,
    *,
    runner_id: str,
    stale_seconds: int,
    reason: str,
    action: str,
    redis_queue: Optional[RedisRunnerQueueStore],
    event_loop: Optional[asyncio.AbstractEventLoop] = None,
) -> None:
    requeue_count = 0
    if isinstance(ctx.get("runner_reaper"), dict):
        requeue_count = ctx["runner_reaper"].get("requeue_count", 0)

    ctx2 = dict(ctx)
    ctx2.pop("runner_id", None)
    ctx2.pop("heartbeat_at", None)
    ctx2["status"] = "queued"
    ctx2["runner_reaper"] = {
        "runner_id": runner_id,
        "stale_seconds": stale_seconds,
        "action": action,
        "reason": reason,
        "requeue_count": requeue_count + 1,
        "requeued_at": _utc_now().isoformat(),
    }
    now = _utc_now()
    tasks_store.update_task(
        task.id,
        execution_context=ctx2,
        status=TaskStatus.PENDING,
        started_at=None,
        next_eligible_at=now,
        blocked_reason=None,
        blocked_payload=None,
        runner_id=None,
        heartbeat_at=None,
        frontier_state="ready",
        frontier_enqueued_at=now,
        error=None,
    )
    _force_release_lock(
        ctx,
        task.pack_id,
        redis_queue,
        persisted_concurrency_key=getattr(task, "concurrency_key", None),
        event_loop=event_loop,
    )


def _reap_stale_running_tasks(
    tasks_store: TasksStore,
    runner_id: str,
    redis_queue: Optional[RedisRunnerQueueStore] = None,
    event_loop: Optional[asyncio.AbstractEventLoop] = None,
    live_state_store: Optional[RunnerLiveStateStore] = None,
) -> None:
    stale_seconds = _env_int("LOCAL_CORE_RUNNER_STALE_TASK_SECONDS", 180)
    threshold = _utc_now() - timedelta(seconds=stale_seconds)

    try:
        running = tasks_store.list_running_playbook_execution_tasks(
            workspace_id=None, limit=500
        )
        list_frontier_running_pending_tasks = getattr(
            tasks_store,
            "list_frontier_running_pending_tasks",
            None,
        )
        if callable(list_frontier_running_pending_tasks):
            running.extend(
                list_frontier_running_pending_tasks(workspace_id=None, limit=500)
            )
    except Exception as e:
        logger.warning(f"Runner stale-task scan failed: {e}")
        return

    seen_task_ids: set[str] = set()
    for t in running:
        if t.id in seen_task_ids:
            continue
        seen_task_ids.add(t.id)
        try:
            ctx = t.execution_context if isinstance(t.execution_context, dict) else {}
            ctx_runner_id = _task_runner_id(t, ctx)
            heartbeat_at = _effective_task_heartbeat_at(t, ctx, live_state_store)

            # Only reap tasks that were executed in runner mode (or clearly runner-owned).
            if ctx.get("execution_mode") not in (None, "runner"):
                continue

            if not ctx_runner_id:
                if (
                    t.status == TaskStatus.PENDING
                    and ctx.get("status") == "queued"
                    and _is_stale_started_task(t, threshold)
                ):
                    msg = (
                        "Runner ownership missing for stale queued task "
                        f"(started_at={getattr(t, 'started_at', None)})"
                    )
                    _requeue_stale_queued_task(
                        tasks_store,
                        t,
                        ctx,
                        runner_id=runner_id,
                        stale_seconds=stale_seconds,
                        reason=msg,
                        action="requeue_orphan_no_runner",
                        redis_queue=redis_queue,
                        event_loop=event_loop,
                    )
                    logger.warning(
                        f"Re-queued stale runner task without owner task_id={t.id} ({msg})"
                    )
                continue

            if heartbeat_at and heartbeat_at > threshold:
                # Even if heartbeat is fresh, if runner_id doesn't match
                # current runner, this task may be orphaned.  Give it a
                # grace period (half stale window) to avoid killing tasks
                # during rolling restarts.
                if ctx_runner_id == runner_id:
                    continue
                grace_threshold = _utc_now() - timedelta(seconds=stale_seconds // 2)
                if heartbeat_at > grace_threshold:
                    continue

            heartbeat_log = _heartbeat_log_value(heartbeat_at, ctx)
            msg = f"Runner heartbeat stale (previous_runner_id={ctx_runner_id}, heartbeat_at={heartbeat_log})"
            ctx2 = dict(ctx)
            ctx2["runner_reaper"] = {
                "runner_id": runner_id,
                "stale_seconds": stale_seconds,
                "action": None,
                "reason": msg,
            }

            # If the task is still queued, re-queue it so a healthy runner can claim it.
            # IMPORTANT:
            # - Do NOT use sandbox_id/current_step_index as "started" heuristics; some runner tasks
            #   execute in-process and may never set sandbox_id even after making real progress.
            if ctx2.get("status") == "queued":
                requeue_count = 0
                if isinstance(ctx.get("runner_reaper"), dict):
                    requeue_count = ctx["runner_reaper"].get("requeue_count", 0)

                if requeue_count >= 3:
                    # Too many re-queues — fail permanently
                    ctx2["status"] = "failed"
                    ctx2["error"] = f"Exceeded max re-queue attempts ({requeue_count})"
                    ctx2["runner_reaper"]["action"] = "fail_max_requeue"
                    ctx2["runner_reaper"]["requeue_count"] = requeue_count
                    tasks_store.update_task(
                        t.id,
                        execution_context=ctx2,
                        status=TaskStatus.FAILED,
                        completed_at=_utc_now(),
                        error=ctx2["error"],
                        runner_id=None,
                        heartbeat_at=None,
                    )
                    _emit_run_state_changed_for_task(
                        t,
                        previous_state="RUNNING",
                        new_state="FAILED",
                        reason=ctx2["error"],
                    )
                    logger.warning(
                        f"Failed task after {requeue_count} re-queues task_id={t.id} ({msg})"
                    )
                else:
                    _requeue_stale_queued_task(
                        tasks_store,
                        t,
                        ctx,
                        runner_id=runner_id,
                        stale_seconds=stale_seconds,
                        reason=msg,
                        action="requeue",
                        redis_queue=redis_queue,
                        event_loop=event_loop,
                    )
                    logger.warning(
                        f"Re-queued stale runner task task_id={t.id} (attempt {requeue_count + 1}/3) ({msg})"
                    )
            else:
                # If the task is running but heartbeat is stale, mark failed.
                # Try on_fail lifecycle hook first (declared in playbook spec).
                hook_handled = False
                try:
                    hook_handled = _invoke_on_fail_hook_sync(ctx2, msg, t.id)
                except Exception as hook_err:
                    logger.warning(f"Reaper on_fail hook error for {t.id}: {hook_err}")

                if hook_handled:
                    ctx2["runner_reaper"]["action"] = "lifecycle_hook_on_fail"
                    logger.warning(
                        f"Reaped + on_fail hook invoked for stale task task_id={t.id} ({msg})"
                    )

                # ALWAYS ensure task reaches terminal state, regardless of hook result.
                # Re-read to check if hook already marked it FAILED.
                refreshed = tasks_store.get_task(t.id)
                if refreshed and refreshed.status not in (
                    TaskStatus.FAILED,
                    TaskStatus.CANCELLED_BY_USER,
                    TaskStatus.SUCCEEDED,
                    TaskStatus.EXPIRED,
                ):
                    ctx2["status"] = "failed"
                    ctx2["error"] = msg
                    ctx2["failed_at"] = _utc_now().isoformat()
                    if not hook_handled:
                        ctx2["runner_reaper"]["action"] = "fail"
                    tasks_store.update_task(
                        t.id,
                        execution_context=ctx2,
                        status=TaskStatus.FAILED,
                        completed_at=_utc_now(),
                        error=msg,
                        runner_id=None,
                        heartbeat_at=None,
                    )
                    _emit_run_state_changed_for_task(
                        t,
                        previous_state="RUNNING",
                        new_state="FAILED",
                        reason=msg,
                    )
                    logger.warning(f"Reaped stale running task task_id={t.id} ({msg})")
                    _force_release_lock(
                        ctx,
                        t.pack_id,
                        redis_queue,
                        persisted_concurrency_key=getattr(t, "concurrency_key", None),
                        event_loop=event_loop,
                    )
            logger.info(
                f"Reaper checked task_id={t.id} - status={t.status} - heartbeat_at={heartbeat_log} - Threshold={threshold.isoformat()}"
            )
        except Exception as e:
            logger.warning(f"Failed to reap stale task {getattr(t,'id',None)}: {e}")



async def _reap_redis_queues(
    tasks_store: TasksStore,
    redis_queue: RedisRunnerQueueStore,
    *,
    ready_target_override: Optional[int] = None,
    all_queues: Optional[list[RedisRunnerQueueStore]] = None,
) -> None:
    """Orchestrator background loop for Redis Queue reliability guarantees."""
    try:
        client = await redis_queue._get_client()
        if not client:
            return
            
        now_ts = redis_queue._utc_now_timestamp()
        ready_target = ready_target_override or _env_int("LOCAL_CORE_RUNNER_READY_TARGET", 64)
        delayed_move_limit = _env_int("LOCAL_CORE_RUNNER_DELAYED_MOVE_LIMIT", 100)
        transport_repair_limit = _env_int("LOCAL_CORE_RUNNER_TRANSPORT_REPAIR_LIMIT", 100)
        
        # 1. Delayed Queue Mover — move in small pipeline batches to avoid
        #    blocking Redis single-threaded processing (SLOWLOG showed 17ms for 688-item pipeline).
        _PIPELINE_BATCH = 100
        delayed_items = await client.zrangebyscore(
            redis_queue.q_delayed, "-inf", now_ts, start=0, num=delayed_move_limit
        )
        if delayed_items:
            try:
                moved = 0
                for i in range(0, len(delayed_items), _PIPELINE_BATCH):
                    batch = delayed_items[i:i + _PIPELINE_BATCH]
                    for task_id in batch:
                        normalized_task_id = _normalize_task_id(task_id)
                        task = await asyncio.to_thread(tasks_store.get_task, normalized_task_id)
                        await redis_queue.enqueue_task(
                            normalized_task_id,
                            route_identity=(
                                build_route_identity_projection(task)
                                if task
                                else {"task_id": normalized_task_id}
                            ),
                        )
                        await client.zrem(redis_queue.q_delayed, task_id)
                    moved += len(batch)
                    # Yield so Redis can serve other clients between batches
                    if i + _PIPELINE_BATCH < len(delayed_items):
                        await asyncio.sleep(0)
                await _mark_frontier_ready(
                    tasks_store,
                    [str(task_id) for task_id in delayed_items],
                    queue_shard=redis_queue.pack_id,
                )
                logger.info(f"[Bridge] Moved {moved} tasks from delayed to pending queue.")
            except Exception as e:
                logger.warning(f"Failed to batch move delayed tasks: {e}")

        temp_repaired = await _reconcile_temp_transport_items(
            tasks_store,
            redis_queue,
            client,
            scan_limit=transport_repair_limit,
        )
        if temp_repaired:
            logger.warning(
                "[Bridge] Repaired %d temp transport member(s) on shard %s.",
                temp_repaired,
                redis_queue.pack_id,
            )

        # 2. Visibility Timeout Recycler
        stale_items = await client.zrangebyscore(redis_queue.q_processing, "-inf", now_ts)
        stale_item_ids = {_normalize_task_id(task_id) for task_id in stale_items}
        scrubbed_count = await _scrub_processing_terminal_items(
            tasks_store,
            redis_queue,
            client,
            skip_task_ids=stale_item_ids,
            scan_limit=transport_repair_limit,
        )
        if scrubbed_count:
            logger.warning(
                "[Bridge] Scrubbed %d invalid processing transport member(s) on shard %s.",
                scrubbed_count,
                redis_queue.pack_id,
            )
        for task_id in stale_items:
            try:
                result = await _recycle_visibility_timeout_item(
                    tasks_store=tasks_store,
                    redis_queue=redis_queue,
                    client=client,
                    task_id=_normalize_task_id(task_id),
                    now_dt=_utc_now(),
                    stale_limit=_utc_now()
                    - timedelta(
                        seconds=_env_int("LOCAL_CORE_RUNNER_STALE_TASK_SECONDS", 180)
                    ),
                )
                if result == "requeued":
                    logger.warning(
                        "[Bridge] Task %s visibility timeout expired. Reverting to queue.",
                        _normalize_task_id(task_id),
                    )
            except Exception as e:
                logger.error(f"Failed to recycle visibility task {task_id}: {e}")

        ready_depth = await client.llen(redis_queue.q_pending)
        release_limit = _blocked_release_limit(ready_target, ready_depth)
        concurrency_released_count = await _release_concurrency_locked_tasks(
            tasks_store,
            redis_queue,
            release_limit=release_limit,
        )
        ready_depth += concurrency_released_count

        release_limit = _blocked_release_limit(ready_target, ready_depth)
        dependency_released_count = await _release_dependency_hold_tasks(
            tasks_store,
            redis_queue,
            release_limit=release_limit,
        )
        ready_depth += dependency_released_count

        release_limit = _blocked_release_limit(ready_target, ready_depth)
        resource_released_count = await _release_resource_wait_tasks(
            tasks_store,
            redis_queue,
            release_limit=release_limit,
        )
        ready_depth += resource_released_count

        release_limit = max(0, ready_target - ready_depth)
        workspace_quota_released_count = await _release_workspace_quota_tasks(
            tasks_store,
            redis_queue,
            release_limit=release_limit,
        )
        ready_depth += workspace_quota_released_count

        release_limit = max(0, ready_target - ready_depth)
        released_count = await _release_admission_deferred_tasks(
            tasks_store,
            redis_queue,
            release_limit=release_limit,
        )
        ready_depth += released_count

        release_limit = max(0, ready_target - ready_depth)
        cold_released_count = await _release_unblocked_cold_tasks(
            tasks_store,
            redis_queue,
            release_limit=release_limit,
        )
        ready_depth += cold_released_count

        peer_refilled_count = await _refill_browser_peer_frontier(
            tasks_store,
            redis_queue,
            all_queues=all_queues,
        )
        ready_depth += peer_refilled_count

        # 3. DB Bridge Sync (Eventual Consistency Repair)
        #    Keep only a bounded ready frontier in Redis. Do not materialize
        #    the full runnable backlog into the hot queue.
        try:
            refill_limit = max(0, ready_target - ready_depth)
            if refill_limit <= 0:
                return

            queue_family = all_queues or [redis_queue]
            all_queued = set()
            for queue_store in queue_family:
                queue_client = client if queue_store is redis_queue else await queue_store._get_client()
                if not queue_client:
                    continue
                pending_members = await queue_client.lrange(queue_store.q_pending, 0, -1)
                temp_members = await queue_client.lrange(queue_store.q_temp, 0, -1)
                processing_members = await queue_client.zrange(
                    queue_store.q_processing, 0, -1
                )
                delayed_members = await queue_client.zrange(
                    queue_store.q_delayed, 0, -1
                )
                all_queued.update(_normalize_task_id(task_id) for task_id in pending_members)
                all_queued.update(_normalize_task_id(task_id) for task_id in temp_members)
                all_queued.update(
                    _normalize_task_id(task_id) for task_id in processing_members
                )
                all_queued.update(_normalize_task_id(task_id) for task_id in delayed_members)

            pending_tasks = await asyncio.to_thread(
                tasks_store.list_runnable_playbook_execution_tasks,
                None,
                max(refill_limit * 4, refill_limit),
                redis_queue.pack_id,
            )

            missing_tasks = []
            for t in pending_tasks:
                if t.id not in all_queued:
                    missing_tasks.append(t)
                if len(missing_tasks) >= refill_limit:
                    break

            if missing_tasks:
                for i in range(0, len(missing_tasks), _PIPELINE_BATCH):
                    batch = missing_tasks[i:i + _PIPELINE_BATCH]
                    for task in batch:
                        await redis_queue.enqueue_task(
                            str(task.id),
                            route_identity=build_route_identity_projection(task),
                        )
                    if i + _PIPELINE_BATCH < len(missing_tasks):
                        await asyncio.sleep(0)
                await _mark_frontier_ready(
                    tasks_store,
                    [str(task.id) for task in missing_tasks],
                    queue_shard=redis_queue.pack_id,
                )
                logger.warning(
                    f"[Bridge] Refilled ready frontier with {len(missing_tasks)} task(s) (ready_depth={ready_depth}, ready_target={ready_target})."
                )
                
        except Exception as e:
            logger.error(f"[Bridge] DB Bridge sync failed: {e}")

    except Exception as e:
        if is_database_recovery_error(e):
            logger.warning(
                "Runner Redis bridge paused while PostgreSQL is recovering."
            )
            return
        logger.error(f"Failed to reap Redis queues: {e}", exc_info=True)


async def _release_admission_deferred_tasks(
    tasks_store: TasksStore,
    redis_queue: RedisRunnerQueueStore,
    *,
    release_limit: int,
) -> int:
    if release_limit <= 0:
        return 0

    list_due_release_candidates = getattr(
        tasks_store,
        "list_due_admission_deferred_release_candidates",
        tasks_store.list_due_admission_deferred_tasks,
    )
    due_tasks = await asyncio.to_thread(
        list_due_release_candidates,
        queue_shard=redis_queue.pack_id,
        limit=max(release_limit * 4, release_limit),
    )
    if not due_tasks:
        return 0

    client = await redis_queue._get_client()
    if not client:
        return 0

    now = _utc_now()
    released_task_ids: list[str] = []

    for task in due_tasks:
        if len(released_task_ids) >= release_limit:
            break

        try:
            decision = await asyncio.to_thread(
                TASK_ADMISSION_SERVICE.evaluate_on_release,
                tasks_store,
                task,
            )
            if decision.allow:
                await asyncio.to_thread(
                    tasks_store.update_task,
                    task.id,
                    next_eligible_at=now,
                    blocked_reason=None,
                    blocked_payload=None,
                    queue_shard=decision.queue_shard or redis_queue.pack_id,
                    frontier_state="ready",
                    frontier_enqueued_at=now,
                    return_updated=False,
                )
                released_task_ids.append(task.id)
                continue

            await asyncio.to_thread(
                tasks_store.update_task,
                task.id,
                next_eligible_at=decision.next_eligible_at,
                blocked_reason=ADMISSION_DEFERRED_REASON,
                blocked_payload=decision.blocked_payload,
                queue_shard=decision.queue_shard or redis_queue.pack_id,
                frontier_state="cold",
                frontier_enqueued_at=None,
                return_updated=False,
            )
        except Exception as exc:
            logger.warning(
                "[Admission] Failed to evaluate deferred task %s on shard %s: %s",
                getattr(task, "id", None),
                redis_queue.pack_id,
                exc,
            )

    if not released_task_ids:
        return 0

    try:
        pipe = client.pipeline()
        for task_id in released_task_ids:
            pipe.rpush(redis_queue.q_pending, task_id)
        await pipe.execute()
    except Exception as exc:
        logger.warning(
            "[Admission] Failed to enqueue %d released task(s) for shard %s: %s",
            len(released_task_ids),
            redis_queue.pack_id,
            exc,
        )

    return len(released_task_ids)


async def _release_workspace_quota_tasks(
    tasks_store: TasksStore,
    redis_queue: RedisRunnerQueueStore,
    *,
    release_limit: int,
) -> int:
    if release_limit <= 0:
        return 0

    list_due_workspace_quota_tasks = getattr(
        tasks_store,
        "list_due_workspace_quota_tasks",
        None,
    )
    if not list_due_workspace_quota_tasks:
        return 0

    due_tasks = await asyncio.to_thread(
        list_due_workspace_quota_tasks,
        queue_shard=redis_queue.pack_id,
        limit=max(release_limit * 4, release_limit),
    )
    if not due_tasks:
        return 0

    client = await redis_queue._get_client()
    if not client:
        return 0

    count_ready_workspace_quota_tasks = getattr(
        tasks_store,
        "count_ready_workspace_quota_tasks",
        None,
    )
    try_release_workspace_quota_task = getattr(
        tasks_store,
        "try_release_workspace_quota_task",
        None,
    )
    now = _utc_now()
    blocked_next_eligible_at = now + timedelta(
        seconds=max(
            1,
            _env_int("LOCAL_CORE_WORKSPACE_QUOTA_RELEASE_BACKOFF_SECONDS", 10),
        )
    )
    released_task_ids: list[str] = []
    released_by_allocation: dict[str, int] = {}
    ready_count_by_allocation: dict[str, int] = {}

    for task in due_tasks:
        if len(released_task_ids) >= release_limit:
            break
        if getattr(task, "blocked_reason", None) not in _WORKSPACE_QUOTA_RELEASE_REASONS:
            continue

        try:
            decision = await asyncio.to_thread(
                decide_workspace_quota_admission_for_task,
                task,
            )
            payload = _workspace_quota_payload(decision)
            allocation = _workspace_quota_allocation(decision, payload)
            allocation_key = _workspace_quota_release_key(task, allocation)
            max_parallel_task_claims = max(
                1,
                _workspace_quota_int(
                    getattr(decision, "max_parallel_task_claims", None)
                    or payload.get("max_parallel_task_claims"),
                    default=1,
                ),
            )
            active_count = max(
                0,
                _workspace_quota_int(
                    getattr(decision, "active_count", None)
                    or payload.get("active_count"),
                    default=0,
                ),
            )
            selectors = _workspace_quota_task_selectors(allocation)
            atomic_release = callable(try_release_workspace_quota_task)

            if not atomic_release and allocation_key not in ready_count_by_allocation:
                ready_count = 0
                if callable(count_ready_workspace_quota_tasks):
                    ready_count = await asyncio.to_thread(
                        count_ready_workspace_quota_tasks,
                        workspace_id=str(getattr(task, "workspace_id", "") or ""),
                        queue_shard=str(
                            getattr(task, "queue_shard", "")
                            or redis_queue.pack_id
                        ),
                        selectors=selectors,
                    )
                ready_count_by_allocation[allocation_key] = max(0, int(ready_count or 0))

            reserved_count = (
                active_count
                + ready_count_by_allocation.get(allocation_key, 0)
                + released_by_allocation.get(allocation_key, 0)
            )
            quota_available = bool(getattr(decision, "allow", False)) and (
                atomic_release or reserved_count < max_parallel_task_claims
            )
            if not quota_available:
                blocked_payload = dict(payload)
                blocked_payload["ready_pending_count"] = ready_count_by_allocation.get(
                    allocation_key,
                    0,
                )
                blocked_payload["released_in_loop"] = released_by_allocation.get(
                    allocation_key,
                    0,
                )
                await asyncio.to_thread(
                    tasks_store.update_task,
                    task.id,
                    next_eligible_at=blocked_next_eligible_at,
                    blocked_reason=(
                        _WORKSPACE_QUOTA_EXHAUSTED_REASON
                        if bool(getattr(decision, "allow", False))
                        else (
                            str(getattr(decision, "reason", "") or "").strip()
                            or _WORKSPACE_QUOTA_EXHAUSTED_REASON
                        )
                    ),
                    blocked_payload=blocked_payload,
                    frontier_state="cold",
                    frontier_enqueued_at=None,
                    return_updated=False,
                )
                continue

            raw_ctx = task.execution_context
            update_kwargs = dict(
                next_eligible_at=now,
                blocked_reason=None,
                blocked_payload=None,
                queue_shard=getattr(task, "queue_shard", None) or redis_queue.pack_id,
                frontier_state="ready",
                frontier_enqueued_at=now,
            )
            if isinstance(raw_ctx, dict):
                ctx2 = dict(raw_ctx)
                ctx2.pop("workspace_quota_admission", None)
                ctx2.pop("runner_claim_admission", None)
                ctx2.pop("resume_after", None)
                update_kwargs["execution_context"] = ctx2
            if atomic_release:
                task_selector = str(
                    getattr(task, "pack_id", None)
                    or update_kwargs.get("execution_context", {}).get("playbook_code")
                    or getattr(task, "task_type", "")
                    or ""
                ).strip()
                released = await asyncio.to_thread(
                    try_release_workspace_quota_task,
                    task.id,
                    workspace_id=str(getattr(task, "workspace_id", "") or ""),
                    queue_shard=str(
                        getattr(task, "queue_shard", "") or redis_queue.pack_id
                    ),
                    selectors=selectors,
                    task_selector=task_selector,
                    allocation_key=allocation_key,
                    max_parallel_task_claims=max_parallel_task_claims,
                    blocked_reasons=list(_WORKSPACE_QUOTA_RELEASE_REASONS),
                    execution_context=update_kwargs.get("execution_context"),
                    now=now,
                )
                if not released:
                    blocked_payload = dict(payload)
                    blocked_payload["atomic_release"] = "reserved_capacity_unavailable"
                    await asyncio.to_thread(
                        tasks_store.update_task,
                        task.id,
                        next_eligible_at=blocked_next_eligible_at,
                        blocked_reason=_WORKSPACE_QUOTA_EXHAUSTED_REASON,
                        blocked_payload=blocked_payload,
                        frontier_state="cold",
                        frontier_enqueued_at=None,
                        return_updated=False,
                    )
                    continue
            else:
                await asyncio.to_thread(
                    tasks_store.update_task,
                    task.id,
                    return_updated=False,
                    **update_kwargs,
                )
            released_task_ids.append(task.id)
            released_by_allocation[allocation_key] = (
                released_by_allocation.get(allocation_key, 0) + 1
            )
        except Exception as exc:
            logger.warning(
                "[Bridge] Failed to release workspace quota task %s on shard %s: %s",
                getattr(task, "id", None),
                redis_queue.pack_id,
                exc,
            )

    if not released_task_ids:
        return 0

    try:
        pipe = client.pipeline()
        for task_id in released_task_ids:
            pipe.rpush(redis_queue.q_pending, task_id)
        await pipe.execute()
    except Exception as exc:
        logger.warning(
            "[Bridge] Failed to enqueue %d workspace quota task(s) for shard %s: %s",
            len(released_task_ids),
            redis_queue.pack_id,
            exc,
        )
        return 0

    logger.warning(
        "[Bridge] Released %d workspace quota task(s) on shard %s.",
        len(released_task_ids),
        redis_queue.pack_id,
    )
    return len(released_task_ids)


async def _release_resource_wait_tasks(
    tasks_store: TasksStore,
    redis_queue: RedisRunnerQueueStore,
    *,
    release_limit: int,
) -> int:
    if release_limit <= 0:
        return 0

    list_due_resource_wait_tasks = getattr(
        tasks_store,
        "list_due_resource_wait_tasks",
        None,
    )
    if not list_due_resource_wait_tasks:
        return 0

    due_tasks = await asyncio.to_thread(
        list_due_resource_wait_tasks,
        queue_shard=redis_queue.pack_id,
        limit=max(release_limit * 4, release_limit),
    )
    if not due_tasks:
        return 0

    client = await redis_queue._get_client()
    if not client:
        return 0

    now = _utc_now()
    released_task_ids: list[str] = []
    released_resource_keys: set[str] = set()

    for task in due_tasks:
        if len(released_task_ids) >= release_limit:
            break
        if getattr(task, "blocked_reason", None) != _RESOURCE_WAIT_REASON:
            continue

        raw_ctx = task.execution_context
        ctx = raw_ctx if isinstance(raw_ctx, dict) else {}
        resource_keys = _resource_wait_keys_from_context(ctx)
        if resource_keys and any(
            resource_key in released_resource_keys for resource_key in resource_keys
        ):
            continue
        still_blocked = _host_resource_wait_still_blocked(ctx)
        if still_blocked is not None:
            next_eligible_at = now + timedelta(
                seconds=max(5, _env_int("LOCAL_CORE_HOST_RESOURCE_WAIT_BACKOFF_SECONDS", 30))
            )
            blocked_payload = {
                "policy": _RESOURCE_WAIT_REASON,
                "reason": getattr(still_blocked, "reason", None) or "host_resource_still_blocked",
                "defer_until": next_eligible_at.isoformat(),
                "evaluated_at": now.isoformat(),
                "host_decision": getattr(still_blocked, "decision", "defer"),
                "host_advisor": getattr(still_blocked, "payload", {}) or {},
            }
            ctx2 = dict(ctx)
            admission = dict(ctx2.get("resource_admission") or {})
            admission["state"] = "waiting"
            admission["reason"] = blocked_payload["reason"]
            admission["defer_until"] = next_eligible_at.isoformat()
            ctx2["resource_admission"] = admission
            ctx2["resume_after"] = next_eligible_at.isoformat()
            try:
                await asyncio.to_thread(
                    tasks_store.update_task,
                    task.id,
                    execution_context=ctx2,
                    next_eligible_at=next_eligible_at,
                    blocked_reason=_RESOURCE_WAIT_REASON,
                    blocked_payload=blocked_payload,
                    frontier_state="cold",
                    frontier_enqueued_at=None,
                    return_updated=False,
                )
            except Exception as exc:
                logger.warning(
                    "[Bridge] Failed to extend resource-wait task %s on shard %s: %s",
                    getattr(task, "id", None),
                    redis_queue.pack_id,
                    exc,
                )
            continue

        try:
            update_kwargs = dict(
                next_eligible_at=now,
                blocked_reason=None,
                blocked_payload=None,
                queue_shard=getattr(task, "queue_shard", None) or redis_queue.pack_id,
                frontier_state="ready",
                frontier_enqueued_at=now,
            )
            if isinstance(raw_ctx, dict):
                ctx2 = dict(raw_ctx)
                ctx2.pop("resource_admission", None)
                ctx2.pop("runner_resource_leases", None)
                ctx2.pop("resume_after", None)
                update_kwargs["execution_context"] = ctx2
            await asyncio.to_thread(
                tasks_store.update_task,
                task.id,
                return_updated=False,
                **update_kwargs,
            )
            released_task_ids.append(task.id)
            released_resource_keys.update(resource_keys)
        except Exception as exc:
            logger.warning(
                "[Bridge] Failed to release resource-wait task %s on shard %s: %s",
                getattr(task, "id", None),
                redis_queue.pack_id,
                exc,
            )

    if not released_task_ids:
        return 0

    try:
        pipe = client.pipeline()
        for task_id in released_task_ids:
            pipe.rpush(redis_queue.q_pending, task_id)
        await pipe.execute()
    except Exception as exc:
        logger.warning(
            "[Bridge] Failed to enqueue %d resource-wait task(s) for shard %s: %s",
            len(released_task_ids),
            redis_queue.pack_id,
            exc,
        )
        return 0

    logger.warning(
        "[Bridge] Released %d due resource-wait task(s) on shard %s.",
        len(released_task_ids),
        redis_queue.pack_id,
    )
    return len(released_task_ids)


async def _release_dependency_hold_tasks(
    tasks_store: TasksStore,
    redis_queue: RedisRunnerQueueStore,
    *,
    release_limit: int,
) -> int:
    if release_limit <= 0:
        return 0

    list_due_dependency_hold_tasks = getattr(
        tasks_store,
        "list_due_dependency_hold_tasks",
        None,
    )
    if not list_due_dependency_hold_tasks:
        return 0

    due_tasks = await asyncio.to_thread(
        list_due_dependency_hold_tasks,
        queue_shard=redis_queue.pack_id,
        limit=max(release_limit * 4, release_limit),
    )
    if not due_tasks:
        return 0

    client = await redis_queue._get_client()
    if not client:
        return 0

    now = _utc_now()
    released_task_ids: list[str] = []

    for task in due_tasks:
        if len(released_task_ids) >= release_limit:
            break
        if getattr(task, "blocked_reason", None) != _DEPENDENCY_HOLD_REASON:
            continue

        try:
            raw_ctx = task.execution_context
            update_kwargs = dict(
                next_eligible_at=now,
                blocked_reason=None,
                blocked_payload=None,
                queue_shard=getattr(task, "queue_shard", None) or redis_queue.pack_id,
                frontier_state="ready",
                frontier_enqueued_at=now,
            )
            if isinstance(raw_ctx, dict):
                ctx2 = dict(raw_ctx)
                ctx2.pop("dependency_hold", None)
                ctx2.pop("resume_after", None)
                update_kwargs["execution_context"] = ctx2
            await asyncio.to_thread(
                tasks_store.update_task,
                task.id,
                **update_kwargs,
            )
            released_task_ids.append(task.id)
        except Exception as exc:
            logger.warning(
                "[Bridge] Failed to release dependency-held task %s on shard %s: %s",
                getattr(task, "id", None),
                redis_queue.pack_id,
                exc,
            )

    if not released_task_ids:
        return 0

    try:
        pipe = client.pipeline()
        for task_id in released_task_ids:
            pipe.rpush(redis_queue.q_pending, task_id)
        await pipe.execute()
    except Exception as exc:
        logger.warning(
            "[Bridge] Failed to enqueue %d dependency-held task(s) for shard %s: %s",
            len(released_task_ids),
            redis_queue.pack_id,
            exc,
        )
        return 0

    logger.warning(
        "[Bridge] Released %d due dependency-held task(s) on shard %s.",
        len(released_task_ids),
        redis_queue.pack_id,
    )
    return len(released_task_ids)


async def _release_unblocked_cold_tasks(
    tasks_store: TasksStore,
    redis_queue: RedisRunnerQueueStore,
    *,
    release_limit: int,
) -> int:
    if release_limit <= 0:
        return 0

    list_due_unblocked_cold_tasks = getattr(
        tasks_store,
        "list_due_unblocked_cold_tasks",
        None,
    )
    if not list_due_unblocked_cold_tasks:
        return 0

    due_tasks = await asyncio.to_thread(
        list_due_unblocked_cold_tasks,
        queue_shard=redis_queue.pack_id,
        limit=max(release_limit * 4, release_limit),
    )
    if not due_tasks:
        return 0

    client = await redis_queue._get_client()
    if not client:
        return 0

    now = _utc_now()
    released_task_ids: list[str] = []

    for task in due_tasks:
        if len(released_task_ids) >= release_limit:
            break
        if getattr(task, "blocked_reason", None):
            continue

        try:
            await asyncio.to_thread(
                tasks_store.update_task,
                task.id,
                next_eligible_at=now,
                blocked_reason=None,
                blocked_payload=None,
                queue_shard=getattr(task, "queue_shard", None) or redis_queue.pack_id,
                frontier_state="ready",
                frontier_enqueued_at=now,
                return_updated=False,
            )
            released_task_ids.append(task.id)
        except Exception as exc:
            logger.warning(
                "[Bridge] Failed to release cold pending task %s on shard %s: %s",
                getattr(task, "id", None),
                redis_queue.pack_id,
                exc,
            )

    if not released_task_ids:
        return 0

    try:
        pipe = client.pipeline()
        for task_id in released_task_ids:
            pipe.rpush(redis_queue.q_pending, task_id)
        await pipe.execute()
    except Exception as exc:
        logger.warning(
            "[Bridge] Failed to enqueue %d cold pending task(s) for shard %s: %s",
            len(released_task_ids),
            redis_queue.pack_id,
            exc,
        )
        return 0

    logger.warning(
        "[Bridge] Released %d unblocked cold task(s) on shard %s.",
        len(released_task_ids),
        redis_queue.pack_id,
    )
    return len(released_task_ids)


async def _release_concurrency_locked_tasks(
    tasks_store: TasksStore,
    redis_queue: RedisRunnerQueueStore,
    *,
    release_limit: int,
) -> int:
    if release_limit <= 0:
        return 0

    list_due_locked_tasks = getattr(
        tasks_store,
        "list_due_concurrency_locked_tasks",
        None,
    )
    if not list_due_locked_tasks:
        return 0

    due_tasks = await asyncio.to_thread(
        list_due_locked_tasks,
        queue_shard=redis_queue.pack_id,
        limit=max(release_limit * 4, release_limit),
    )
    if not due_tasks:
        return 0

    client = await redis_queue._get_client()
    if not client:
        return 0

    now = _utc_now()
    released_task_ids: list[str] = []
    released_lock_keys: set[str] = set()

    for task in due_tasks:
        if len(released_task_ids) >= release_limit:
            break
        if getattr(task, "blocked_reason", None) != _CONCURRENCY_LOCKED_REASON:
            continue

        raw_ctx = task.execution_context
        ctx = raw_ctx if isinstance(raw_ctx, dict) else {}
        lock_keys = _resolve_lock_keys(
            ctx,
            str(getattr(task, "pack_id", "") or ""),
            persisted_concurrency_key=getattr(task, "concurrency_key", None),
        )
        if lock_keys and any(lock_key in released_lock_keys for lock_key in lock_keys):
            continue

        try:
            update_kwargs = dict(
                next_eligible_at=now,
                blocked_reason=None,
                blocked_payload=None,
                queue_shard=getattr(task, "queue_shard", None) or redis_queue.pack_id,
                frontier_state="ready",
                frontier_enqueued_at=now,
            )
            if isinstance(raw_ctx, dict):
                ctx2 = dict(raw_ctx)
                ctx2.pop("runner_skip_reason", None)
                ctx2.pop("runner_skip_lock_key", None)
                ctx2.pop("runner_skip_conflict_lock_key", None)
                ctx2.pop("resume_after", None)
                update_kwargs["execution_context"] = ctx2
            await asyncio.to_thread(
                tasks_store.update_task,
                task.id,
                return_updated=False,
                **update_kwargs,
            )
            released_task_ids.append(task.id)
            released_lock_keys.update(lock_keys)
        except Exception as exc:
            logger.warning(
                "[Bridge] Failed to release concurrency-locked task %s on shard %s: %s",
                getattr(task, "id", None),
                redis_queue.pack_id,
                exc,
            )

    if not released_task_ids:
        return 0

    try:
        pipe = client.pipeline()
        for task_id in released_task_ids:
            pipe.rpush(redis_queue.q_pending, task_id)
        await pipe.execute()
    except Exception as exc:
        logger.warning(
            "[Bridge] Failed to enqueue %d concurrency-locked task(s) for shard %s: %s",
            len(released_task_ids),
            redis_queue.pack_id,
            exc,
        )
        return 0

    logger.warning(
        "[Bridge] Released %d due concurrency-locked task(s) on shard %s.",
        len(released_task_ids),
        redis_queue.pack_id,
    )
    return len(released_task_ids)
