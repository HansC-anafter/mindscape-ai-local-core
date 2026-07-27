"""Playbook execution helpers for the WorkflowOrchestrator facade."""

import logging
from typing import Any, Dict, Optional

from backend.app.services.execution_core.clock import utc_now as _utc_now
from backend.app.services.workflow.result_mapper import map_tool_result_to_step_outputs
from backend.app.services.workflow.step_lifecycle import (
    build_gate_pause_result,
    maybe_invoke_step_hook,
    resolve_gate_action,
)

logger = logging.getLogger(__name__)


async def execute_playbook_steps_for_orchestrator(
    orchestrator: Any,
    playbook_json: Any,
    playbook_inputs: Dict[str, Any],
    execution_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
    profile_id: Optional[str] = None,
    project_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute all steps in a playbook through the orchestrator facade."""
    resume_checkpoint = orchestrator._resolve_resume_checkpoint(
        playbook_inputs=playbook_inputs,
        execution_id=execution_id,
        playbook_json=playbook_json,
    )
    logger.info(
        "WorkflowOrchestrator._execute_playbook_steps: Starting execution. "
        "project_id=%s, workspace_id=%s, playbook_inputs keys: %s",
        project_id,
        workspace_id,
        list(playbook_inputs.keys()),
    )
    sandbox_id = await orchestrator._ensure_execution_sandbox(
        playbook_json=playbook_json,
        execution_id=execution_id,
        workspace_id=workspace_id,
        project_id=project_id,
        resume_checkpoint=resume_checkpoint,
    )

    step_outputs, completed_steps = orchestrator._restore_checkpoint_state(
        playbook_inputs=playbook_inputs,
        resume_checkpoint=resume_checkpoint,
    )

    orchestrator._apply_execution_profile_registry_route(
        playbook_json=playbook_json,
        playbook_inputs=playbook_inputs,
    )

    while len(completed_steps) < len(playbook_json.steps):
        ready_steps = orchestrator._get_ready_steps(
            playbook_json.steps, completed_steps, playbook_inputs, step_outputs
        )
        logger.debug(
            "WorkflowOrchestrator._execute_playbook_steps: Found %s ready steps, "
            "playbook_inputs keys: %s",
            len(ready_steps),
            list(playbook_inputs.keys()),
        )

        if not ready_steps:
            raise RuntimeError("Circular dependency or missing dependencies detected")

        for step in ready_steps:
            try:
                step_index = len(completed_steps)
                logger.debug(
                    "WorkflowOrchestrator._execute_playbook_steps: Executing step %s, "
                    "playbook_inputs keys: %s",
                    step.id,
                    list(playbook_inputs.keys()),
                )

                await maybe_invoke_step_hook(
                    step_id=step.id,
                    hook_phase="pre_step",
                    hook_spec_model=(
                        step.hooks.pre_step
                        if hasattr(step, "hooks") and step.hooks
                        else None
                    ),
                    playbook_inputs=playbook_inputs,
                    execution_id=execution_id,
                    workspace_id=workspace_id,
                    profile_id=profile_id,
                    step_outputs=step_outputs,
                    strict=True,
                )

                step_result = await orchestrator._execute_single_step(
                    step,
                    playbook_json,
                    playbook_inputs,
                    step_outputs,
                    playbook_json.inputs,
                    execution_id=execution_id,
                    workspace_id=workspace_id,
                    profile_id=profile_id,
                    project_id=project_id,
                    step_index=step_index,
                )
                step_outputs[step.id] = step_result
                step_result_keys = (
                    list(step_result.keys()) if isinstance(step_result, dict) else "N/A"
                )
                step_result_preview = {}
                if isinstance(step_result, dict):
                    for key, value in step_result.items():
                        if isinstance(value, (list, dict)):
                            step_result_preview[key] = (
                                f"{type(value).__name__}(len={len(value)})"
                            )
                        else:
                            string_value = str(value)
                            step_result_preview[key] = (
                                string_value[:100]
                                if len(string_value) > 100
                                else string_value
                            )
                logger.info(
                    "Step %s completed successfully. Output keys: %s, Preview: %s",
                    step.id,
                    step_result_keys,
                    step_result_preview,
                )

                await maybe_invoke_step_hook(
                    step_id=step.id,
                    hook_phase="post_step",
                    hook_spec_model=(
                        step.hooks.post_step
                        if hasattr(step, "hooks") and step.hooks
                        else None
                    ),
                    playbook_inputs=playbook_inputs,
                    execution_id=execution_id,
                    workspace_id=workspace_id,
                    profile_id=profile_id,
                    step_outputs=step_outputs,
                )

                gate = getattr(step, "gate", None)
                if gate and getattr(gate, "required", False):
                    action = resolve_gate_action(
                        playbook_inputs=playbook_inputs,
                        step_id=step.id,
                    )
                    if action == "rejected":
                        raise RuntimeError(f"Gate rejected for step {step.id}")
                    if action != "approved":
                        partial_outputs = orchestrator._collect_final_outputs(
                            playbook_json.outputs, step_outputs
                        )
                        return build_gate_pause_result(
                            step_id=step.id,
                            gate=gate,
                            execution_id=execution_id,
                            playbook_code=getattr(playbook_json, "playbook_code", None),
                            sandbox_id=sandbox_id,
                            completed_steps=completed_steps,
                            step_outputs=step_outputs,
                            partial_outputs=partial_outputs,
                            created_at=_utc_now(),
                        )
                    completed_steps.add(step.id)
                    continue

                completed_steps.add(step.id)
            except Exception as exc:
                error_msg = str(exc)[:500] if len(str(exc)) > 500 else str(exc)
                logger.error(f"Step {step.id} failed: {error_msg}")
                if execution_id and workspace_id and orchestrator.store:
                    orchestrator._create_step_event(
                        execution_id=execution_id,
                        workspace_id=workspace_id,
                        profile_id=profile_id,
                        step_id=step.id,
                        step_name=step.id,
                        step_index=len(completed_steps),
                        status="failed",
                        error=str(exc),
                    )

                await maybe_invoke_step_hook(
                    step_id=step.id,
                    hook_phase="on_error",
                    hook_spec_model=(
                        step.hooks.on_error
                        if hasattr(step, "hooks") and step.hooks
                        else None
                    ),
                    playbook_inputs=playbook_inputs,
                    execution_id=execution_id,
                    workspace_id=workspace_id,
                    profile_id=profile_id,
                    step_outputs=step_outputs,
                    error=error_msg,
                )

                raise

    final_outputs = orchestrator._collect_final_outputs(
        playbook_json.outputs, step_outputs
    )
    return await orchestrator._finalize_playbook_execution(
        playbook_json=playbook_json,
        playbook_inputs=playbook_inputs,
        step_outputs=step_outputs,
        final_outputs=final_outputs,
        execution_id=execution_id,
        workspace_id=workspace_id,
        sandbox_id=sandbox_id,
    )


async def execute_single_step_iteration_for_orchestrator(
    orchestrator: Any,
    step: Any,
    playbook_json: Any,
    playbook_inputs: Dict[str, Any],
    step_outputs: Dict[str, Dict[str, Any]],
    playbook_input_defs: Dict[str, Any],
    execution_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
    profile_id: Optional[str] = None,
    project_id: Optional[str] = None,
    step_index: int = 0,
) -> Dict[str, Any]:
    """Execute a single step iteration for loop handling."""
    step._in_loop_iteration = True
    try:
        return await orchestrator._execute_single_step(
            step,
            playbook_json,
            playbook_inputs,
            step_outputs,
            playbook_input_defs,
            execution_id=execution_id,
            workspace_id=workspace_id,
            profile_id=profile_id,
            project_id=project_id,
            step_index=step_index,
        )
    finally:
        if hasattr(step, "_in_loop_iteration"):
            delattr(step, "_in_loop_iteration")


async def execute_single_step_for_orchestrator(
    orchestrator: Any,
    step: Any,
    playbook_json: Any,
    playbook_inputs: Dict[str, Any],
    step_outputs: Dict[str, Dict[str, Any]],
    playbook_input_defs: Dict[str, Any],
    execution_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
    profile_id: Optional[str] = None,
    project_id: Optional[str] = None,
    step_index: int = 0,
) -> Dict[str, Any]:
    """Execute a single playbook step through the orchestrator facade."""
    step_started_at = _utc_now()

    if execution_id and workspace_id and orchestrator.store:
        orchestrator._create_step_event(
            execution_id=execution_id,
            workspace_id=workspace_id,
            profile_id=profile_id,
            step_id=step.id,
            step_name=step.id,
            step_index=step_index,
            status="running",
            started_at=step_started_at,
        )

    try:
        if (
            hasattr(step, "for_each")
            and step.for_each
            and not hasattr(step, "_in_loop_iteration")
        ):
            return await orchestrator.step_loop.execute_step_with_loop(
                step,
                orchestrator._execute_single_step_iteration,
                playbook_json,
                playbook_inputs,
                step_outputs,
                playbook_input_defs,
                execution_id=execution_id,
                workspace_id=workspace_id,
                profile_id=profile_id,
                project_id=project_id,
                step_index=step_index,
            )

        playbook_inputs_with_context = playbook_inputs.copy()
        if workspace_id:
            playbook_inputs_with_context["workspace_id"] = workspace_id
        if execution_id:
            playbook_inputs_with_context["execution_id"] = execution_id

        workflow_context: Dict[str, Any] = {}
        if workspace_id:
            workflow_context["workspace_id"] = workspace_id
        if execution_id:
            workflow_context["execution_id"] = execution_id
        if profile_id:
            workflow_context["profile_id"] = profile_id

        resolved_inputs = orchestrator.template_engine.prepare_playbook_inputs(
            step, playbook_inputs_with_context, step_outputs, workflow_context
        )

        tool_id = None
        if hasattr(step, "tool_slot") and step.tool_slot:
            tool_id = await orchestrator._resolve_tool_slot_to_tool_id(
                step=step,
                workspace_id=workspace_id,
                project_id=project_id,
                playbook_inputs=playbook_inputs,
            )
        elif hasattr(step, "playbook_slot") and step.playbook_slot:
            return await orchestrator._execute_playbook_slot(
                step=step,
                resolved_inputs=resolved_inputs,
                execution_id=execution_id,
                workspace_id=workspace_id,
                profile_id=profile_id,
                project_id=project_id,
            )
        else:
            raise ValueError(
                "PlaybookStep must have 'tool', 'tool_slot', or 'playbook_slot'"
            )

        tool_result = await orchestrator._execute_tool_step(
            step=step,
            tool_id=tool_id,
            resolved_inputs=resolved_inputs,
            playbook_inputs=playbook_inputs,
            playbook_json=playbook_json,
            execution_id=execution_id,
            workspace_id=workspace_id,
            profile_id=profile_id,
        )

        step_output = map_tool_result_to_step_outputs(
            step_id=step.id,
            output_defs=step.outputs,
            tool_result=tool_result,
        )

        step_completed_at = _utc_now()

        if execution_id and workspace_id and orchestrator.store:
            orchestrator._create_step_event(
                execution_id=execution_id,
                workspace_id=workspace_id,
                profile_id=profile_id,
                step_id=step.id,
                step_name=step.id,
                step_index=step_index,
                status="completed",
                started_at=step_started_at,
                completed_at=step_completed_at,
            )

        return step_output
    except Exception as exc:
        step_completed_at = _utc_now()
        if execution_id and workspace_id and orchestrator.store:
            orchestrator._create_step_event(
                execution_id=execution_id,
                workspace_id=workspace_id,
                profile_id=profile_id,
                step_id=step.id,
                step_name=step.id,
                step_index=step_index,
                status="failed",
                started_at=step_started_at,
                completed_at=step_completed_at,
                error=str(exc),
            )
        raise
