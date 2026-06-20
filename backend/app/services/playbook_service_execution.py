import uuid
from typing import Any, Dict, Optional

from backend.app.models.playbook import PlaybookInvocationContext
from backend.app.services.playbook_loaders import PlaybookJsonLoader

from .playbook_service_models import ExecutionMode, ExecutionResult


async def execute_playbook_for_service(
    *,
    service: Any,
    playbook_code: str,
    workspace_id: str,
    profile_id: str,
    inputs: Dict[str, Any],
    execution_mode: ExecutionMode = ExecutionMode.ASYNC,
    locale: str = "zh-TW",
    context: Optional[PlaybookInvocationContext] = None,
    project_id: Optional[str] = None,
    logger: Any,
) -> ExecutionResult:
    """Execute a playbook through the existing PlaybookRunExecutor path."""
    _ = execution_mode
    playbook = await service.get_playbook(
        playbook_code,
        locale=locale,
        workspace_id=workspace_id,
    )
    if not playbook:
        raise ValueError(f"Playbook not found: {playbook_code}")

    _select_graph_variant(service=service, playbook=playbook, inputs=inputs, logger=logger)

    from backend.app.services.playbook_run_executor import PlaybookRunExecutor

    playbook_run_executor = PlaybookRunExecutor()
    executor_inputs = inputs or {}
    executor_locale = locale or executor_inputs.get("locale") or "zh-TW"

    try:
        project_id_to_use = await resolve_project_id_for_execution(
            store=service.store,
            workspace_id=workspace_id,
            inputs=executor_inputs,
            explicit_project_id=project_id,
            playbook_code=playbook_code,
            logger=logger,
        )
        execution_result_dict = await playbook_run_executor.execute_playbook_run(
            playbook_code=playbook_code,
            profile_id=profile_id,
            inputs=executor_inputs,
            workspace_id=workspace_id,
            project_id=project_id_to_use,
            target_language=executor_inputs.get("target_language"),
            locale=executor_locale,
            context=context,
        )
        execution_id = _extract_execution_id(execution_result_dict)
        if not execution_id:
            execution_id = str(uuid.uuid4())
            logger.warning(
                "PlaybookService: No execution_id found in result, generated new one: %s",
                execution_id,
            )
        else:
            logger.info(
                "PlaybookService: Extracted execution_id=%s from result",
                execution_id,
            )

        status = execution_result_dict.get("status", "running")
        if "execution_mode" in execution_result_dict:
            status = "running"

        logger.info(
            "PlaybookService: Executed playbook %s, execution_id=%s, status=%s",
            playbook_code,
            execution_id,
            status,
        )
        return ExecutionResult(
            execution_id=execution_id,
            status=status,
            result=execution_result_dict,
            progress=execution_result_dict.get("progress", 0.0),
        )
    except Exception as exc:
        logger.error(
            "PlaybookService: Failed to execute playbook %s: %s",
            playbook_code,
            exc,
            exc_info=True,
        )
        from backend.app.shared.error_handler import parse_api_error

        error_info = parse_api_error(exc)
        return ExecutionResult(
            execution_id=str(uuid.uuid4()),
            status="error",
            result=None,
            error=error_info.user_message,
            progress=0.0,
        )


async def resolve_project_id_for_execution(
    *,
    store: Any,
    workspace_id: str,
    inputs: Dict[str, Any],
    explicit_project_id: Optional[str],
    playbook_code: str,
    logger: Any,
) -> Optional[str]:
    """Preserve explicit, input, then workspace primary project precedence."""
    project_id_to_use = explicit_project_id
    if not project_id_to_use:
        project_id_to_use = inputs.get("project_id") if inputs else None
    if project_id_to_use:
        return project_id_to_use

    try:
        workspace = await store.get_workspace(workspace_id) if store else None
        if (
            workspace
            and hasattr(workspace, "primary_project_id")
            and workspace.primary_project_id
        ):
            logger.info(
                "PlaybookService: Using workspace.primary_project_id=%s for playbook %s",
                workspace.primary_project_id,
                playbook_code,
            )
            return workspace.primary_project_id
    except Exception as exc:
        logger.warning(
            "PlaybookService: Failed to get workspace.primary_project_id: %s",
            exc,
        )
    return None


