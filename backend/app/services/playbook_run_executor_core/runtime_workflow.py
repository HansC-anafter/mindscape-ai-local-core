"""Runtime workflow dispatcher for ``PlaybookRunExecutor``."""

import asyncio
import logging
from typing import Any, Callable, Dict, Optional

from backend.app.core.domain_context import LocalDomainContext
from backend.app.services.execution_core.errors import RecoverableStepError
from backend.app.services.playbook_run_executor_core.runtime_workflow_lens import (
    generate_lens_receipt,
    inject_lens_context,
)
from backend.app.services.playbook_run_executor_core.runtime_workflow_payloads import (
    _build_canonical_workflow_result,
    _build_runtime_task_context,
    _extract_execution_backend_hint,
    _extract_sandbox_id,
    _extract_step_and_output_payloads,
    _merge_task_params,
    _resolve_execution_id,
)
from backend.app.services.playbook_run_executor_core.runtime_workflow_persistence import (
    _land_runtime_result,
    mark_failed_runtime_task,
    mark_pending_runtime_task,
    maybe_create_runtime_output_artifacts,
    persist_running_runtime_task,
    persist_runtime_result,
)
from backend.app.services.run_harness.workflow_ledger_bridge import (
    record_run_harness_workflow_started as record_started,
)

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
    try:
        from backend.app.services.service_endpoint_registry import (
            build_runtime_service_endpoint_context,
        )

        runtime_context = build_runtime_service_endpoint_context()
    except Exception:
        logger.debug(
            "PlaybookRunExecutor: Service endpoint context unavailable",
            exc_info=True,
        )
        runtime_context = {"service_endpoints": {"version": 1, "endpoints": []}}

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
            "runtime_context": runtime_context,
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
    record_started(
        normalized_inputs=normalized_inputs,
        execution_id=execution_id,
        metadata={
            "playbook_code": playbook_code,
            "runtime": runtime.name,
            "workspace_id": workspace_id,
            "project_id": project_id,
        },
    )

    async def _run_runtime_in_background() -> None:
        try:
            runtime_result = await runtime.execute(
                playbook_run=playbook_run,
                context=exec_context,
                inputs=normalized_inputs,
            )
            sandbox_id = _extract_sandbox_id(runtime_result)
            store = (
                getattr(executor, "store", None)
                or getattr(getattr(executor, "workflow_orchestrator", None), "store", None)
                or getattr(getattr(executor, "playbook_service", None), "store", None)
            )
            await maybe_create_runtime_output_artifacts(
                playbook_run=playbook_run,
                normalized_inputs=normalized_inputs,
                runtime_result=runtime_result,
                execution_id=execution_id,
                workspace_id=workspace_id,
                sandbox_id=sandbox_id,
                store=store,
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
                normalized_inputs=normalized_inputs,
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
