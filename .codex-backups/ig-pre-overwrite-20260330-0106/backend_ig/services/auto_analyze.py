"""
Auto-analyze: Fire-and-forget background task enqueue for IG analysis pipelines.

Creates a Task record with status=PENDING. The runner worker polls and picks it up
without blocking the calling thread.

Active entry points:
  - enqueue_reference_analysis: after pinning a reference → ig_analyze_pinned_reference
  - enqueue_visit_analysis: after a successful account visit → visible
    ig_batch_pin_references(source_mode="captured_posts")
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from capabilities.ig.services.vision_runtime_policy import (
    build_reference_execution_intent,
    extract_reference_execution_intent_from_inputs,
)

logger = logging.getLogger(__name__)


def _utc_now():
    return datetime.now(timezone.utc)


def _normalize_handle(handle: Optional[str]) -> str:
    return (handle or "").lstrip("@").strip()


def _resolve_parent_execution_id(
    parent_execution_id: Optional[str],
    execution_id: str,
) -> Optional[str]:
    resolved_parent_execution_id = parent_execution_id
    if resolved_parent_execution_id:
        return resolved_parent_execution_id
    try:
        from backend.app.services.parameter_adapter.context import (
            active_parent_execution_id,
        )

        ctx_parent = active_parent_execution_id.get()
        if ctx_parent and ctx_parent != execution_id:
            return ctx_parent
    except Exception:
        pass
    return resolved_parent_execution_id


def _load_parent_reference_execution_intent(
    parent_execution_id: Optional[str],
) -> Optional[Dict[str, Any]]:
    if not parent_execution_id:
        return None

    try:
        from backend.app.services.stores.tasks_store import TasksStore

        task = TasksStore().get_task_by_execution_id(parent_execution_id)
        ctx = getattr(task, "execution_context", None) or {}
        if not isinstance(ctx, dict):
            return None
        inputs = ctx.get("inputs") or {}
        return extract_reference_execution_intent_from_inputs(inputs)
    except Exception:
        logger.debug(
            "[auto_analyze] Failed to load parent reference execution intent",
            exc_info=True,
        )
        return None


def _build_reference_analysis_inputs(
    *,
    workspace_id: str,
    reference_id: str,
    image_url: str,
    source_handle: Optional[str],
    analysis_profile: str,
    workload_execution_intent: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    inputs: Dict[str, Any] = {
        "workspace_id": workspace_id,
        "reference_id": reference_id,
        "image_url": image_url,
        "source_handle": source_handle or "",
        "analysis_profile": analysis_profile,
    }
    inputs["workload_execution_intent"] = (
        dict(workload_execution_intent)
        if isinstance(workload_execution_intent, dict)
        else build_reference_execution_intent(workspace_id=workspace_id)
    )
    return inputs


def _build_admission_policy(
    *,
    visibility: str,
    producer_kind: str,
) -> Dict[str, str]:
    return {
        "mode": "auto",
        "visibility": visibility,
        "producer_kind": producer_kind,
    }


def _build_reference_analysis_execution_context(
    *,
    execution_id: str,
    workspace_id: str,
    reference_id: str,
    image_url: str,
    source_handle: Optional[str],
    analysis_profile: str,
    parent_execution_id: Optional[str],
    workload_execution_intent: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "playbook_code": "ig_analyze_pinned_reference",
        "playbook_name": "Analyze Pinned Reference",
        "execution_id": execution_id,
        "status": "pending",
        "auto_triggered": True,
        "trigger": "pin_reference",
        "admission_policy": _build_admission_policy(
            visibility="background",
            producer_kind="pin_reference",
        ),
        "concurrency": {
            "lock_scope": "playbook",
        },
        "inputs": _build_reference_analysis_inputs(
            workspace_id=workspace_id,
            reference_id=reference_id,
            image_url=image_url,
            source_handle=source_handle,
            analysis_profile=analysis_profile,
            workload_execution_intent=workload_execution_intent,
        ),
        "parent_execution_id": parent_execution_id,
        "workspace_id": workspace_id,
    }


def _resolve_reference_analysis_execution_intent(
    *,
    workspace_id: str,
    workload_execution_intent: Optional[Dict[str, Any]],
    inherited_execution_intent: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    if isinstance(workload_execution_intent, dict):
        return dict(workload_execution_intent)

    if isinstance(inherited_execution_intent, dict):
        return dict(inherited_execution_intent)

    return build_reference_execution_intent(workspace_id=workspace_id)


def _build_visit_batch_pin_execution_context(
    *,
    execution_id: str,
    workspace_id: str,
    target_handle: str,
    target_count: int,
    user_data_dir: str,
    parent_execution_id: Optional[str],
    source_handle: Optional[str],
) -> Dict[str, Any]:
    return {
        "playbook_code": "ig_batch_pin_references",
        "playbook_name": "Batch Pin References",
        "execution_id": execution_id,
        "status": "pending",
        "auto_triggered": True,
        "trigger": "after_visit",
        "admission_policy": _build_admission_policy(
            visibility="visible",
            producer_kind="after_visit",
        ),
        "concurrency": {
            "lock_key_input": "user_data_dir",
            "lock_scope": "playbook_input",
            "max_parallel": 1,
        },
        "inputs": {
            "workspace_id": workspace_id,
            "target_handle": target_handle,
            "target_count": target_count,
            "user_data_dir": user_data_dir,
            "source_mode": "captured_posts",
            "source_handle": source_handle or "",
        },
        "parent_execution_id": parent_execution_id,
        "workspace_id": workspace_id,
    }


def enqueue_reference_analysis(
    *,
    workspace_id: str,
    reference_id: str,
    image_url: str,
    source_handle: Optional[str] = None,
    analysis_profile: str = "visual_anatomy",
    parent_execution_id: Optional[str] = None,
    workload_execution_intent: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """
    Fire-and-forget: enqueue ig_analyze_pinned_reference playbook for a newly pinned reference.

    Returns execution_id if enqueued, None on failure.
    """
    try:
        from backend.app.services.stores.tasks_store import TasksStore
        from backend.app.models.workspace import Task, TaskStatus

        tasks_store = TasksStore()
        execution_id = str(uuid.uuid4())
        resolved_parent_execution_id = _resolve_parent_execution_id(
            parent_execution_id, execution_id
        )
        inherited_execution_intent = _load_parent_reference_execution_intent(
            resolved_parent_execution_id
        )
        effective_execution_intent = _resolve_reference_analysis_execution_intent(
            workspace_id=workspace_id,
            workload_execution_intent=workload_execution_intent,
            inherited_execution_intent=inherited_execution_intent,
        )

        task = Task(
            id=execution_id,
            workspace_id=workspace_id,
            message_id=str(uuid.uuid4()),
            execution_id=execution_id,
            parent_execution_id=resolved_parent_execution_id,
            pack_id="ig_analyze_pinned_reference",
            task_type="playbook_execution",
            status=TaskStatus.PENDING,
            execution_context=_build_reference_analysis_execution_context(
                execution_id=execution_id,
                workspace_id=workspace_id,
                reference_id=reference_id,
                image_url=image_url,
                source_handle=source_handle,
                analysis_profile=analysis_profile,
                parent_execution_id=resolved_parent_execution_id,
                workload_execution_intent=effective_execution_intent,
            ),
            created_at=_utc_now(),
            updated_at=_utc_now(),
        )
        tasks_store.create_task(task)
        logger.info(
            "[auto_analyze] Enqueued ig_analyze_pinned_reference "
            "execution_id=%s reference_id=%s",
            execution_id,
            reference_id,
        )
        return execution_id
    except Exception as e:
        logger.warning(
            "[auto_analyze] Failed to enqueue reference analysis (non-fatal): %s", e
        )
        return None


def enqueue_visit_analysis(
    *,
    workspace_id: str,
    target_username: str,
    source_handle: Optional[str] = None,
    user_data_dir: Optional[str] = None,
    parent_execution_id: Optional[str] = None,
    target_count: Optional[int] = None,
) -> Optional[str]:
    """
    Enqueue a visible batch-pin task that consumes already captured posts.

    This keeps after-visit follow-up on the normal task queue and run logs,
    instead of spawning a hidden secondary playbook.
    """
    normalized_target = _normalize_handle(target_username)
    if not workspace_id or not normalized_target:
        return None

    resolved_user_data_dir = (
        (user_data_dir or "").strip() or "/app/data/ig-browser-profiles/default"
    )
    resolved_target_count = max(1, int(target_count or 12))

    try:
        from sqlalchemy import text
        from backend.app.models.workspace import Task, TaskStatus
        from backend.app.services.stores.tasks_store import TasksStore
        from capabilities.ig.tools.ig_batch_pin_tool import (
            _get_existing_reference_shortcodes,
        )

        existing_reference_count = len(
            _get_existing_reference_shortcodes(workspace_id, normalized_target)
        )
        if existing_reference_count >= resolved_target_count:
            logger.info(
                "[auto_analyze] Skip after-visit batch pin for @%s — "
                "existing references already satisfy target_count=%s",
                normalized_target,
                resolved_target_count,
            )
            return None

        tasks_store = TasksStore()
        with tasks_store.get_connection() as conn:
            existing = conn.execute(
                text(
                    """
                    SELECT execution_id
                    FROM tasks
                    WHERE workspace_id = :workspace_id
                      AND pack_id = 'ig_batch_pin_references'
                      AND status IN ('pending', 'running')
                      AND COALESCE(execution_context->'inputs'->>'target_handle', '') = :target_handle
                      AND COALESCE(execution_context->'inputs'->>'user_data_dir', '') = :user_data_dir
                      AND COALESCE(execution_context->'inputs'->>'target_count', '') = :target_count
                    ORDER BY created_at DESC
                    LIMIT 1
                    """
                ),
                {
                    "workspace_id": workspace_id,
                    "target_handle": normalized_target,
                    "user_data_dir": resolved_user_data_dir,
                    "target_count": str(resolved_target_count),
                },
            ).fetchone()

        if existing and existing[0]:
            logger.info(
                "[auto_analyze] Reusing existing visible batch pin task %s for @%s target_count=%s",
                existing[0],
                normalized_target,
                resolved_target_count,
            )
            return str(existing[0])

        execution_id = str(uuid.uuid4())
        resolved_parent_execution_id = _resolve_parent_execution_id(
            parent_execution_id, execution_id
        )
        task = Task(
            id=execution_id,
            workspace_id=workspace_id,
            message_id=str(uuid.uuid4()),
            execution_id=execution_id,
            parent_execution_id=resolved_parent_execution_id,
            pack_id="ig_batch_pin_references",
            task_type="playbook_execution",
            status=TaskStatus.PENDING,
            execution_context=_build_visit_batch_pin_execution_context(
                execution_id=execution_id,
                workspace_id=workspace_id,
                target_handle=normalized_target,
                target_count=resolved_target_count,
                user_data_dir=resolved_user_data_dir,
                parent_execution_id=resolved_parent_execution_id,
                source_handle=source_handle,
            ),
            created_at=_utc_now(),
            updated_at=_utc_now(),
        )
        tasks_store.create_task(task)
        logger.info(
            "[auto_analyze] Enqueued visible ig_batch_pin_references "
            "execution_id=%s target=%s source_mode=captured_posts",
            execution_id,
            normalized_target,
        )
        return execution_id
    except Exception as e:
        logger.warning(
            "[auto_analyze] Failed to enqueue visible after-visit batch pin (non-fatal): %s",
            e,
        )
        return None
