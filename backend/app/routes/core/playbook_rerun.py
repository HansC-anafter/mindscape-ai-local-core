"""
Playbook rerun endpoint.

Extracted from playbook_execution.py. Handles re-execution of a
previously completed/failed playbook by looking up the original
task's execution context and re-dispatching.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from fastapi import HTTPException, Query, Body

from .execution_schemas import RerunExecutionRequest
from .execution_shared import playbook_executor, playbook_service
from .execution_dispatch import (
    get_execution_mode,
    dispatch_remote_execution,
    resolve_and_acquire_backend,
    release_backend,
)
from .execution_hooks import (
    async_invoke_lifecycle_hook,
    async_invoke_tool_slot,
    resolve_inputs_map,
)
from .execution_metadata import resolve_runner_metadata, should_route_through_runner
from backend.app.services.runner_topology import DEFAULT_LOCAL_QUEUE_PARTITION

logger = logging.getLogger(__name__)


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


def _infer_target_username_from_artifacts(
    workspace_id: str, exec_id: str
) -> Optional[str]:
    """Infer target_username for ig_analyze_following reruns from artifact metadata."""
    try:
        from backend.app.services.stores.postgres.artifacts_store import (
            PostgresArtifactsStore,
        )

        artifacts_store = PostgresArtifactsStore()
        arts = artifacts_store.list_artifacts_by_workspace(
            workspace_id=workspace_id, limit=300
        )
        for a in arts:
            if getattr(a, "execution_id", None) != exec_id:
                continue
            if getattr(a, "playbook_code", None) != "ig_analyze_following":
                continue
            meta = a.metadata if isinstance(a.metadata, dict) else {}
            val = (meta.get("target_username") or meta.get("target_seed") or "").strip()
            if val:
                return val
            content = a.content if isinstance(a.content, dict) else {}
            cm = (
                content.get("metadata")
                if isinstance(content.get("metadata"), dict)
                else {}
            )
            val2 = (cm.get("target_username") or cm.get("target_seed") or "").strip()
            if val2:
                return val2
    except Exception:
        return None
    return None


def _normalize_rerun_spec(playbook_run) -> Dict[str, Any]:
    """Return playbook rerun metadata as a plain dict."""
    pj = getattr(playbook_run, "playbook_json", None)
    if pj is None:
        return {}

    rerun_spec = getattr(pj, "rerun", None)
    if rerun_spec is None:
        return {}
    if isinstance(rerun_spec, dict):
        return rerun_spec
    if hasattr(rerun_spec, "model_dump"):
        dumped = rerun_spec.model_dump(exclude_none=True)
        return dumped if isinstance(dumped, dict) else {}
    return {}


def _has_required_input_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _collect_missing_required_inputs(
    merged_inputs: Dict[str, Any], required_inputs: Any
) -> list[str]:
    if not isinstance(required_inputs, list):
        return []

    missing: list[str] = []
    for key in required_inputs:
        if not isinstance(key, str) or not key.strip():
            continue
        normalized_key = key.strip()
        if not _has_required_input_value(merged_inputs.get(normalized_key)):
            missing.append(normalized_key)
    return missing


def _extract_resolved_input_updates(resolver_result: Any) -> Dict[str, Any]:
    """Normalize resolver output into a flat input patch dict."""
    if isinstance(resolver_result, dict):
        nested_inputs = resolver_result.get("inputs")
        if isinstance(nested_inputs, dict):
            return nested_inputs
        return resolver_result
    return {}


async def _resolve_rerun_inputs(
    *,
    playbook_run,
    playbook_code: str,
    original_execution_id: str,
    original_execution_context: Dict[str, Any],
    workspace_id: Optional[str],
    project_id: Optional[str],
    profile_id: Optional[str],
    merged_inputs: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Backfill missing required rerun inputs via declarative resolver or legacy fallback."""
    normalized_inputs = dict(merged_inputs) if isinstance(merged_inputs, dict) else {}
    rerun_spec = _normalize_rerun_spec(playbook_run)
    required_inputs = rerun_spec.get("required_inputs") or []
    missing_inputs = _collect_missing_required_inputs(normalized_inputs, required_inputs)

    input_resolver = rerun_spec.get("input_resolver")
    if missing_inputs and isinstance(input_resolver, dict):
        tool_slot = input_resolver.get("tool_slot")
        if tool_slot:
            try:
                resolver_inputs = resolve_inputs_map(
                    input_resolver.get("inputs_map", {}),
                    normalized_inputs,
                    {
                        **original_execution_context,
                        "execution_id": original_execution_id,
                        "original_execution_id": original_execution_id,
                        "playbook_code": playbook_code,
                        "workspace_id": workspace_id,
                        "project_id": project_id,
                        "profile_id": profile_id,
                        "inputs": normalized_inputs,
                    },
                )
                resolver_result = await async_invoke_tool_slot(
                    tool_slot, resolver_inputs
                )
                resolved_updates = _extract_resolved_input_updates(resolver_result)
                if resolved_updates:
                    normalized_inputs.update(resolved_updates)
                missing_inputs = _collect_missing_required_inputs(
                    normalized_inputs, required_inputs
                )
            except Exception as exc:
                logger.warning(
                    "rerun input_resolver failed for %s execution %s: %s",
                    playbook_code,
                    original_execution_id,
                    exc,
                )

    if missing_inputs and playbook_code == "ig_analyze_following":
        workspace_id_for_infer = (workspace_id or "").strip()
        inferred = (
            _infer_target_username_from_artifacts(
                workspace_id_for_infer, original_execution_id
            )
            if workspace_id_for_infer
            else None
        )
        if inferred:
            logger.warning(
                "Using legacy ig_analyze_following rerun fallback for execution %s",
                original_execution_id,
            )
            normalized_inputs["target_username"] = inferred
            missing_inputs = _collect_missing_required_inputs(
                normalized_inputs, required_inputs
            )

    if missing_inputs:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot rerun {playbook_code}: missing required inputs "
                f"{', '.join(missing_inputs)}. "
                "Provide override_inputs or configure rerun.input_resolver."
            ),
        )

    return normalized_inputs