async def get_execution_status_for_service(
    *,
    store: Any,
    execution_id: str,
    logger: Any,
) -> Optional[str]:
    """Read task execution status through the existing TasksStore path."""
    if not store:
        logger.warning("PlaybookService.get_execution_status() requires store")
        return None

    try:
        task, task_status = _get_task(execution_id)
        if task:
            return _status_map(task_status).get(task.status, "unknown")
        return None
    except Exception as exc:
        logger.error(
            "PlaybookService: Failed to get execution status for %s: %s",
            execution_id,
            exc,
            exc_info=True,
        )
        return None


async def get_execution_result_for_service(
    *,
    store: Any,
    execution_id: str,
    logger: Any,
) -> Optional[ExecutionResult]:
    """Read task execution result through the existing TasksStore path."""
    if not store:
        logger.warning("PlaybookService.get_execution_result() requires store")
        return None

    try:
        task, task_status = _get_task(execution_id)
        if not task:
            return None

        result = None
        error = None
        progress = 0.0
        if task.execution_context:
            result = task.execution_context
            progress = result.get("current_step_index", 0) / max(
                result.get("total_steps", 1),
                1,
            )
        if task.status == task_status.FAILED:
            error = result.get("error") if result else "Execution failed"

        return ExecutionResult(
            execution_id=execution_id,
            status=_status_map(task_status).get(task.status, "unknown"),
            result=result,
            error=error,
            progress=progress,
        )
    except Exception as exc:
        logger.error(
            "PlaybookService: Failed to get execution result for %s: %s",
            execution_id,
            exc,
            exc_info=True,
        )
        return None


async def load_playbook_run_for_service(
    *,
    service: Any,
    playbook_code: str,
    locale: str = "zh-TW",
    workspace_id: Optional[str] = None,
    logger: Any,
) -> Optional["PlaybookRun"]:
    """Load playbook.run through the existing playbook and JSON loader paths."""
    from backend.app.models.playbook import PlaybookRun

    playbook = await service.get_playbook(playbook_code, locale, workspace_id)
    if not playbook:
        logger.warning("playbook.md not found for %s", playbook_code)
        return None

    playbook_json = PlaybookJsonLoader.load_playbook_json(playbook_code)
    return PlaybookRun(playbook=playbook, playbook_json=playbook_json)


def _select_graph_variant(*, service: Any, playbook: Any, inputs: Dict[str, Any], logger: Any) -> None:
    if not hasattr(playbook.metadata, "graph_ir") or not playbook.metadata.graph_ir:
        return

    try:
        from backend.app.core.ir.graph_ir import GraphIR

        graph_ir = GraphIR.from_dict(playbook.metadata.graph_ir)
        selection_context = {
            "risk_level": inputs.get("risk_level", "low"),
            "urgency": inputs.get("urgency", "normal"),
            "cost_constraint": inputs.get("cost_constraint", "normal"),
        }
        selected_graph = service.graph_selector.select_variant(
            graph_id=graph_ir.graph_id,
            context=selection_context,
        )
        if selected_graph:
            logger.info(
                "PlaybookService: Selected graph variant '%s' for playbook %s",
                selected_graph.variant_name,
                playbook.metadata.playbook_code,
            )
    except Exception as exc:
        logger.warning(
            "PlaybookService: Failed to process Graph IR for playbook %s: %s",
            playbook.metadata.playbook_code,
            exc,
            exc_info=True,
        )


def _extract_execution_id(execution_result_dict: Dict[str, Any]) -> Optional[str]:
    return (
        execution_result_dict.get("execution_id")
        or execution_result_dict.get("result", {}).get("execution_id")
        if isinstance(execution_result_dict.get("result"), dict)
        else None
    )


def _get_task(execution_id: str):
    from backend.app.models.workspace import TaskStatus
    from backend.app.services.stores.tasks_store import TasksStore

    tasks_store = TasksStore()
    return tasks_store.get_task(execution_id), TaskStatus


def _status_map(task_status: Any) -> Dict[Any, str]:
    return {
        task_status.PENDING: "pending",
        task_status.RUNNING: "running",
        task_status.SUCCEEDED: "completed",
        task_status.FAILED: "failed",
        task_status.CANCELLED: "cancelled",
    }
