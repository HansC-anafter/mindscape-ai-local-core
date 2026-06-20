"""Persistence helpers for runtime workflow execution."""

import logging
import uuid
from typing import Any, Callable, Dict, Optional

from backend.app.services.execution_core.clock import utc_now as _utc_now
from backend.app.services.execution_core.errors import RecoverableStepError
from backend.app.services.playbook_run_executor_core.result_compaction import (
    compact_workflow_result_for_task_context,
)
from backend.app.services.playbook_run_executor_core.runtime_workflow_payloads import (
    _build_canonical_workflow_result,
    _build_runtime_task_context,
    _extract_execution_backend_hint,
    _extract_sandbox_id,
    _extract_step_and_output_payloads,
    _merge_task_params,
)
from backend.app.services.run_harness.workflow_ledger_bridge import (
    record_run_harness_workflow_failed as record_failed,
    record_run_harness_workflow_pending as record_pending,
    record_run_harness_workflow_terminal as record_terminal,
)

logger = logging.getLogger(__name__)


async def maybe_create_runtime_output_artifacts(
    *,
    playbook_run: Any,
    normalized_inputs: Dict[str, Any],
    runtime_result: Any,
    execution_id: str,
    workspace_id: Optional[str],
    sandbox_id: Optional[str],
    store: Any,
    create_output_artifacts_fn: Optional[Callable[..., Any]] = None,
) -> None:
    """Create file-backed output artifacts for runtime workflow completions."""
    if not (execution_id and workspace_id and store):
        return

    playbook_json = getattr(playbook_run, "playbook_json", None)
    if playbook_json is None:
        return

    step_outputs_payload, _outputs_payload = _extract_step_and_output_payloads(
        runtime_result
    )
    if not step_outputs_payload:
        return

    if create_output_artifacts_fn is None:
        from backend.app.services.workflow.playbook_finalization import (
            maybe_create_output_artifacts,
        )

        create_output_artifacts_fn = maybe_create_output_artifacts

    artifact_thread_id = normalized_inputs.get(
        "meeting_session_id"
    ) or normalized_inputs.get(
        "thread_id"
    )
    artifact_task_id = normalized_inputs.get("task_id") or normalized_inputs.get(
        "task_ir_id"
    )
    try:
        from backend.app.services.stores.tasks_store import TasksStore

        existing_task = TasksStore().get_task_by_execution_id(execution_id)
        artifact_task_id = (
            getattr(existing_task, "id", None) if existing_task else artifact_task_id
        )
    except Exception:
        logger.debug(
            "PlaybookRunExecutor: Could not resolve task id for output artifacts %s",
            execution_id,
            exc_info=True,
        )

    try:
        await create_output_artifacts_fn(
            store=store,
            playbook_json=playbook_json,
            playbook_inputs=normalized_inputs,
            step_outputs=step_outputs_payload,
            execution_id=execution_id,
            workspace_id=workspace_id,
            sandbox_id=sandbox_id,
            thread_id=artifact_thread_id,
            task_id=artifact_task_id,
        )
    except Exception:
        logger.warning(
            "PlaybookRunExecutor: Runtime output artifact creation failed for %s",
            execution_id,
            exc_info=True,
        )


def _land_runtime_result(
    *,
    workspace_id: Optional[str],
    project_id: Optional[str],
    playbook_code: str,
    execution_id: str,
    task_id: str,
    result: Dict[str, Any],
) -> None:
    if not workspace_id:
        return
    try:
        from backend.app.services.orchestration.governance_engine import GovernanceEngine
        from backend.app.services.stores.postgres.workspaces_store import (
            PostgresWorkspacesStore,
        )

        workspace = PostgresWorkspacesStore().get_workspace_sync(workspace_id)
        storage_path = (
            getattr(workspace, "storage_base_path", None) if workspace else None
        )
        GovernanceEngine().process_completion(
            workspace_id=workspace_id,
            execution_id=execution_id,
            result_data=result or {},
            storage_base_path=storage_path,
            project_id=project_id,
            task_id=task_id,
            playbook_code=playbook_code,
        )
    except Exception:
        logger.warning(
            "PlaybookRunExecutor: Runtime result landing failed for %s",
            execution_id,
            exc_info=True,
        )


