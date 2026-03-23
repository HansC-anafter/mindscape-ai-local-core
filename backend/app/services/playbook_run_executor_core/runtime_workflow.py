"""Runtime workflow helpers for ``PlaybookRunExecutor``."""

import asyncio
import logging
import uuid
from typing import Any, Callable, Dict, Optional

from backend.app.core.domain_context import LocalDomainContext
from backend.app.services.execution_core.clock import utc_now as _utc_now
from backend.app.services.execution_core.errors import RecoverableStepError

logger = logging.getLogger(__name__)


def _resolve_execution_id(normalized_inputs: Optional[Dict[str, Any]]) -> str:
    if isinstance(normalized_inputs, dict):
        existing = normalized_inputs.get("execution_id")
        if isinstance(existing, str) and existing.strip():
            return existing.strip()
    return str(uuid.uuid4())


def _extract_execution_backend_hint(
    normalized_inputs: Optional[Dict[str, Any]],
) -> Optional[str]:
    if not isinstance(normalized_inputs, dict):
        return None
    backend_hint = normalized_inputs.get("execution_backend")
    if isinstance(backend_hint, str) and backend_hint:
        return backend_hint
    return None


def _build_runtime_task_context(
    *,
    playbook_code: str,
    execution_id: str,
    normalized_inputs: Dict[str, Any],
    workspace_id: Optional[str],
    project_id: Optional[str],
    profile_id: str,
    execution_backend_hint: Optional[str],
) -> Dict[str, Any]:
    context = {
        "playbook_code": playbook_code,
        "execution_id": execution_id,
        "status": "running",
        "inputs": normalized_inputs,
        "workspace_id": workspace_id,
        "project_id": project_id,
        "profile_id": profile_id,
        "meeting_session_id": normalized_inputs.get("meeting_session_id"),
        "thread_id": normalized_inputs.get("thread_id"),
    }
    if execution_backend_hint:
        context["execution_backend_hint"] = execution_backend_hint
    return context


