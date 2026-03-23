import logging
import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional, Any, Dict

from fastapi import (
    APIRouter,
    HTTPException,
    Path as PathParam,
    Query,
    Body,
    Request,
)
from pydantic import BaseModel, Field

from ....services.mindscape_store import MindscapeStore
from ....services.queue_position_cache import QUEUE_CACHE as _QUEUE_CACHE
from ....services.stores.tasks_store import TasksStore
from ....services.stores.task_feedback_store import TaskFeedbackStore
from ..execution_ordering import build_execution_order_clause
from ....models.workspace import (
    TaskFeedback,
    TaskFeedbackAction,
    TaskFeedbackReasonCode,
)
from ....services.task_status_fix import TaskStatusFixService
from ....services.remote_step_resend_service import (
    extract_remote_step_resend_payload,
    resend_remote_workflow_step_child_task,
)
from ....services.task_execution_projection import (
    build_execution_group_summary,
    project_execution_for_api,
)
from ..execution_dispatch import get_or_create_cloud_connector

router = APIRouter()
logger = logging.getLogger(__name__)
store = MindscapeStore()


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
    return {
        "state": "deferred",
        "reason": admission_ctx.get("reason"),
        "defer_until": admission_ctx.get("defer_until"),
        "visibility": admission_ctx.get("visibility"),
        "producer_kind": admission_ctx.get("producer_kind"),
        "queue_shard": admission_ctx.get("queue_shard") or getattr(task_obj, "queue_shard", None),
    }


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
                        _row = _conn.execute(
                            _text(
                                "SELECT content::jsonb->'progress' AS p "
                                "FROM artifacts "
                                "WHERE execution_id = :eid "
                                "AND content::jsonb ? 'progress' "
                                "ORDER BY updated_at DESC LIMIT 1"
                            ),
                            {"eid": execution_id},
                        ).fetchone()
                        if _row and _row[0]:
                            progress = (
                                _row[0]
                                if isinstance(_row[0], dict)
                                else json.loads(_row[0])
                            )
                            if isinstance(progress, dict):
                                last_known_progress = progress
                            loops_since_artifact_poll = 0
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
                "heartbeat_at": ctx.get("heartbeat_at"),
                "runner_id": ctx.get("runner_id"),
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


@router.get("/{workspace_id}/tasks")
async def get_workspace_tasks(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of tasks"),
    include_completed: bool = Query(False, description="Include completed tasks"),
):
    """Get tasks for a workspace"""
    try:
        tasks_store = TasksStore()

        if include_completed:
            # Always include running tasks first — they must never be cut off
            # by ORDER BY created_at DESC LIMIT even if they were created long ago.
            running = await asyncio.to_thread(tasks_store.list_running_tasks, workspace_id)
            remaining_limit = max(0, limit - len(running))
            rest = await asyncio.to_thread(
                tasks_store.list_tasks_by_workspace, workspace_id, limit=remaining_limit
            )
            running_ids = {t.id for t in running}
            all_tasks = running + [t for t in rest if t.id not in running_ids]
        else:
            pending = await asyncio.to_thread(tasks_store.list_pending_tasks, workspace_id)
            running = await asyncio.to_thread(tasks_store.list_running_tasks, workspace_id)
            all_tasks = (pending + running)[:limit]

        return {"tasks": [task.model_dump() for task in all_tasks]}
    except Exception as e:
        logger.error(f"Failed to get workspace tasks: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{workspace_id}/executions")