def persist_running_runtime_task(
    *,
    playbook_code: str,
    execution_id: str,
    workspace_id: Optional[str],
    project_id: Optional[str],
    profile_id: str,
    normalized_inputs: Dict[str, Any],
    utc_now_fn: Callable[[], Any] = _utc_now,
) -> None:
    try:
        from backend.app.models.workspace import Task, TaskStatus
        from backend.app.services.stores.tasks_store import TasksStore

        tasks_store = TasksStore()
        existing = tasks_store.get_task_by_execution_id(execution_id)
        execution_backend_hint = _extract_execution_backend_hint(normalized_inputs)
        context = _build_runtime_task_context(
            playbook_code=playbook_code,
            execution_id=execution_id,
            normalized_inputs=normalized_inputs,
            workspace_id=workspace_id,
            project_id=project_id,
            profile_id=profile_id,
            execution_backend_hint=execution_backend_hint,
        )
        if existing:
            merged_params = _merge_task_params(
                getattr(existing, "params", None),
                normalized_inputs,
            )
            merged_context = (
                dict(existing.execution_context)
                if isinstance(existing.execution_context, dict)
                else {}
            )
            merged_context.update(context)
            tasks_store.update_task(
                existing.id,
                params=merged_params,
                execution_context=merged_context,
                status=TaskStatus.RUNNING,
                started_at=existing.started_at or utc_now_fn(),
                error=None,
            )
            return

        tasks_store.create_task(
            Task(
                id=execution_id,
                workspace_id=workspace_id,
                message_id=str(uuid.uuid4()),
                execution_id=execution_id,
                project_id=project_id,
                profile_id=profile_id,
                pack_id=playbook_code,
                task_type="playbook_execution",
                status=TaskStatus.RUNNING,
                params=dict(normalized_inputs),
                execution_context=context,
                created_at=utc_now_fn(),
                started_at=utc_now_fn(),
                updated_at=utc_now_fn(),
            )
        )
    except Exception as exc:
        logger.warning(
            "PlaybookRunExecutor: Failed to create running task record: %s",
            exc,
            exc_info=True,
        )


def persist_runtime_result(
    *,
    playbook_run: Any,
    playbook_code: str,
    execution_id: str,
    workspace_id: Optional[str],
    project_id: Optional[str],
    profile_id: str,
    normalized_inputs: Dict[str, Any],
    runtime_result: Any,
    result: Dict[str, Any],
    runtime_result_has_errors_fn: Callable[[Any, Optional[Dict[str, Any]]], bool],
    utc_now_fn: Callable[[], Any] = _utc_now,
) -> None:
    try:
        from backend.app.models.workspace import TaskStatus
        from backend.app.services.stores.tasks_store import TasksStore

        tasks_store = TasksStore()
        total_steps = (
            len(playbook_run.playbook_json.steps) if playbook_run.playbook_json.steps else 1
        )
        playbook_name = (
            playbook_run.playbook.metadata.name
            if playbook_run.playbook and playbook_run.playbook.metadata
            else playbook_code
        )
        step_outputs_payload, outputs_payload = _extract_step_and_output_payloads(
            runtime_result
        )
        workflow_failed = runtime_result_has_errors_fn(runtime_result, result)
        canonical_workflow_result = _build_canonical_workflow_result(
            result=result,
            runtime_result=runtime_result,
            workflow_failed=workflow_failed,
            step_outputs_payload=step_outputs_payload,
            outputs_payload=outputs_payload,
        )
        compact_workflow_result = compact_workflow_result_for_task_context(
            canonical_workflow_result
        )
        execution_context = {
            "playbook_code": playbook_code,
            "playbook_name": playbook_name,
            "execution_id": execution_id,
            "total_steps": total_steps,
            "current_step_index": (
                total_steps
                if runtime_result
                and getattr(runtime_result, "status", None) == "completed"
                and not workflow_failed
                else 0
            ),
            "status": (
                "failed"
                if workflow_failed
                else getattr(runtime_result, "status", None) or "failed"
            ),
            "inputs": normalized_inputs,
            "workspace_id": workspace_id,
            "project_id": project_id,
            "profile_id": profile_id,
            "workflow_result": compact_workflow_result,
        }
        try:
            from backend.app.services.object_action_closure_wiring import (
                close_object_action_from_execution_result,
            )

            closure_result = close_object_action_from_execution_result(
                workspace_id=workspace_id,
                execution_id=execution_id,
                inputs=normalized_inputs,
                execution_result=canonical_workflow_result,
            )
            if closure_result:
                execution_context["object_action_closure"] = closure_result
        except Exception:
            logger.exception(
                "PlaybookRunExecutor: Failed to run AOL object action closure for execution %s",
                execution_id,
            )
        backend_hint = _extract_execution_backend_hint(normalized_inputs)
        if backend_hint:
            execution_context["execution_backend_hint"] = backend_hint

        checkpoint = getattr(runtime_result, "checkpoint", None)
        if isinstance(checkpoint, dict):
            execution_context["checkpoint"] = checkpoint

        sandbox_id = _extract_sandbox_id(runtime_result)
        if sandbox_id:
            execution_context["sandbox_id"] = sandbox_id

        runtime_status = getattr(runtime_result, "status", None)
        pause_mode = checkpoint.get("pause_mode") if isinstance(checkpoint, dict) else None
        if runtime_status == "paused":
            task_status = TaskStatus.PENDING
        elif runtime_status == "completed" and not workflow_failed:
            task_status = TaskStatus.SUCCEEDED
        else:
            task_status = TaskStatus.FAILED

        error_value = None
        if task_status == TaskStatus.FAILED:
            error_value = (
                "Workflow completed with step errors"
                if workflow_failed
                else getattr(runtime_result, "error", None)
                or "Runtime execution returned None"
            )

        update_kwargs: Dict[str, Any] = {
            "execution_context": None,
            "status": task_status,
            "completed_at": (
                utc_now_fn()
                if task_status in (TaskStatus.SUCCEEDED, TaskStatus.FAILED)
                else None
            ),
            "error": error_value,
        }
        if task_status == TaskStatus.PENDING and pause_mode == "user_reserved":
            update_kwargs.update(
                {
                    "blocked_reason": "user_pause_reserved",
                    "blocked_payload": None,
                    "frontier_state": "cold",
                    "frontier_enqueued_at": None,
                    "next_eligible_at": None,
                }
            )

        existing_task = tasks_store.get_task_by_execution_id(execution_id)
        if existing_task:
            update_kwargs["params"] = _merge_task_params(
                getattr(existing_task, "params", None),
                normalized_inputs,
            )
            merged_context = (
                dict(existing_task.execution_context)
                if isinstance(existing_task.execution_context, dict)
                else {}
            )
            merged_context.update(execution_context)
            update_kwargs["execution_context"] = merged_context
            tasks_store.update_task(
                existing_task.id,
                **update_kwargs,
            )
            if task_status in (TaskStatus.SUCCEEDED, TaskStatus.FAILED):
                _land_runtime_result(
                    workspace_id=workspace_id,
                    project_id=project_id,
                    playbook_code=playbook_code,
                    execution_id=execution_id,
                    task_id=existing_task.id,
                    result=canonical_workflow_result,
                )
        bridge_compact_result = dict(compact_workflow_result)
        bridge_compact_result["workflow_failed"] = workflow_failed
        record_terminal(
            normalized_inputs=normalized_inputs,
            execution_id=execution_id,
            runtime_result=runtime_result,
            compact_result=bridge_compact_result,
        )
    except Exception as exc:
        logger.warning(
            "PlaybookRunExecutor: Failed to persist execution context: %s",
            exc,
            exc_info=True,
        )


