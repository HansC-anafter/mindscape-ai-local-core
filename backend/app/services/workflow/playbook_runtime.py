"""Playbook-runtime bootstrap helpers for workflow execution."""

import logging
from typing import Any, Awaitable, Callable, Dict, Optional, Set, Tuple

from backend.app.services.workflow.step_lifecycle import resolve_gate_action

logger = logging.getLogger(__name__)


def resolve_resume_checkpoint(
    *,
    playbook_inputs: Optional[Dict[str, Any]],
    execution_id: Optional[str],
    playbook_code: Optional[str],
) -> Optional[Dict[str, Any]]:
    """Return a matching workflow checkpoint when the resume payload is valid."""
    try:
        if isinstance(playbook_inputs, dict):
            candidate = playbook_inputs.get("_workflow_checkpoint")
            if isinstance(candidate, dict):
                if candidate.get("execution_id") == execution_id and candidate.get(
                    "playbook_code"
                ) == playbook_code:
                    return candidate
    except Exception:
        return None

    return None


def restore_checkpoint_state(
    *,
    playbook_inputs: Optional[Dict[str, Any]],
    resume_checkpoint: Optional[Dict[str, Any]],
) -> Tuple[Dict[str, Dict[str, Any]], Set[str]]:
    """Restore step outputs and completed steps from a resume checkpoint."""
    step_outputs: Dict[str, Dict[str, Any]] = {}
    completed_steps: Set[str] = set()

    if not isinstance(resume_checkpoint, dict):
        return step_outputs, completed_steps

    cp_step_outputs = resume_checkpoint.get("step_outputs")
    cp_completed_steps = resume_checkpoint.get("completed_steps")
    if isinstance(cp_step_outputs, dict):
        step_outputs = cp_step_outputs
    if isinstance(cp_completed_steps, list):
        completed_steps = {step_id for step_id in cp_completed_steps if isinstance(step_id, str)}

    paused_step_id = resume_checkpoint.get("paused_step_id")
    if isinstance(paused_step_id, str) and paused_step_id:
        action = resolve_gate_action(
            playbook_inputs=playbook_inputs,
            step_id=paused_step_id,
        )
        if action == "approved":
            completed_steps.add(paused_step_id)

    return step_outputs, completed_steps


def apply_execution_profile_model_override(
    *,
    playbook_json: Any,
    playbook_inputs: Dict[str, Any],
    resolve_model_fn: Optional[Callable[..., Tuple[Optional[str], Any]]] = None,
) -> Optional[str]:
    """Populate `_model_override` from execution_profile when it is absent."""
    if (
        not hasattr(playbook_json, "execution_profile")
        or not playbook_json.execution_profile
        or playbook_inputs.get("_model_override")
    ):
        return None

    if resolve_model_fn is None:
        from backend.app.services.capability_profile_resolver import (
            CapabilityProfileResolver,
        )

        resolve_model_fn = CapabilityProfileResolver().resolve

    try:
        execution_profile = playbook_json.execution_profile
        capability_profile = execution_profile.get("reasoning", "standard")
        resolved_model, _variant = resolve_model_fn(
            capability_profile,
            execution_profile=execution_profile,
            deployment_scope="local",
        )
        if resolved_model:
            playbook_inputs["_model_override"] = resolved_model
            logger.info(
                "v3.1: execution_profile resolved _model_override=%s "
                "(profile=%s, modalities=%s, locality=%s)",
                resolved_model,
                capability_profile,
                execution_profile.get("modalities"),
                execution_profile.get("locality"),
            )
            return resolved_model
    except Exception as exc:
        logger.warning("v3.1: execution_profile resolve failed (non-fatal): %s", exc)

    return None


