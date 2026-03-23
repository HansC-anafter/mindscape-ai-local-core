"""Legacy workflow execution helpers for ``PlaybookRunExecutor``."""

import asyncio
import logging
import uuid
from typing import Any, Callable, Dict, Optional

from backend.app.models.execution_metadata import (
    ExecutionMetadata,
    extract_governance_payload,
)
from backend.app.models.workspace import PlaybookExecution
from backend.app.services.execution_core.clock import utc_now as _utc_now

logger = logging.getLogger(__name__)


def _register_background_task(execution_id: str, task: "asyncio.Task[Any]") -> None:
    from backend.app.services.execution_task_registry import execution_task_registry

    execution_task_registry.register(execution_id, task)


def _unregister_background_task(execution_id: str) -> None:
    try:
        from backend.app.services.execution_task_registry import execution_task_registry

        execution_task_registry.unregister(execution_id)
    except Exception:
        pass


def _normalize_legacy_inputs(
    *,
    inputs: Optional[Dict[str, Any]],
    workspace_id: Optional[str],
    project_id: Optional[str],
    profile_id: str,
) -> Dict[str, Any]:
    normalized_inputs = dict(inputs or {})
    if workspace_id and "workspace_id" not in normalized_inputs:
        normalized_inputs["workspace_id"] = workspace_id
    if project_id and "project_id" not in normalized_inputs:
        normalized_inputs["project_id"] = project_id
    if profile_id and "profile_id" not in normalized_inputs:
        normalized_inputs["profile_id"] = profile_id
    return normalized_inputs


async def _create_execution_record(
    *,
    executor: Any,
    execution_id: str,
    playbook_code: str,
    workspace_id: str,
    inputs: Optional[Dict[str, Any]],
) -> None:
    if not executor.executions_store:
        return

    execution_record = PlaybookExecution(
        id=execution_id,
        workspace_id=workspace_id,
        playbook_code=playbook_code,
        thread_id=inputs.get("thread_id") if isinstance(inputs, dict) else None,
        intent_instance_id=None,
        status="running",
        phase="initialization",
        last_checkpoint=None,
        progress_log_path=None,
        feature_list_path=None,
        created_at=_utc_now(),
        updated_at=_utc_now(),
    )
    executor.executions_store.create_execution(execution_record)

    init_result = await executor.initializer.initialize_playbook_execution(
        execution_id=execution_record.id,
        playbook_code=playbook_code,
        workspace_id=workspace_id,
    )
    if init_result["success"]:
        execution_record.progress_log_path = init_result["artifacts"].get(
            "progress_log"
        )
        execution_record.feature_list_path = init_result["artifacts"].get(
            "feature_list"
        )
        executor.executions_store.update_execution_status(
            execution_id=execution_record.id,
            status="running",
            phase="execution",
        )