async def rerun_playbook_execution(
    execution_id: str,
    request: Optional[RerunExecutionRequest] = Body(None),
    execution_backend: Optional[str] = Query(
        None,
        description="Neutral execution backend hint: auto|runner|in_process. Routing is always decided by backend.",
    ),
):
    """Rerun a playbook execution using original inputs with optional overrides."""
    try:
        from backend.app.services.stores.tasks_store import TasksStore

        tasks_store = TasksStore()
        task = await asyncio.to_thread(
            tasks_store.get_task_by_execution_id, execution_id
        )
        if not task:
            raise HTTPException(status_code=404, detail="Execution not found")

        ctx = task.execution_context if isinstance(task.execution_context, dict) else {}
        playbook_code = ctx.get("playbook_code") or task.pack_id
        if not playbook_code:
            raise HTTPException(
                status_code=409, detail="Missing playbook_code for rerun"
            )

        original_inputs = ctx.get("inputs") or task.params or None
        if not isinstance(original_inputs, dict) and original_inputs is not None:
            original_inputs = None

        merged_inputs: Optional[dict] = None
        if isinstance(original_inputs, dict):
            merged_inputs = dict(original_inputs)
        if request and isinstance(request.override_inputs, dict):
            merged_inputs = merged_inputs or {}
            merged_inputs.update(request.override_inputs)

        final_execution_backend = (execution_backend or "auto").strip().lower()
        if final_execution_backend not in {"auto", "runner", "in_process", "remote"}:
            final_execution_backend = "auto"

        # Pool-aware backend selection
        final_execution_backend, pool_acquired_backend = resolve_and_acquire_backend(
            final_execution_backend
        )

        if merged_inputs is None:
            merged_inputs = {}
        if isinstance(merged_inputs, dict):
            merged_inputs["execution_backend"] = final_execution_backend

        # Ensure workspace_id and project_id are passed (executor expects them).
        workspace_id = ctx.get("workspace_id") or task.workspace_id
        project_id = ctx.get("project_id") or getattr(task, "project_id", None)
        profile_id = (
            ctx.get("profile_id") or getattr(task, "profile_id", None) or "default-user"
        )
        playbook_run = await playbook_service.load_playbook_run(
            playbook_code=playbook_code,
            locale="zh-TW",
            workspace_id=workspace_id,
        )
        merged_inputs = await _resolve_rerun_inputs(
            playbook_run=playbook_run,
            playbook_code=playbook_code,
            original_execution_id=execution_id,
            original_execution_context=ctx,
            workspace_id=workspace_id,
            project_id=project_id,
            profile_id=profile_id,
            merged_inputs=merged_inputs,
        )

        # Remote backend: dispatch rerun to cloud
        if final_execution_backend == "remote":
            try:
                return await dispatch_remote_execution(
                    playbook_code=playbook_code,
                    inputs=merged_inputs,
                    workspace_id=workspace_id,
                    profile_id=profile_id,
                )
            finally:
                release_backend(pool_acquired_backend)
        runner_metadata = resolve_runner_metadata(playbook_run)

        # If backend is configured for runner (or caller explicitly prefers runner), enqueue workflow-json playbooks.
        exec_mode = get_execution_mode()
        prefer_runner = should_route_through_runner(
            playbook_run=playbook_run,
            requested_backend=final_execution_backend,
            env_execution_mode=exec_mode,
        )
        if prefer_runner and final_execution_backend == "in_process":
            logger.warning(
                "Ignoring execution_backend=in_process for runner-only playbook %s rerun",
                playbook_code,
            )
            final_execution_backend = "runner"
        if prefer_runner:
            if (
                playbook_run
                and playbook_run.get_execution_mode() == "workflow"
                and playbook_run.has_json()
            ):
                new_execution_id = str(uuid.uuid4())
                normalized_inputs = (
                    merged_inputs.copy() if isinstance(merged_inputs, dict) else {}
                )
                normalized_inputs["execution_id"] = new_execution_id
                normalized_inputs["execution_backend"] = final_execution_backend
                if workspace_id and "workspace_id" not in normalized_inputs:
                    normalized_inputs["workspace_id"] = workspace_id
                if project_id and "project_id" not in normalized_inputs:
                    normalized_inputs["project_id"] = project_id
                if profile_id and "profile_id" not in normalized_inputs:
                    normalized_inputs["profile_id"] = profile_id

                from backend.app.models.workspace import (
                    PlaybookExecution,
                    Task,
                    TaskStatus,
                )

                playbook_name = (
                    playbook_run.playbook.metadata.name
                    if playbook_run.playbook and playbook_run.playbook.metadata
                    else playbook_code
                )
                total_steps = (
                    len(playbook_run.playbook_json.steps)
                    if playbook_run.playbook_json and playbook_run.playbook_json.steps
                    else 1
                )

                from backend.app.services.mindscape_store import MindscapeStore

                rerun_store = MindscapeStore()
                executions_store = rerun_store.playbook_executions
                if executions_store and workspace_id:
                    await asyncio.to_thread(
                        executions_store.create_execution,
                        PlaybookExecution(
                            id=new_execution_id,
                            workspace_id=workspace_id,
                            playbook_code=playbook_code,
                            thread_id=(
                                normalized_inputs.get("thread_id")
                                if isinstance(normalized_inputs, dict)
                                else None
                            ),
                            intent_instance_id=None,
                            status="running",
                            phase="queue",
                            last_checkpoint=None,
                            progress_log_path=None,
                            feature_list_path=None,
                            metadata={
                                "execution_mode": "runner",
                                "execution_backend_hint": final_execution_backend,
                                "playbook_name": playbook_name,
                                "resource_class": runner_metadata.get("resource_class"),
                                "queue_partition": runner_metadata.get("queue_partition")
                                or runner_metadata.get("queue_shard")
                                or DEFAULT_LOCAL_QUEUE_PARTITION,
                                "queue_shard": runner_metadata.get("queue_shard")
                                or DEFAULT_LOCAL_QUEUE_PARTITION,
                                "runner_profile_hint": runner_metadata.get(
                                    "runner_profile_hint"
                                ),
                                "runtime_affinity": runner_metadata.get(
                                    "runtime_affinity"
                                ),
                                "rerun_of": execution_id,
                            },
                            created_at=_utc_now(),
                            updated_at=_utc_now(),
                        ),
                    )

                await asyncio.to_thread(
                    tasks_store.create_task,
                    Task(
                        id=new_execution_id,
                        workspace_id=workspace_id,
                        message_id=str(uuid.uuid4()),
                        execution_id=new_execution_id,
                        project_id=project_id,
                        profile_id=profile_id,
                        pack_id=playbook_code,
                        task_type="playbook_execution",
                        status=TaskStatus.PENDING,
                        queue_shard=runner_metadata.get("queue_shard")
                        or DEFAULT_LOCAL_QUEUE_PARTITION,
                        execution_context={
                            "playbook_code": playbook_code,
                            "playbook_name": playbook_name,
                            "execution_id": new_execution_id,
                            "status": "queued",
                            "execution_mode": "runner",
                            "execution_backend_hint": final_execution_backend,
                            "inputs": normalized_inputs,
                            "workspace_id": workspace_id,
                            "project_id": project_id,
                            "profile_id": profile_id,
                            "total_steps": total_steps,
                            **runner_metadata,
                        },
                        created_at=_utc_now(),
                        started_at=None,
                    ),
                )
                lifecycle_hooks_config = runner_metadata.get("lifecycle_hooks")
                if isinstance(lifecycle_hooks_config, dict):
                    on_queue = lifecycle_hooks_config.get("on_queue")
                    if on_queue and isinstance(on_queue, dict):
                        asyncio.create_task(
                            async_invoke_lifecycle_hook(
                                hook_name="on_queue",
                                hook_spec=on_queue,
                                normalized_inputs=normalized_inputs,
                                execution_context={
                                    "execution_id": new_execution_id,
                                    "workspace_id": workspace_id,
                                    "playbook_code": playbook_code,
                                    "original_execution_id": execution_id,
                                },
                            )
                        )

                return {
                    "status": "rerun_queued",
                    "original_execution_id": execution_id,
                    "execution_id": new_execution_id,
                    "playbook_code": playbook_code,
                    "execution_backend_hint": final_execution_backend,
                    "note": "Execution queued",
                }

        result = await playbook_executor.execute_playbook_run(
            playbook_code=playbook_code,
            profile_id=profile_id,
            inputs=merged_inputs,
            workspace_id=workspace_id,
            project_id=project_id,
        )

        if result.get("execution_mode") == "conversation":
            return result.get("result", result)

        return {
            "status": "rerun_started",
            "original_execution_id": execution_id,
            "execution_id": result.get("execution_id"),
            "playbook_code": playbook_code,
            **(result.get("result", {}) or {}),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to rerun execution: {str(e)}"
        )