async def get_workspace_executions(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    limit: int = Query(30, ge=1, le=200, description="Maximum number of executions"),
    playbook_code_prefix: Optional[str] = Query(
        None, description="Filter by playbook code prefix (e.g., 'ig_')"
    ),
    playbook_code: Optional[str] = Query(
        None, description="Filter by exact playbook code"
    ),
    parent_execution_id: Optional[str] = Query(
        None,
        description="Filter child executions by exact parent execution ID",
    ),
    order_by: str = Query("created_at", description="Field to order by"),
    order: str = Query("desc", description="Sort order: asc or desc"),
    include_execution_context: bool = Query(
        False,
        description=(
            "Include full execution_context payload. "
            "Default false returns a trimmed context to avoid oversized list payloads."
        ),
    ),
    group_by_parent: bool = Query(
        False, description="Group results by parent_execution_id"
    ),
):
    """List executions (tasks) for a workspace with optional playbook filters."""
    try:
        from sqlalchemy import text

        tasks_store = TasksStore()

        query_parts = [
            """
            SELECT
                id,
                workspace_id,
                message_id,
                execution_id,
                parent_execution_id,
                project_id,
                pack_id,
                task_type,
                status,
                params,
                result,
                CASE
                    WHEN :include_execution_context THEN execution_context
                    WHEN execution_context IS NULL THEN NULL
                    ELSE (
                        execution_context::jsonb
                        - 'result'
                        - 'workflow_result'
                        - 'step_outputs'
                        - 'outputs'
                    )::json
                END AS execution_context,
                storyline_tags,
                created_at,
                started_at,
                completed_at,
                error
            FROM tasks
            WHERE workspace_id = :workspace_id
            """
        ]
        params: dict = {
            "workspace_id": workspace_id,
            "include_execution_context": include_execution_context,
        }

        if playbook_code:
            query_parts.append("AND pack_id = :pack_id")
            params["pack_id"] = playbook_code
        elif playbook_code_prefix:
            query_parts.append("AND pack_id LIKE :pack_prefix")
            params["pack_prefix"] = f"{playbook_code_prefix}%"

        if parent_execution_id:
            query_parts.append("AND parent_execution_id = :parent_execution_id")
            params["parent_execution_id"] = parent_execution_id

        # Active executions must sort ahead of older completed history even when
        # the response is grouped by parent, otherwise live runs disappear from
        # the top-card data source once newer pending child tasks arrive.
        query_parts.append(build_execution_order_clause(order_by, order))

        query_parts.append("LIMIT :limit")
        params["limit"] = limit

        def _fetch_executions():
            with tasks_store.get_connection() as conn:
                rows = conn.execute(text(" ".join(query_parts)), params).fetchall()
                return [tasks_store._row_to_task(row) for row in rows]

        tasks = await asyncio.to_thread(_fetch_executions)

        # Refresh queue cache for position data
        _QUEUE_CACHE.refresh_if_stale(tasks_store)

        # Enrich with fields the UI expects (RunLogCard reads playbook_code, not pack_id)
        executions = []
        for task in tasks:
            task_payload = task.model_dump()
            executions.append(
                project_execution_for_api(
                    task_payload,
                    queue_position=_QUEUE_CACHE.get_position(tasks_store, task),
                    queue_total=_QUEUE_CACHE.get_total(
                        task_payload.get("queue_shard") or "default"
                    ),
                )
            )

        if group_by_parent:
            groups = {}
            ungrouped = []
            for d in executions:
                pid = d.get("parent_execution_id")
                if pid:
                    groups.setdefault(pid, []).append(d)
                else:
                    ungrouped.append(d)
            
            group_summaries = []
            for pid, tasks_list in groups.items():
                group_summaries.append({
                    "parent_execution_id": pid,
                    "tasks": tasks_list,
                    "summary": build_execution_group_summary(tasks_list),
                })
            return {"groups": group_summaries, "ungrouped": ungrouped}

        return {"executions": executions}
    except Exception as e:
        logger.error(f"Failed to get workspace executions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{workspace_id}/executions/{execution_id}/progress-snapshot")
