"""IG Auto-Resume Handler -- on_fail lifecycle hook tool.

Invoked via lifecycle_hooks.on_fail declared in ig_analyze_following.json.
Handles retry logic, risk signal detection, and follow-up task creation
for IG browser automation executions.
"""

import logging
import os
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        v = int(raw)
        return v if v > 0 else default
    except Exception:
        return default


def _extract_target_username(task_ctx: Optional[Dict[str, Any]]) -> Optional[str]:
    """Extract target username from execution context inputs."""
    if not isinstance(task_ctx, dict):
        return None
    inputs = task_ctx.get("inputs")
    if not isinstance(inputs, dict):
        return None
    for key in ("target_username", "seed", "handle"):
        val = inputs.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def _get_risk_cooldown_seconds() -> int:
    """Random cooldown between min and max to avoid predictable retry patterns."""
    min_s = _env_int("IG_RISK_COOLDOWN_MIN_SECONDS", 3600)
    max_s = _env_int("IG_RISK_COOLDOWN_MAX_SECONDS", 21600)
    if max_s < min_s:
        max_s = min_s
    if max_s == min_s:
        return min_s
    return random.randint(min_s, max_s)


def _recent_ig_risk_signal(target_username: Optional[str]) -> Optional[Dict[str, Any]]:
    """Check for recent IG risk signals (rate limiting, challenges, etc.)."""
    if not target_username:
        return None
    try:
        from backend.app.services.stores.tasks_store import TasksStore
        from sqlalchemy import text

        tasks_store = TasksStore()
        with tasks_store.get_connection() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT updated_at,
                           content::jsonb->'progress'->>'error_type' AS error_type,
                           content::jsonb->'progress'->>'error_message' AS error_message,
                           content::jsonb->'progress'->>'stage' AS stage
                    FROM artifacts
                    WHERE playbook_code = 'ig_analyze_following'
                      AND content IS NOT NULL
                      AND content::jsonb->'metadata'->>'target_username' = :target
                      AND (
                        (content::jsonb->'progress'->>'error_type') IN ('rate_limited','challenge_required','login_required')
                        OR (content::jsonb->'progress'->>'stage') = 'blocked'
                        OR (content::jsonb->'progress'->>'error_message') ILIKE '%try again later%'
                        OR (content::jsonb->'progress'->>'error_message') ILIKE '%risk signal%'
                        OR (content::jsonb->'progress'->>'error_message') ILIKE '%we restrict%'
                      )
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """
                ),
                {"target": target_username},
            ).fetchone()
    except Exception as e:
        logger.debug(f"IG risk signal lookup failed: {e}")
        return None

    if not row:
        return None
    mapping = row._mapping if hasattr(row, "_mapping") else row
    updated_at = mapping.get("updated_at") if isinstance(mapping, dict) else row[0]
    if not isinstance(updated_at, datetime):
        return None
    return {
        "updated_at": updated_at,
        "error_type": (
            mapping.get("error_type") if isinstance(mapping, dict) else row[1]
        ),
        "error_message": (
            mapping.get("error_message") if isinstance(mapping, dict) else row[2]
        ),
        "stage": mapping.get("stage") if isinstance(mapping, dict) else row[3],
    }


def ig_auto_resume_handler(
    task_id: str,
    workspace_id: str,
    failure_reason: str = "",
    execution_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Handle IG task failure with auto-resume logic.

    This is the on_fail lifecycle hook entry point. It:
    1. Checks retry count against max retries
    2. Checks for IG risk signals (rate limiting, challenges)
    3. If safe, creates a follow-up visit-only task for partial resume
    4. Returns result indicating what action was taken

    Args:
        task_id: The failed task's ID
        workspace_id: Workspace ID
        failure_reason: Why the task failed
        execution_context: The full execution context from the failed task
    """
    ctx = execution_context or {}
    result = {"action": "none", "task_id": task_id}

    try:
        from backend.app.models.workspace import Task, TaskStatus
        from backend.app.services.stores.tasks_store import TasksStore

        tasks_store = TasksStore()

        # Get the original task
        task = tasks_store.get_task(task_id)
        if not task:
            result["error"] = f"Task {task_id} not found"
            return result

        # Refresh context from the actual task (may have been updated by runner)
        current_ctx = (
            task.execution_context if isinstance(task.execution_context, dict) else {}
        )
        current_ctx = dict(current_ctx)

        # Check retry count
        retry_count = current_ctx.get("auto_resume_count", 0)
        max_retries = _env_int("IG_AUTO_RESUME_MAX_RETRIES", 3)
        if retry_count >= max_retries:
            logger.info(
                f"Auto-resume skipped for task {task_id}: "
                f"retry_count={retry_count} >= max={max_retries}"
            )
            result["action"] = "skip_max_retries"
            result["retry_count"] = retry_count
            tasks_store.update_task(
                task.id,
                execution_context=current_ctx,
                status=TaskStatus.FAILED,
                completed_at=_utc_now(),
                error=f"{failure_reason} (Auto-resume skipped: max retries reached)",
            )
            return result

        # Risk cooldown guard
        target_username = _extract_target_username(current_ctx)
        cooldown_until_str = current_ctx.get("ig_risk_cooldown_until")
        if cooldown_until_str:
            try:
                cooldown_until = datetime.fromisoformat(cooldown_until_str)
                if _utc_now() < cooldown_until:
                    current_ctx["auto_resume_suppressed"] = True
                    current_ctx["auto_resume_suppressed_reason"] = (
                        "ig_risk_cooldown_active"
                    )
                    tasks_store.update_task(
                        task.id, 
                        execution_context=current_ctx,
                        status=TaskStatus.FAILED,
                        completed_at=_utc_now(),
                        error=f"{failure_reason} (Auto-resume suppressed: cooldown active)"
                    )
                    result["action"] = "skip_cooldown"
                    return result
            except Exception:
                pass

        # Check for recent risk signals
        risk = _recent_ig_risk_signal(target_username)
        if risk:
            now_utc = _utc_now()
            risk_time = risk.get("updated_at")
            if isinstance(risk_time, datetime):
                max_s = _env_int("IG_RISK_COOLDOWN_MAX_SECONDS", 21600)
                if risk_time >= (now_utc - timedelta(seconds=max_s)):
                    cooldown_seconds = _get_risk_cooldown_seconds()
                    cooldown_until_ts = _utc_now() + timedelta(seconds=cooldown_seconds)
                    current_ctx["auto_resume_suppressed"] = True
                    current_ctx["auto_resume_suppressed_reason"] = "ig_risk_signal"
                    current_ctx["ig_risk_detected_at"] = risk_time.isoformat()
                    current_ctx["ig_risk_error_type"] = risk.get("error_type")
                    current_ctx["ig_risk_error_message"] = risk.get("error_message")
                    current_ctx["ig_risk_cooldown_until"] = (
                        cooldown_until_ts.isoformat()
                    )
                    tasks_store.update_task(
                        task.id, 
                        execution_context=current_ctx,
                        status=TaskStatus.FAILED,
                        completed_at=_utc_now(),
                        error=f"{failure_reason} (Auto-resume suppressed: recent IG risk signal)"
                    )
                    logger.warning(
                        f"Auto-resume suppressed for task {task_id} due to IG risk "
                        f"signal (target={target_username}, "
                        f"cooldown_until={current_ctx['ig_risk_cooldown_until']})"
                    )
                    result["action"] = "skip_risk_signal"
                    return result

        # Mark CURRENT task as failed with resume note
        current_ctx["auto_resumed"] = True
        resume_error = f"{failure_reason} (auto-resume #{retry_count + 1} queued)"
        tasks_store.update_task(
            task.id,
            execution_context=current_ctx,
            status=TaskStatus.FAILED,
            completed_at=_utc_now(),
            error=resume_error,
        )

        # Build params for the follow-up visit-only task
        original_params = task.params if isinstance(task.params, dict) else {}
        new_params = dict(original_params)
        new_params["run_mode"] = "visit"
        new_params["allow_partial_resume"] = True

        new_ctx = dict(current_ctx)
        new_ctx["auto_resume_count"] = retry_count + 1
        new_ctx["resumed_from_task_id"] = task.id
        new_ctx["status"] = "queued"
        new_ctx.pop("auto_resumed", None)
        new_ctx.pop("runner_id", None)
        new_ctx.pop("heartbeat_at", None)
        new_ctx.pop("failed_at", None)
        new_ctx.pop("error", None)
        watchdog_abort = new_ctx.pop("watchdog_abort", None)
        new_ctx.pop("watchdog_abort_requested_at", None)
        new_ctx.pop("watchdog_abort_reason", None)
        if isinstance(watchdog_abort, dict):
            new_ctx["resume_origin"] = "watchdog_abort"
            if watchdog_abort.get("reason"):
                new_ctx["resume_origin_reason"] = watchdog_abort.get("reason")

        # Inject run_mode and allow_partial_resume into inputs
        ctx_inputs = new_ctx.get("inputs", {})
        if not isinstance(ctx_inputs, dict):
            ctx_inputs = {}
        ctx_inputs = dict(ctx_inputs)
        ctx_inputs["run_mode"] = "visit"
        ctx_inputs["allow_partial_resume"] = True
        new_ctx["inputs"] = ctx_inputs

        # Create NEW follow-up task
        new_task = Task(
            id=str(uuid.uuid4()),
            workspace_id=task.workspace_id,
            message_id=getattr(task, "message_id", "") or "",
            execution_id=getattr(task, "execution_id", None),
            parent_execution_id=getattr(task, "execution_id", None),
            project_id=getattr(task, "project_id", None),
            pack_id=task.pack_id,
            task_type=getattr(task, "task_type", "playbook_execution"),
            status=TaskStatus.PENDING,
            params=new_params,
            execution_context=new_ctx,
            created_at=_utc_now(),
        )
        tasks_store.create_task(new_task)
        logger.info(
            f"Auto-resume #{retry_count + 1} queued for IG task "
            f"{task.id} -> new task {new_task.id}"
        )

        result["action"] = "auto_resumed"
        result["new_task_id"] = new_task.id
        result["retry_count"] = retry_count + 1
        return result

    except Exception as e:
        logger.warning(f"ig_auto_resume_handler failed: {e}")
        result["action"] = "error"
        result["error"] = str(e)
        return result
