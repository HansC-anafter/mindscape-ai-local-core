"""No-progress watchdog checks for runner tasks."""

from __future__ import annotations

import json
import logging
import os
from datetime import timedelta, timezone
from typing import Any, Optional

from backend.app.services.stores.tasks_store import TasksStore
from backend.app.runner.reaper_context import (
    _heartbeat_log_value,
    _task_heartbeat_at,
)
from backend.app.runner.utils import _env_int, _parse_utc_iso, _utc_now

logger = logging.getLogger("backend.app.runner.reaper")

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