def _build_legacy_execution_context(
    *,
    playbook_run: Any,
    playbook_code: str,
    execution_id: str,
    total_steps: int,
    inputs: Optional[Dict[str, Any]],
    workspace_id: str,
    project_id: Optional[str],
    profile_id: str,
    execution_metadata: ExecutionMetadata,
    governance_payload: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    playbook_name = (
        playbook_run.playbook.metadata.name
        if playbook_run.playbook and playbook_run.playbook.metadata
        else playbook_code
    )
    execution_context = {
        "playbook_code": playbook_code,
        "playbook_name": playbook_name,
        "execution_id": execution_id,
        "total_steps": total_steps,
        "current_step_index": 0,
        "status": "running",
        "inputs": dict(inputs or {}),
        "workspace_id": workspace_id,
        "project_id": project_id,
        "profile_id": profile_id,
        "execution_metadata": execution_metadata.to_dict(),
        "meeting_session_id": inputs.get("meeting_session_id")
        if isinstance(inputs, dict)
        else None,
        "thread_id": inputs.get("thread_id") if isinstance(inputs, dict) else None,
    }
    if governance_payload:
        execution_context["governance"] = dict(governance_payload)
    if isinstance(inputs, dict):
        execution_backend_hint = inputs.get("execution_backend")
        if isinstance(execution_backend_hint, str) and execution_backend_hint:
            execution_context["execution_backend_hint"] = execution_backend_hint
    return execution_context


def _persist_legacy_running_task(
    *,
    execution_id: str,
    playbook_code: str,
    workspace_id: str,
    project_id: Optional[str],
    profile_id: str,
    execution_context: Dict[str, Any],
    utc_now_fn: Callable[[], Any] = _utc_now,
) -> Any:
    from backend.app.models.workspace import Task, TaskStatus
    from backend.app.services.stores.tasks_store import TasksStore

    tasks_store = TasksStore()
    task = Task(
        id=execution_id,
        workspace_id=workspace_id,
        message_id=str(uuid.uuid4()),
        execution_id=execution_id,
        project_id=project_id,
        profile_id=profile_id,
        pack_id=playbook_code,
        task_type="playbook_execution",
        status=TaskStatus.RUNNING,
        execution_context=execution_context,
        created_at=utc_now_fn(),
        started_at=utc_now_fn(),
        updated_at=utc_now_fn(),
    )

    existing_task = tasks_store.get_task_by_execution_id(execution_id)
    if existing_task:
        merged_context = (
            dict(existing_task.execution_context)
            if isinstance(existing_task.execution_context, dict)
            else {}
        )
        merged_context.update(execution_context)
        tasks_store.update_task(
            existing_task.id,
            execution_context=merged_context,
            status=TaskStatus.RUNNING,
            started_at=existing_task.started_at or utc_now_fn(),
            error=None,
        )
        return tasks_store, existing_task

    tasks_store.create_task(task)
    return tasks_store, task


async def _land_governed_result(
    *,
    execution_id: str,
    workspace_id: str,
    project_id: Optional[str],
    playbook_code: str,
    result: Dict[str, Any],
) -> None:
    try:
        from backend.app.services.mindscape_store import MindscapeStore
        from backend.app.services.orchestration.governance_engine import GovernanceEngine

        landing_store = MindscapeStore()
        workspace = await landing_store.get_workspace(workspace_id)
        storage_path = getattr(workspace, "storage_base_path", None) if workspace else None
        governance = GovernanceEngine()
        governance.process_completion(
            workspace_id=workspace_id,
            execution_id=execution_id,
            result_data=result or {},
            storage_base_path=storage_path,
            project_id=project_id,
            playbook_code=playbook_code,
        )
        logger.info(
            "PlaybookRunExecutor: Landed result via GovernanceEngine for %s",
            execution_id,
        )
    except Exception as exc:
        logger.warning(
            "PlaybookRunExecutor: GovernanceEngine landing failed (non-fatal): %s",
            exc,
        )


async def execute_legacy_workflow(
    *,
    executor: Any,
    playbook_run: Any,
    playbook_code: str,
    profile_id: str,
    inputs: Optional[Dict[str, Any]],
    workspace_id: Optional[str],
    project_id: Optional[str],
    workflow_result_has_errors_fn: Callable[[Dict[str, Any]], bool],
    is_runner_process_fn: Callable[[], bool],
) -> Dict[str, Any]:
    """Execute workflow playbooks through the legacy orchestrator bridge."""
    if not workspace_id:
        error_msg = f"workspace_id is required for playbook execution: {playbook_code}"
        logger.error("PlaybookRunExecutor: %s", error_msg)
        raise ValueError(error_msg)

    from backend.app.models.playbook import HandoffPlan, WorkflowStep
    from backend.app.models.workspace import TaskStatus

    execution_id = str(uuid.uuid4())
    total_steps = len(playbook_run.playbook_json.steps) if playbook_run.playbook_json.steps else 1
    governance_payload = (
        extract_governance_payload(inputs) if isinstance(inputs, dict) else None
    )
    execution_metadata = ExecutionMetadata()
    execution_metadata.set_execution_context(playbook_code=playbook_code)
    execution_metadata.set_governance(governance_payload)

    await _create_execution_record(
        executor=executor,
        execution_id=execution_id,
        playbook_code=playbook_code,
        workspace_id=workspace_id,
        inputs=inputs,
    )

    execution_context = _build_legacy_execution_context(
        playbook_run=playbook_run,
        playbook_code=playbook_code,
        execution_id=execution_id,
        total_steps=total_steps,
        inputs=inputs,
        workspace_id=workspace_id,
        project_id=project_id,
        profile_id=profile_id,
        execution_metadata=execution_metadata,
        governance_payload=governance_payload,
    )
    tasks_store, task = _persist_legacy_running_task(
        execution_id=execution_id,
        playbook_code=playbook_code,
        workspace_id=workspace_id,
        project_id=project_id,
        profile_id=profile_id,
        execution_context=execution_context,
    )

    normalized_inputs = _normalize_legacy_inputs(
        inputs=inputs,
        workspace_id=workspace_id,
        project_id=project_id,
        profile_id=profile_id,
    )
    logger.info(
        "PlaybookRunExecutor._execute_workflow_legacy: normalized_inputs keys=%s",
        list(normalized_inputs.keys()),
    )

    workflow_step = WorkflowStep(
        playbook_code=playbook_code,
        kind=playbook_run.playbook_json.kind,
        inputs=normalized_inputs,
        interaction_mode=(
            playbook_run.playbook.metadata.interaction_mode
            if playbook_run.playbook and playbook_run.playbook.metadata
            else "conversational"
        ),
    )
    handoff_plan = HandoffPlan(steps=[workflow_step], context=normalized_inputs)

    async def _run_workflow_in_background() -> None:
        nonlocal execution_context
        try:
            result = await executor.workflow_orchestrator.execute_workflow(
                handoff_plan,
                execution_id=execution_id,
                workspace_id=workspace_id,
                profile_id=profile_id,
                project_id=project_id,
            )

            status = result.get("status") if isinstance(result, dict) else "completed"
            existing = tasks_store.get_task(task.id)
            merged_context = (
                dict(existing.execution_context)
                if existing and isinstance(existing.execution_context, dict)
                else {}
            )

            if status == "paused":
                execution_context["status"] = "paused"
                execution_context["workflow_result"] = result
                execution_context["checkpoint"] = (
                    result.get("checkpoint")
                    if isinstance(result.get("checkpoint"), dict)
                    else None
                )
                merged_context.update(execution_context)
                tasks_store.update_task(
                    task.id,
                    execution_context=merged_context,
                    status=TaskStatus.RUNNING,
                    completed_at=None,
                    error=None,
                )
                logger.info(
                    "PlaybookRunExecutor: Execution %s paused (waiting gate)",
                    execution_id,
                )
                return

            workflow_failed = workflow_result_has_errors_fn(result)
            execution_context["status"] = "failed" if workflow_failed else "completed"
            execution_context["current_step_index"] = total_steps
            execution_context["workflow_result"] = result
            merged_context.update(execution_context)
            tasks_store.update_task(
                task.id,
                execution_context=merged_context,
                status=TaskStatus.FAILED if workflow_failed else TaskStatus.SUCCEEDED,
                completed_at=_utc_now(),
                error="Workflow completed with step errors" if workflow_failed else None,
            )
            await _land_governed_result(
                execution_id=execution_id,
                workspace_id=workspace_id,
                project_id=project_id,
                playbook_code=playbook_code,
                result=result or {},
            )
        except Exception as exc:
            from backend.app.shared.error_handler import parse_api_error

            error_info = parse_api_error(exc)
            execution_context["status"] = "failed"
            execution_context["error"] = error_info.user_message
            execution_context["error_details"] = error_info.to_dict()
            existing = tasks_store.get_task(task.id)
            merged_context = (
                dict(existing.execution_context)
                if existing and isinstance(existing.execution_context, dict)
                else {}
            )
            merged_context.update(execution_context)
            tasks_store.update_task(
                task.id,
                execution_context=merged_context,
                status=TaskStatus.FAILED,
                completed_at=_utc_now(),
                error=error_info.user_message,
            )
            logger.error(
                "PlaybookRunExecutor: Execution %s failed: %s",
                execution_id,
                exc,
            )
        finally:
            _unregister_background_task(execution_id)

    if is_runner_process_fn():
        await _run_workflow_in_background()
        return {
            "execution_mode": "workflow",
            "playbook_code": playbook_code,
            "execution_id": execution_id,
            "result": {"status": "completed", "note": "Execution completed"},
            "has_json": True,
        }

    background_task = asyncio.create_task(_run_workflow_in_background())
    _register_background_task(execution_id, background_task)
    return {
        "execution_mode": "workflow",
        "playbook_code": playbook_code,
        "execution_id": execution_id,
        "result": {"status": "running", "note": "Execution started"},
        "has_json": True,
    }