def _extract_step_and_output_payloads(
    runtime_result: Any,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    step_outputs_payload: Dict[str, Any] = {}
    outputs_payload: Dict[str, Any] = {}
    metadata = getattr(runtime_result, "metadata", None) or {}
    steps_meta = metadata.get("steps") if isinstance(metadata, dict) else None

    if isinstance(steps_meta, dict):
        for step_result in steps_meta.values():
            if not isinstance(step_result, dict):
                continue
            if isinstance(step_result.get("step_outputs"), dict) and step_result["step_outputs"]:
                step_outputs_payload = step_result["step_outputs"]
            if isinstance(step_result.get("outputs"), dict) and step_result["outputs"]:
                outputs_payload = step_result["outputs"]
            if step_outputs_payload or outputs_payload:
                break

    outputs = getattr(runtime_result, "outputs", None)
    if not step_outputs_payload and isinstance(outputs, dict):
        step_outputs_payload = outputs
    if not outputs_payload and isinstance(outputs, dict):
        outputs_payload = outputs
    return step_outputs_payload, outputs_payload


def _extract_sandbox_id(runtime_result: Any) -> Optional[str]:
    metadata = getattr(runtime_result, "metadata", None) or {}
    if isinstance(metadata, dict):
        sandbox_id = metadata.get("sandbox_id")
        if isinstance(sandbox_id, str) and sandbox_id:
            return sandbox_id
        steps = metadata.get("steps")
        if isinstance(steps, dict):
            for step_result in steps.values():
                if isinstance(step_result, dict):
                    sandbox_id = step_result.get("sandbox_id")
                    if isinstance(sandbox_id, str) and sandbox_id:
                        return sandbox_id
    return None


def _register_background_task(execution_id: str, task: "asyncio.Task[Any]") -> None:
    from backend.app.services.execution_task_registry import execution_task_registry

    execution_task_registry.register(execution_id, task)


def _unregister_background_task(execution_id: str) -> None:
    try:
        from backend.app.services.execution_task_registry import execution_task_registry

        execution_task_registry.unregister(execution_id)
    except Exception:
        pass


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
            merged_context = (
                dict(existing.execution_context)
                if isinstance(existing.execution_context, dict)
                else {}
            )
            merged_context.update(context)
            tasks_store.update_task(
                existing.id,
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
        canonical_workflow_result = result or {
            "status": (
                "failed"
                if workflow_failed
                else getattr(runtime_result, "status", None) or "failed"
            ),
            "step_outputs": step_outputs_payload,
            "outputs": outputs_payload,
        }
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
            "workflow_result": canonical_workflow_result,
        }
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
        if runtime_status == "paused":
            task_status = TaskStatus.RUNNING
        elif runtime_status == "completed" and not workflow_failed:
            task_status = TaskStatus.SUCCEEDED
        else:
            task_status = TaskStatus.FAILED

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
                status=task_status,
                completed_at=(
                    utc_now_fn()
                    if task_status in (TaskStatus.SUCCEEDED, TaskStatus.FAILED)
                    else None
                ),
                error=(
                    "Workflow completed with step errors"
                    if workflow_failed
                    else getattr(runtime_result, "error", None)
                    or "Runtime execution returned None"
                ),
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
            tasks_store.update_task(
                existing_task.id,
                execution_context=context,
                status=TaskStatus.PENDING,
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
    except Exception:
        pass


def inject_lens_context(
    *,
    profile_id: str,
    workspace_id: Optional[str],
    execution_id: str,
    normalized_inputs: Dict[str, Any],
) -> Optional[Any]:
    from backend.app.core.feature_flags import FeatureFlags

    if not FeatureFlags.USE_EFFECTIVE_LENS_RESOLVER:
        return None

    try:
        from backend.app.services.lens.lens_execution_injector import (
            LensExecutionInjector,
        )

        injector = LensExecutionInjector()
        lens_context = injector.prepare_lens_context(
            profile_id=profile_id,
            workspace_id=workspace_id,
            session_id=execution_id,
        )
        if not lens_context:
            return None

        logger.info(
            "PlaybookRunExecutor: Lens context prepared, hash=%s",
            lens_context.get("effective_lens_hash"),
        )
        if "system_prompt_additions" in lens_context:
            normalized_inputs["_lens_system_prompt"] = lens_context[
                "system_prompt_additions"
            ]
        if "anti_goals" in lens_context:
            normalized_inputs["_lens_anti_goals"] = lens_context["anti_goals"]
        if "emphasized_values" in lens_context:
            normalized_inputs["_lens_emphasized_values"] = lens_context[
                "emphasized_values"
            ]
        return lens_context.get("effective_lens")
    except Exception as exc:
        logger.warning(
            "PlaybookRunExecutor: Failed to inject lens context: %s",
            exc,
            exc_info=True,
        )
        return None


def generate_lens_receipt(
    *,
    execution_id: str,
    workspace_id: Optional[str],
    runtime_result: Any,
    effective_lens: Any,
) -> None:
    if not effective_lens:
        return

    from backend.app.core.feature_flags import FeatureFlags

    if not FeatureFlags.USE_EFFECTIVE_LENS_RESOLVER:
        return

    try:
        from backend.app.services.lens.lens_execution_injector import (
            LensExecutionInjector,
        )

        injector = LensExecutionInjector()
        outputs = getattr(runtime_result, "outputs", None)
        output_text = str(outputs) if outputs else None
        receipt = injector.generate_receipt(
            execution_id=execution_id,
            workspace_id=workspace_id,
            effective_lens=effective_lens,
            output=output_text,
            base_output=None,
        )
        if receipt:
            logger.info(
                "PlaybookRunExecutor: Lens receipt generated for execution %s",
                execution_id,
            )
    except Exception as exc:
        logger.warning(
            "PlaybookRunExecutor: Failed to generate lens receipt: %s",
            exc,
            exc_info=True,
        )


async def execute_runtime_workflow(
    *,
    executor: Any,
    playbook_run: Any,
    playbook_code: str,
    profile_id: str,
    normalized_inputs: Dict[str, Any],
    workspace_id: Optional[str],
    project_id: Optional[str],
    runtime_result_has_errors_fn: Callable[[Any, Optional[Dict[str, Any]]], bool],
    is_runner_process_fn: Callable[[], bool],
) -> Dict[str, Any]:
    """Execute workflow-mode playbooks through the runtime system."""
    if not workspace_id:
        error_msg = f"workspace_id is required for playbook execution: {playbook_code}"
        logger.error("PlaybookRunExecutor: %s", error_msg)
        raise ValueError(error_msg)

    execution_profile = playbook_run.get_execution_profile()
    runtime = executor.runtime_factory.get_runtime(execution_profile)
    logger.info(
        "PlaybookRunExecutor: Selected runtime: %s for playbook %s",
        runtime.name,
        playbook_code,
    )

    execution_id = _resolve_execution_id(normalized_inputs)
    logger.info(
        "PlaybookRunExecutor: Creating LocalDomainContext with project_id=%s",
        project_id,
    )
    exec_context = LocalDomainContext(
        actor_id=profile_id,
        workspace_id=workspace_id,
        tags={
            "execution_id": execution_id,
            "playbook_code": playbook_code,
            "project_id": project_id or "",
        },
    )
    logger.info(
        "PlaybookRunExecutor: LocalDomainContext.tags.project_id=%s",
        exec_context.tags.get("project_id") if exec_context.tags else "None",
    )

    normalized_inputs.setdefault("execution_id", execution_id)
    effective_lens = inject_lens_context(
        profile_id=profile_id,
        workspace_id=workspace_id,
        execution_id=execution_id,
        normalized_inputs=normalized_inputs,
    )
    persist_running_runtime_task(
        playbook_code=playbook_code,
        execution_id=execution_id,
        workspace_id=workspace_id,
        project_id=project_id,
        profile_id=profile_id,
        normalized_inputs=normalized_inputs,
    )

    async def _run_runtime_in_background() -> None:
        try:
            runtime_result = await runtime.execute(
                playbook_run=playbook_run,
                context=exec_context,
                inputs=normalized_inputs,
            )
            metadata = getattr(runtime_result, "metadata", None) or {}
            steps = metadata.get("steps", {}) if isinstance(metadata, dict) else {}
            result = {
                "status": getattr(runtime_result, "status", None) or "failed",
                "context": getattr(runtime_result, "outputs", None) or {},
                "steps": steps,
            }
            generate_lens_receipt(
                execution_id=execution_id,
                workspace_id=workspace_id,
                runtime_result=runtime_result,
                effective_lens=effective_lens,
            )
            persist_runtime_result(
                playbook_run=playbook_run,
                playbook_code=playbook_code,
                execution_id=execution_id,
                workspace_id=workspace_id,
                project_id=project_id,
                profile_id=profile_id,
                normalized_inputs=normalized_inputs,
                runtime_result=runtime_result,
                result=result,
                runtime_result_has_errors_fn=runtime_result_has_errors_fn,
            )
        except RecoverableStepError as exc:
            logger.warning(
                "PlaybookRunExecutor: Step runtime recoverable error: %s",
                exc,
            )
            mark_pending_runtime_task(
                execution_id=execution_id,
                error=exc,
            )
        except Exception as exc:
            logger.error(
                "PlaybookRunExecutor: Runtime execution failed: %s",
                exc,
                exc_info=True,
            )
            mark_failed_runtime_task(
                execution_id=execution_id,
                error=exc,
                normalized_inputs=normalized_inputs,
                workspace_id=workspace_id,
                project_id=project_id,
                profile_id=profile_id,
            )
        finally:
            _unregister_background_task(execution_id)

    if is_runner_process_fn():
        await _run_runtime_in_background()
        return {
            "execution_mode": "workflow",
            "playbook_code": playbook_code,
            "execution_id": execution_id,
            "result": {"status": "completed", "execution_id": execution_id},
            "has_json": True,
            "runtime": runtime.name,
        }

    background_task = asyncio.create_task(_run_runtime_in_background())
    _register_background_task(execution_id, background_task)
    return {
        "execution_mode": "workflow",
        "playbook_code": playbook_code,
        "execution_id": execution_id,
        "result": {"status": "running", "execution_id": execution_id},
        "has_json": True,
        "runtime": runtime.name,
    }
