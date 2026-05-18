import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from backend.app.models.workspace import TaskStatus
from backend.app.services.json_safety import json_value_without_nul
from backend.app.services.queue_position_cache import QUEUE_CACHE as _QUEUE_CACHE
from backend.app.services.stores.tasks_store import TasksStore

logger = logging.getLogger(__name__)


@dataclass
class _ExecutionStreamState:
    subscribers: set = field(default_factory=set)  # set[asyncio.Queue[str]]
    poller_task: Optional[asyncio.Task] = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    stop_requested: bool = False
    last_progress_signature: Optional[str] = None
    last_payload: Optional[str] = None
    last_emit_monotonic: float = 0.0


_STREAM_STATES: dict[str, _ExecutionStreamState] = {}
_STREAM_STATES_LOCK = asyncio.Lock()


async def _get_or_create_stream_state(execution_id: str) -> _ExecutionStreamState:
    async with _STREAM_STATES_LOCK:
        state = _STREAM_STATES.get(execution_id)
        if state is None:
            state = _ExecutionStreamState()
            _STREAM_STATES[execution_id] = state
        return state


def _enqueue_event(queue: asyncio.Queue, payload: str) -> None:
    try:
        queue.put_nowait(payload)
    except asyncio.QueueFull:
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
        try:
            queue.put_nowait(payload)
        except asyncio.QueueFull:
            # If queue remains full, skip this event for that subscriber.
            pass


async def _broadcast_to_subscribers(state: _ExecutionStreamState, payload: str) -> None:
    async with state.lock:
        subscribers = list(state.subscribers)
    for q in subscribers:
        _enqueue_event(q, payload)


async def _cleanup_stream_state_if_idle(execution_id: str, state: _ExecutionStreamState) -> None:
    async with state.lock:
        should_cleanup = not state.subscribers and state.poller_task is None
    if not should_cleanup:
        return
    async with _STREAM_STATES_LOCK:
        if _STREAM_STATES.get(execution_id) is state:
            _STREAM_STATES.pop(execution_id, None)


def _build_terminal_payload(task_obj: Any) -> str:
    failed_statuses = {"failed", "cancelled", "cancelled_by_user", "expired", "FAILED"}
    ctx = task_obj.execution_context if isinstance(task_obj.execution_context, dict) else {}
    raw = (task_obj.status or "").lower().replace(" ", "_")
    if raw in failed_statuses or task_obj.status in failed_statuses:
        return json.dumps(
            {
                "type": "execution_error",
                "error": ctx.get("error") or f"Execution {raw}",
                "status": task_obj.status,
                "execution_context": ctx,
            }
        )
    return json.dumps(
        {
            "type": "execution_complete",
            "status": task_obj.status,
            "execution_context": ctx,
        }
    )