async def ensure_execution_sandbox(
    *,
    store: Any,
    playbook_json: Any,
    execution_id: Optional[str],
    workspace_id: Optional[str],
    project_id: Optional[str],
    resume_checkpoint: Optional[Dict[str, Any]],
    get_project_fn: Optional[Callable[..., Awaitable[Any]]] = None,
    get_or_create_project_sandbox_fn: Optional[Callable[..., Awaitable[Optional[str]]]] = None,
    create_execution_sandbox_fn: Optional[Callable[..., Awaitable[Optional[str]]]] = None,
) -> Optional[str]:
    """Ensure a sandbox exists for the current playbook execution."""
    sandbox_id = None
    if isinstance(resume_checkpoint, dict):
        sandbox_id = resume_checkpoint.get("sandbox_id") or None

    if not workspace_id:
        logger.warning(
            "WorkflowOrchestrator: No workspace_id provided, skipping sandbox creation"
        )
        return sandbox_id

    if project_id and not sandbox_id:
        if get_project_fn is None:

            async def get_project_fn(*, project_id: str, workspace_id: str) -> Any:
                from backend.app.services.project.project_manager import ProjectManager

                project_manager = ProjectManager(store)
                return await project_manager.get_project(
                    project_id,
                    workspace_id=workspace_id,
                )

        if get_or_create_project_sandbox_fn is None:

            async def get_or_create_project_sandbox_fn(
                *, project_id: str, workspace_id: str
            ) -> Optional[str]:
                from backend.app.services.sandbox.playbook_integration import (
                    SandboxPlaybookAdapter,
                )

                sandbox_adapter = SandboxPlaybookAdapter(store)
                return await sandbox_adapter.get_or_create_sandbox_for_project(
                    project_id=project_id,
                    workspace_id=workspace_id,
                )

        try:
            logger.info(
                "WorkflowOrchestrator: Getting project %s for workspace %s",
                project_id,
                workspace_id,
            )
            project_obj = await get_project_fn(
                project_id=project_id,
                workspace_id=workspace_id,
            )
            logger.info(
                "WorkflowOrchestrator: project_obj=%s",
                project_obj is not None,
            )
            if project_obj:
                logger.info(
                    "WorkflowOrchestrator: Playbook execution in Project mode: %s",
                    project_id,
                )
                try:
                    logger.info(
                        "WorkflowOrchestrator: Creating sandbox for project %s",
                        project_id,
                    )
                    sandbox_id = await get_or_create_project_sandbox_fn(
                        project_id=project_id,
                        workspace_id=workspace_id,
                    )
                    logger.info(
                        "WorkflowOrchestrator: Using unified sandbox %s for project %s",
                        sandbox_id,
                        project_id,
                    )
                except Exception as exc:
                    logger.error(
                        "WorkflowOrchestrator: Failed to get unified sandbox: %s",
                        exc,
                        exc_info=True,
                    )
            else:
                logger.warning(
                    "WorkflowOrchestrator: Project %s not found or doesn't belong to workspace %s",
                    project_id,
                    workspace_id,
                )
        except Exception as exc:
            logger.error(
                "WorkflowOrchestrator: Failed to create sandbox for project: %s",
                exc,
                exc_info=True,
            )

    if sandbox_id:
        return sandbox_id

    if create_execution_sandbox_fn is None:

        async def create_execution_sandbox_fn(
            *, workspace_id: str, execution_id: Optional[str], playbook_code: Optional[str]
        ) -> Optional[str]:
            from backend.app.services.sandbox.sandbox_manager import SandboxManager

            sandbox_manager = SandboxManager(store)
            return await sandbox_manager.create_sandbox(
                sandbox_type="project_repo",
                workspace_id=workspace_id,
                context={
                    "execution_id": execution_id,
                    "playbook_code": playbook_code,
                },
            )

    try:
        logger.info(
            "WorkflowOrchestrator: Creating execution sandbox for workspace %s",
            workspace_id,
        )
        sandbox_id = await create_execution_sandbox_fn(
            workspace_id=workspace_id,
            execution_id=execution_id,
            playbook_code=getattr(playbook_json, "playbook_code", None),
        )
        logger.info("WorkflowOrchestrator: Created execution sandbox %s", sandbox_id)
    except Exception as exc:
        logger.error(
            "WorkflowOrchestrator: Failed to create execution sandbox: %s",
            exc,
            exc_info=True,
        )

    return sandbox_id
