"""Playbook finalization helpers for workflow execution."""

import json
import logging
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Optional

logger = logging.getLogger(__name__)


def resolve_playbook_code(playbook_json: Any) -> str:
    """Resolve the canonical playbook code for completion-time lookups."""
    playbook_code = getattr(playbook_json, "playbook_code", None)
    if not playbook_code and hasattr(playbook_json, "metadata") and playbook_json.metadata:
        playbook_code = getattr(playbook_json.metadata, "playbook_code", None)

    if not playbook_code:
        logger.warning("Cannot determine playbook_code for artifact creation")
        return "unknown"
    return playbook_code


async def load_playbook_metadata(
    *,
    store: Any,
    playbook_code: str,
    playbook_json: Any,
    load_playbook_fn: Optional[Callable[[str], Awaitable[Any]]] = None,
    load_playbook_json_fn: Optional[Callable[[str], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Load playbook metadata, including output_artifacts declared in JSON specs."""
    playbook_metadata: Dict[str, Any] = {}
    if not playbook_code or playbook_code == "unknown":
        return playbook_metadata

    if load_playbook_fn is None:

        async def load_playbook_fn(playbook_code: str) -> Any:
            from backend.app.services.playbook_service import PlaybookService

            playbook_service = PlaybookService(store=store)
            return await playbook_service.get_playbook(playbook_code)

    if load_playbook_json_fn is None:

        def load_playbook_json_fn(playbook_code: str) -> Dict[str, Any]:
            base_dir = Path(__file__).parent.parent.parent
            playbook_json_path = base_dir / "playbooks" / "specs" / f"{playbook_code}.json"
            if not playbook_json_path.exists():
                return {}
            with open(playbook_json_path, "r", encoding="utf-8") as handle:
                return json.load(handle)

    playbook = await load_playbook_fn(playbook_code)
    if playbook and hasattr(playbook, "metadata") and playbook.metadata:
        if hasattr(playbook.metadata, "__dict__"):
            playbook_metadata = dict(playbook.metadata.__dict__)
        elif isinstance(playbook.metadata, dict):
            playbook_metadata = dict(playbook.metadata)

    if hasattr(playbook_json, "output_artifacts"):
        playbook_metadata["output_artifacts"] = playbook_json.output_artifacts

    try:
        playbook_json_data = load_playbook_json_fn(playbook_code)
        if isinstance(playbook_json_data, dict) and "output_artifacts" in playbook_json_data:
            playbook_metadata["output_artifacts"] = playbook_json_data["output_artifacts"]
    except Exception as exc:
        logger.warning("Failed to load output_artifacts from JSON file: %s", exc)

    return playbook_metadata


async def maybe_create_output_artifacts(
    *,
    store: Any,
    playbook_json: Any,
    playbook_inputs: Dict[str, Any],
    step_outputs: Dict[str, Dict[str, Any]],
    execution_id: Optional[str],
    workspace_id: Optional[str],
    sandbox_id: Optional[str],
    load_playbook_metadata_fn: Optional[Callable[..., Awaitable[Dict[str, Any]]]] = None,
    create_artifacts_fn: Optional[Callable[..., Awaitable[Any]]] = None,
) -> None:
    """Create output artifacts for a completed playbook when configured."""
    if not (execution_id and workspace_id and store):
        return

    try:
        if load_playbook_metadata_fn is None:
            load_playbook_metadata_fn = load_playbook_metadata

        playbook_code = resolve_playbook_code(playbook_json)
        playbook_metadata = await load_playbook_metadata_fn(
            store=store,
            playbook_code=playbook_code,
            playbook_json=playbook_json,
        )
        if not playbook_metadata.get("output_artifacts"):
            return

        if create_artifacts_fn is None:
            from backend.app.services.playbook_output_artifact_creator import (
                PlaybookOutputArtifactCreator,
            )
            from backend.app.services.stores.postgres.artifacts_store import (
                PostgresArtifactsStore,
            )

            artifacts_store = PostgresArtifactsStore()
            artifact_creator = PlaybookOutputArtifactCreator(artifacts_store)
            create_artifacts_fn = artifact_creator.create_artifacts_from_playbook_outputs

        execution_context = {"execution_id": execution_id}
        if sandbox_id:
            execution_context["sandbox_id"] = sandbox_id
            logger.info(
                "WorkflowOrchestrator: Passing sandbox_id=%s to artifact creator",
                sandbox_id,
            )
        else:
            logger.warning(
                "WorkflowOrchestrator: No sandbox_id available for execution %s",
                execution_id,
            )

        created_artifacts = await create_artifacts_fn(
            playbook_code=playbook_code,
            execution_id=execution_id,
            workspace_id=workspace_id,
            playbook_metadata=playbook_metadata,
            step_outputs=step_outputs,
            inputs=playbook_inputs,
            execution_context=execution_context,
        )
        if created_artifacts:
            logger.info(
                "Created %s artifacts from playbook execution",
                len(created_artifacts),
            )
    except Exception as exc:
        logger.error(
            "Failed to create artifacts from playbook outputs: %s",
            exc,
            exc_info=True,
        )


def preserve_sandbox_context(
    *,
    sandbox_id: Optional[str],
    execution_id: Optional[str],
    workspace_id: Optional[str],
    update_task_execution_context_fn: Optional[Callable[..., bool]] = None,
) -> None:
    """Persist sandbox_id onto the task execution context when possible."""
    logger.debug(
        "Preserve sandbox_id check: sandbox_id=%s, execution_id=%s, workspace_id=%s",
        sandbox_id,
        execution_id,
        workspace_id,
    )
    if not (sandbox_id and execution_id and workspace_id):
        logger.debug(
            "Skipping sandbox_id preservation: sandbox_id=%s, execution_id=%s, workspace_id=%s",
            sandbox_id,
            execution_id,
            workspace_id,
        )
        return

    if update_task_execution_context_fn is None:

        def update_task_execution_context_fn(
            *,
            execution_id: str,
            sandbox_id: str,
        ) -> bool:
            from backend.app.services.stores.tasks_store import TasksStore

            tasks_store = TasksStore()
            logger.debug("Getting task by execution_id: %s", execution_id)
            task = tasks_store.get_task_by_execution_id(execution_id)
            logger.debug("Task found: %s", task is not None)
            if not task:
                return False
            execution_context = task.execution_context or {}
            execution_context["sandbox_id"] = sandbox_id
            logger.debug("Updating task %s with sandbox_id=%s", task.id, sandbox_id)
            tasks_store.update_task(task.id, execution_context=execution_context)
            return True

    try:
        updated = update_task_execution_context_fn(
            execution_id=execution_id,
            sandbox_id=sandbox_id,
        )
        if updated:
            logger.debug(
                "WorkflowOrchestrator: Preserved sandbox_id=%s in execution_context for execution %s",
                sandbox_id,
                execution_id,
            )
        else:
            logger.debug("Task not found for execution_id: %s", execution_id)
    except Exception as exc:
        logger.error(
            "WorkflowOrchestrator: Failed to preserve sandbox_id in execution_context: %s",
            exc,
            exc_info=True,
        )


def build_completed_result(
    *,
    step_outputs: Dict[str, Dict[str, Any]],
    final_outputs: Dict[str, Any],
    sandbox_id: Optional[str],
) -> Dict[str, Any]:
    """Build the final completed playbook result payload."""
    result = {
        "status": "completed",
        "step_outputs": step_outputs,
        "outputs": final_outputs,
    }
    if sandbox_id:
        result["sandbox_id"] = sandbox_id
    return result


async def finalize_playbook_execution(
    *,
    store: Any,
    playbook_json: Any,
    playbook_inputs: Dict[str, Any],
    step_outputs: Dict[str, Dict[str, Any]],
    final_outputs: Dict[str, Any],
    execution_id: Optional[str],
    workspace_id: Optional[str],
    sandbox_id: Optional[str],
    load_playbook_metadata_fn: Optional[Callable[..., Awaitable[Dict[str, Any]]]] = None,
    create_artifacts_fn: Optional[Callable[..., Awaitable[Any]]] = None,
    update_task_execution_context_fn: Optional[Callable[..., bool]] = None,
) -> Dict[str, Any]:
    """Run completion-time side effects and build the final result."""
    await maybe_create_output_artifacts(
        store=store,
        playbook_json=playbook_json,
        playbook_inputs=playbook_inputs,
        step_outputs=step_outputs,
        execution_id=execution_id,
        workspace_id=workspace_id,
        sandbox_id=sandbox_id,
        load_playbook_metadata_fn=load_playbook_metadata_fn,
        create_artifacts_fn=create_artifacts_fn,
    )
    preserve_sandbox_context(
        sandbox_id=sandbox_id,
        execution_id=execution_id,
        workspace_id=workspace_id,
        update_task_execution_context_fn=update_task_execution_context_fn,
    )
    return build_completed_result(
        step_outputs=step_outputs,
        final_outputs=final_outputs,
        sandbox_id=sandbox_id,
    )