async def get_execution_progress_snapshot(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    execution_id: str = PathParam(..., description="Execution ID"),
):
    """
    Return a lightweight progress snapshot for one execution.

    This endpoint avoids returning full artifact `content` payloads while still exposing
    the latest `progress` object and metadata needed by UI status/debug cards.
    """
    import json
    from sqlalchemy import text

    def _to_json(value: Any, default: Any = None):
        if value is None:
            return default
        if isinstance(value, (dict, list, int, float, bool)):
            return value
        if isinstance(value, str):
            try:
                return json.loads(value)
            except Exception:
                return default
        return default

    try:
        tasks_store = TasksStore()
        task = tasks_store.get_task_by_execution_id(execution_id)
        if not task:
            task = tasks_store.get_task(execution_id)
        if not task:
            raise HTTPException(status_code=404, detail="Execution not found")
        if task.workspace_id != workspace_id:
            raise HTTPException(
                status_code=403, detail="Execution does not belong to this workspace"
            )

        artifact_id = None
        artifact_updated_at = None
        progress = None
        artifact_metadata = {}
        content_metadata = {}

        # Fast path (Postgres JSON extraction): read only progress + metadata, not full content blob.
        try:
            with tasks_store.get_connection() as conn:
                row = conn.execute(
                    text(
                        """
                        SELECT
                            id,
                            updated_at,
                            created_at,
                            metadata,
                            content::jsonb->'progress' AS progress,
                            content::jsonb->'metadata' AS content_metadata
                        FROM artifacts
                        WHERE workspace_id = :workspace_id
                          AND execution_id = :execution_id
                          AND content IS NOT NULL
                          AND content::jsonb ? 'progress'
                        ORDER BY updated_at DESC
                        LIMIT 1
                        """
                    ),
                    {"workspace_id": workspace_id, "execution_id": execution_id},
                ).fetchone()
            if row:
                artifact_id = str(row.id)
                ts = row.updated_at or row.created_at
                artifact_updated_at = ts.isoformat() if ts else None
                progress = _to_json(row.progress, {})
                artifact_metadata = _to_json(row.metadata, {}) or {}
                content_metadata = _to_json(row.content_metadata, {}) or {}
        except Exception:
            # Fallback: use store-level artifact read if DB JSON operators aren't available.
            artifact = store.artifacts.get_by_execution_id(execution_id)
            if artifact and artifact.workspace_id == workspace_id:
                content = artifact.content or {}
                artifact_id = artifact.id
                ts = artifact.updated_at or artifact.created_at
                artifact_updated_at = ts.isoformat() if ts else None
                artifact_metadata = artifact.metadata or {}
                if isinstance(content, dict):
                    p = content.get("progress")
                    progress = p if isinstance(p, dict) else {}
                    cm = content.get("metadata")
                    content_metadata = cm if isinstance(cm, dict) else {}

        ctx = task.execution_context if isinstance(task.execution_context, dict) else {}

        # Refresh queue cache for position data
        _QUEUE_CACHE.refresh_if_stale(tasks_store)

        return {
            "workspace_id": workspace_id,
            "execution_id": execution_id,
            "task_status": task.status,
            "artifact_id": artifact_id,
            "artifact_updated_at": artifact_updated_at,
            "progress": progress if isinstance(progress, dict) else None,
            "queue_position": _QUEUE_CACHE.get_position(tasks_store, task),
            "queue_total": _QUEUE_CACHE.get_total(task.queue_shard or "default"),
            "blocked_reason": task.blocked_reason,
            "blocked_payload": task.blocked_payload,
            "frontier_state": task.frontier_state,
            "next_eligible_at": (
                task.next_eligible_at.isoformat() if task.next_eligible_at else None
            ),
            "admission_state": _build_admission_state(task, ctx),
            "artifact_metadata": artifact_metadata,
            "content_metadata": content_metadata,
            "execution_context": {
                "heartbeat_at": ctx.get("heartbeat_at"),
                "runner_id": ctx.get("runner_id"),
                "execution_backend_hint": ctx.get("execution_backend_hint"),
                "inputs": ctx.get("inputs") if isinstance(ctx.get("inputs"), dict) else {},
                "dependency_hold": ctx.get("dependency_hold"),
                "admission_policy": (
                    ctx.get("admission_policy")
                    if isinstance(ctx.get("admission_policy"), dict)
                    else None
                ),
                "admission": ctx.get("admission") if isinstance(ctx.get("admission"), dict) else None,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to get execution progress snapshot for {execution_id}: {e}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{workspace_id}/executions/{execution_id}/stream")
async def stream_execution_events(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    execution_id: str = PathParam(..., description="Execution ID"),
    request: Request = None,
):
    """SSE stream for execution progress events.

    For completed/failed/cancelled tasks: sends stream_end immediately.
    For running tasks: sends heartbeat events until completion.
    """
    from starlette.responses import StreamingResponse

    state, queue = await _subscribe_execution_stream(workspace_id, execution_id)

    async def event_generator():
        try:
            while True:
                if request and await request.is_disconnected():
                    return
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=5)
                except asyncio.TimeoutError:
                    continue
                except asyncio.CancelledError:
                    return

                yield f"data: {payload}\n\n"

                try:
                    parsed = json.loads(payload)
                except Exception:
                    parsed = {}
                if parsed.get("type") == "stream_end":
                    return
        finally:
            await _unsubscribe_execution_stream(execution_id, state, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


class RejectTaskRequest(BaseModel):
    """Request model for rejecting a task"""

    reason_code: Optional[str] = Field(None, description="Rejection reason code")
    comment: Optional[str] = Field(
        None, description="Optional comment explaining rejection"
    )


class ResendRemoteStepTaskRequest(BaseModel):
    """Request model for resending a remote workflow step child task."""

    target_device_id: Optional[str] = Field(
        None,
        description="Optional override target GPU VM / executor device ID",
    )


@router.post("/{workspace_id}/tasks/{task_id}/reject")
async def reject_task(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    task_id: str = PathParam(..., description="Task ID"),
    request: RejectTaskRequest = Body(...),
):
    """Reject a task"""
    try:
        tasks_store = TasksStore()
        feedback_store = PostgresTaskFeedbackStore()

        task = tasks_store.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        if task.workspace_id != workspace_id:
            raise HTTPException(
                status_code=403, detail="Task does not belong to this workspace"
            )

        reason_code_enum = None
        if request.reason_code:
            try:
                reason_code_enum = TaskFeedbackReasonCode(request.reason_code)
            except ValueError:
                logger.warning(f"Invalid reason_code: {request.reason_code}")

        feedback = TaskFeedback(
            id=str(uuid.uuid4()),
            task_id=task_id,
            workspace_id=workspace_id,
            user_id="default-user",
            action=TaskFeedbackAction.REJECT,
            reason_code=reason_code_enum,
            comment=request.comment,
        )

        feedback_store.create_feedback(feedback)

        return {
            "success": True,
            "message": "Task rejected successfully",
            "feedback_id": feedback.id,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to reject task: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{workspace_id}/tasks/{task_id}/cancel")
async def cancel_task(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    task_id: str = PathParam(..., description="Task ID"),
):
    """Cancel a pending or running task"""
    try:
        tasks_store = TasksStore()
        task = tasks_store.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        if task.workspace_id != workspace_id:
            raise HTTPException(
                status_code=403, detail="Task does not belong to this workspace"
            )

        success = tasks_store.cancel_task(task_id)
        if not success:
            raise HTTPException(
                status_code=409,
                detail=f"Task cannot be cancelled (status: {task.status})",
            )
        return {"success": True, "message": "Task cancelled"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel task: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{workspace_id}/tasks/{task_id}/resend-remote-step")
async def resend_remote_step_task(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    task_id: str = PathParam(..., description="Task ID"),
    request: Optional[ResendRemoteStepTaskRequest] = Body(None),
):
    """Resend a remote workflow-step child task using its stored request payload."""
    try:
        tasks_store = TasksStore()
        task = tasks_store.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        if task.workspace_id != workspace_id:
            raise HTTPException(
                status_code=403, detail="Task does not belong to this workspace"
            )

        extract_remote_step_resend_payload(task, workspace_id=workspace_id)
        connector = get_or_create_cloud_connector()
        if connector is None:
            raise HTTPException(
                status_code=503,
                detail="Cloud Connector not available for remote step resend",
            )
        return await resend_remote_workflow_step_child_task(
            task=task,
            workspace_id=workspace_id,
            connector=connector,
            target_device_id=request.target_device_id if request else None,
        )
    except HTTPException:
        raise
    except ValueError as e:
        status_code = 503 if "Cloud Connector" in str(e) else 409
        raise HTTPException(status_code=status_code, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to resend remote step task: {e}", exc_info=True)
        raise HTTPException(status_code=502, detail=f"Cloud dispatch failed: {e}")


@router.post("/{workspace_id}/fix-task-status")
async def fix_task_status(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    create_timeline_items: bool = Query(
        True, description="Create timeline items for fixed tasks"
    ),
    limit: Optional[int] = Query(None, description="Maximum number of tasks to fix"),
):
    """
    Fix tasks with inconsistent status and reap zombie tasks.

    Finds and fixes tasks where:
    - task.status = "running" but execution_context.status = "completed" or "failed"
    - task.status = "running" but heartbeat is stale (zombie reaper)

    This happens when PlaybookRunExecutor didn't properly update task status,
    or when a runner crashes without marking the task as failed.
    """
    try:
        fix_service = TaskStatusFixService()
        result = fix_service.fix_all_inconsistent_tasks(
            workspace_id=workspace_id,
            create_timeline_items=create_timeline_items,
            limit=limit,
        )

        # Also run zombie reaper
        tasks_store = TasksStore()
        reaped_ids = tasks_store.reap_zombie_tasks()
        result["zombie_tasks_reaped"] = len(reaped_ids)
        result["zombie_task_ids"] = reaped_ids

        return result
    except Exception as e:
        logger.error(f"Failed to fix task status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