def _build_admission_state(task_obj: Any, ctx: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    blocked_reason = getattr(task_obj, "blocked_reason", None)
    if blocked_reason != "admission_deferred":
        return None

    admission_ctx = ctx.get("admission") if isinstance(ctx.get("admission"), dict) else {}
    blocked_payload = (
        getattr(task_obj, "blocked_payload", None)
        if isinstance(getattr(task_obj, "blocked_payload", None), dict)
        else {}
    )
    return {
        "state": "deferred",
        "reason": admission_ctx.get("reason") or blocked_payload.get("reason"),
        "defer_until": admission_ctx.get("defer_until")
        or blocked_payload.get("defer_until")
        or (
            task_obj.next_eligible_at.isoformat()
            if getattr(task_obj, "next_eligible_at", None)
            else None
        ),
        "visibility": admission_ctx.get("visibility")
        or blocked_payload.get("visibility"),
        "producer_kind": admission_ctx.get("producer_kind")
        or blocked_payload.get("producer_kind"),
        "queue_shard": admission_ctx.get("queue_shard")
        or blocked_payload.get("queue_shard")
        or getattr(task_obj, "queue_shard", None),
    }


def _extract_artifact_progress_from_content(content: Any) -> tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    content_json = json_value_without_nul(content, {})
    if not isinstance(content_json, dict):
        return None, {}

    progress = content_json.get("progress")
    content_metadata = content_json.get("metadata")
    return (
        progress if isinstance(progress, dict) else None,
        content_metadata if isinstance(content_metadata, dict) else {},
    )


async def _execution_stream_poller(
    workspace_id: str, execution_id: str, state: _ExecutionStreamState
) -> None:
    tasks_store = TasksStore()
    failed_statuses = {"failed", "cancelled", "cancelled_by_user", "expired", "FAILED"}
    completed_statuses = {"completed", "succeeded", "SUCCEEDED"}
    terminal_statuses = failed_statuses | completed_statuses

    artifact_progress_poll_stride = 3  # 3 loops * 3s = ~9s
    loops_since_artifact_poll = artifact_progress_poll_stride
    last_known_progress = None
    heartbeat_interval_s = 15.0

    try:
        while True:
            async with state.lock:
                if state.stop_requested or not state.subscribers:
                    break

            task = tasks_store.get_task_by_execution_id(execution_id)
            if not task:
                task = tasks_store.get_task(execution_id)
            if not task or task.workspace_id != workspace_id:
                await _broadcast_to_subscribers(
                    state,
                    json.dumps({"type": "execution_error", "error": "Execution not found"}),
                )
                await _broadcast_to_subscribers(
                    state,
                    json.dumps(
                        {
                            "type": "stream_end",
                            "reason": "not_found",
                            "terminal": True,
                        }
                    ),
                )
                break

            status = (task.status or "").lower().replace(" ", "_")
            if status in terminal_statuses or task.status in terminal_statuses:
                await _broadcast_to_subscribers(state, _build_terminal_payload(task))
                await _broadcast_to_subscribers(
                    state,
                    json.dumps(
                        {
                            "type": "stream_end",
                            "reason": "terminal",
                            "terminal": True,
                        }
                    ),
                )
                break

            ctx = task.execution_context if isinstance(task.execution_context, dict) else {}
            progress = ctx.get("progress") if isinstance(ctx, dict) else None

            if isinstance(progress, dict):
                last_known_progress = progress
                loops_since_artifact_poll = 0
            else:
                loops_since_artifact_poll += 1

            if not progress and loops_since_artifact_poll >= artifact_progress_poll_stride:
                try:
                    from sqlalchemy import text as _text

                    with tasks_store.get_connection() as _conn:
                        _rows = _conn.execute(
                            _text(
                                "SELECT content "
                                "FROM artifacts "
                                "WHERE workspace_id = :workspace_id "
                                "AND execution_id = :eid "
                                "AND content IS NOT NULL "
                                "ORDER BY updated_at DESC LIMIT 5"
                            ),
                            {
                                "workspace_id": workspace_id,
                                "eid": execution_id,
                            },
                        ).fetchall()
                        for _row in _rows:
                            progress, _content_metadata = _extract_artifact_progress_from_content(
                                _row[0]
                            )
                            if isinstance(progress, dict):
                                last_known_progress = progress
                                loops_since_artifact_poll = 0
                                break
                except Exception:
                    pass

            if not progress:
                progress = last_known_progress

            # Refresh queue cache (shared, max once per 3s across all pollers)
            _QUEUE_CACHE.refresh_if_stale(tasks_store)

            payload_obj = {
                "type": "progress",
                "status": task.status,
                "progress": progress,
                "queue_position": _QUEUE_CACHE.get_position(tasks_store, task),
                "queue_total": _QUEUE_CACHE.get_total(task.queue_shard or "default"),
                "blocked_reason": task.blocked_reason,
                "blocked_payload": task.blocked_payload,
                "frontier_state": task.frontier_state,
                "next_eligible_at": (
                    task.next_eligible_at.isoformat() if task.next_eligible_at else None
                ),
                "admission_state": _build_admission_state(task, ctx),
                "dependency_hold": ctx.get("dependency_hold"),
                "heartbeat_at": (
                    task.heartbeat_at.isoformat()
                    if getattr(task, "heartbeat_at", None)
                    else (
                        ctx.get("heartbeat_at")
                        if task.status == TaskStatus.RUNNING
                        else None
                    )
                ),
                "runner_id": getattr(task, "runner_id", None)
                or (ctx.get("runner_id") if task.status == TaskStatus.RUNNING else None),
            }
            payload = json.dumps(payload_obj)
            signature = json.dumps(payload_obj, sort_keys=True, default=str)
            now = time.monotonic()

            should_emit = False
            async with state.lock:
                if signature != state.last_progress_signature:
                    should_emit = True
                    state.last_progress_signature = signature
                elif (now - state.last_emit_monotonic) >= heartbeat_interval_s:
                    should_emit = True
                if should_emit:
                    state.last_payload = payload
                    state.last_emit_monotonic = now

            if should_emit:
                await _broadcast_to_subscribers(state, payload)

            await asyncio.sleep(3)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(
            f"Execution stream poller crashed for {execution_id}: {e}",
            exc_info=True,
        )
        await _broadcast_to_subscribers(
            state,
            json.dumps(
                {
                    "type": "execution_error",
                    "error": "Stream poller crashed",
                    "status": "failed",
                }
            ),
        )
        await _broadcast_to_subscribers(
            state,
            json.dumps(
                {"type": "stream_end", "reason": "poller_error", "terminal": False}
            ),
        )
    finally:
        async with state.lock:
            state.poller_task = None
            state.stop_requested = False
        await _cleanup_stream_state_if_idle(execution_id, state)


async def _subscribe_execution_stream(
    workspace_id: str, execution_id: str
) -> tuple[_ExecutionStreamState, asyncio.Queue]:
    state = await _get_or_create_stream_state(execution_id)
    queue: asyncio.Queue = asyncio.Queue(maxsize=200)

    async with state.lock:
        state.subscribers.add(queue)
        if state.last_payload:
            _enqueue_event(queue, state.last_payload)
        if state.poller_task is None or state.poller_task.done():
            state.stop_requested = False
            state.poller_task = asyncio.create_task(
                _execution_stream_poller(workspace_id, execution_id, state)
            )

    return state, queue


async def _unsubscribe_execution_stream(
    execution_id: str, state: _ExecutionStreamState, queue: asyncio.Queue
) -> None:
    task_to_cancel: Optional[asyncio.Task] = None
    async with state.lock:
        state.subscribers.discard(queue)
        if not state.subscribers:
            state.stop_requested = True
            if state.poller_task and not state.poller_task.done():
                task_to_cancel = state.poller_task
    if task_to_cancel:
        task_to_cancel.cancel()
    await _cleanup_stream_state_if_idle(execution_id, state)