def mark_pending_runtime_task(
    *,
    execution_id: str,
    error: RecoverableStepError,
    normalized_inputs: Optional[Dict[str, Any]] = None,
    utc_now_fn: Callable[[], Any] = _utc_now,
) -> None:
    try:
        from backend.app.models.workspace import TaskStatus
        from backend.app.services.stores.tasks_store import TasksStore

        tasks_store = TasksStore()
        existing_task = tasks_store.get_task_by_execution_id(execution_id)
        if existing_task:
            context = (
                dict(existing_task.execution_context)
                if isinstance(existing_task.execution_context, dict)
                else {}
            )
            context["pending_reason"] = getattr(error, "error_type", "recoverable_error")
            context["pending_detail"] = str(error)
            context["pending_since"] = utc_now_fn().isoformat()
            context["status"] = "queued"
            for transient_key in ("runner_id", "heartbeat_at", "resume_after"):
                context.pop(transient_key, None)
            next_eligible_at = utc_now_fn()
            tasks_store.update_task(
                existing_task.id,
                execution_context=context,
                status=TaskStatus.PENDING,
                started_at=None,
                completed_at=None,
                next_eligible_at=next_eligible_at,
                blocked_reason=None,
                blocked_payload=None,
                frontier_state="ready",
                frontier_enqueued_at=next_eligible_at,
                error=str(error),
            )
        record_pending(
            normalized_inputs=normalized_inputs or {},
            execution_id=execution_id,
            checkpoint={
                "step_id": getattr(error, "step_id", None),
                "error_type": getattr(error, "error_type", None),
            },
            error=str(error),
        )
    except Exception as exc:
        logger.error(
            "PlaybookRunExecutor: Failed to set task pending: %s",
            exc,
            exc_info=True,
        )


def mark_failed_runtime_task(
    *,
    execution_id: str,
    error: Exception,
    normalized_inputs: Dict[str, Any],
    workspace_id: Optional[str],
    project_id: Optional[str],
    profile_id: str,
    utc_now_fn: Callable[[], Any] = _utc_now,
) -> None:
    try:
        from backend.app.models.workspace import TaskStatus
        from backend.app.services.stores.tasks_store import TasksStore

        tasks_store = TasksStore()
        existing_task = tasks_store.get_task_by_execution_id(execution_id)
        if existing_task:
            context = (
                dict(existing_task.execution_context)
                if isinstance(existing_task.execution_context, dict)
                else {}
            )
            context["status"] = "failed"
            context["error"] = str(error)
            context["inputs"] = normalized_inputs
            context["workspace_id"] = workspace_id
            context["project_id"] = project_id
            context["profile_id"] = profile_id
            tasks_store.update_task(
                existing_task.id,
                execution_context=context,
                status=TaskStatus.FAILED,
                completed_at=utc_now_fn(),
                error=str(error),
            )
        record_failed(
            normalized_inputs=normalized_inputs,
            execution_id=execution_id,
            error=error,
        )
    except Exception:
        pass
