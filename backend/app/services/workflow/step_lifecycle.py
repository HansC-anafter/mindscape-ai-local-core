"""Step lifecycle helpers for workflow execution."""

import logging
from datetime import datetime
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


async def maybe_invoke_step_hook(
    *,
    step_id: str,
    hook_phase: str,
    hook_spec_model: Any,
    playbook_inputs: Dict[str, Any],
    execution_id: Optional[str],
    workspace_id: Optional[str],
    profile_id: Optional[str],
    step_outputs: Dict[str, Dict[str, Any]],
    error: Optional[str] = None,
    strict: bool = False,
    invoke_step_hook_fn: Optional[Callable[..., Any]] = None,
) -> None:
    """Invoke a configured step hook when present."""
    if not hook_spec_model:
        return

    if invoke_step_hook_fn is None:
        from backend.app.services.step_hook_invoker import invoke_step_hook

        invoke_step_hook_fn = invoke_step_hook

    try:
        await invoke_step_hook_fn(
            hook_name=f"{hook_phase}:{step_id}",
            hook_spec_model=hook_spec_model,
            playbook_inputs=playbook_inputs,
            execution_id=execution_id,
            workspace_id=workspace_id,
            profile_id=profile_id,
            step_id=step_id,
            step_outputs=step_outputs,
            error=error,
        )
    except Exception as exc:
        if strict:
            logger.error(
                "Step %s %s hook failed, skipping step: %s",
                step_id,
                hook_phase,
                exc,
            )
            raise ValueError(
                f"{hook_phase} hook failed for step '{step_id}': {exc}"
            ) from exc

        logger.warning(
            "Step %s %s hook failed (non-fatal): %s",
            step_id,
            hook_phase,
            exc,
        )


def resolve_gate_action(
    *,
    playbook_inputs: Optional[Dict[str, Any]],
    step_id: str,
) -> Optional[Any]:
    """Resolve a gate decision action for a workflow step."""
    decisions = {}
    if isinstance(playbook_inputs, dict) and isinstance(
        playbook_inputs.get("gate_decisions"), dict
    ):
        decisions = playbook_inputs.get("gate_decisions") or {}

    decision = decisions.get(step_id) if isinstance(decisions, dict) else None
    if isinstance(decision, dict):
        return decision.get("action")
    return decision


def build_gate_pause_result(
    *,
    step_id: str,
    gate: Any,
    execution_id: Optional[str],
    playbook_code: Optional[str],
    sandbox_id: Optional[str],
    completed_steps: set[str],
    step_outputs: Dict[str, Dict[str, Any]],
    partial_outputs: Dict[str, Any],
    created_at: datetime,
) -> Dict[str, Any]:
    """Build the paused workflow payload for a gate wait."""
    gate_payload = gate.model_dump() if hasattr(gate, "model_dump") else gate
    checkpoint = {
        "execution_id": execution_id,
        "playbook_code": playbook_code,
        "sandbox_id": sandbox_id,
        "paused_step_id": step_id,
        "gate": gate_payload,
        "completed_steps": list(completed_steps),
        "step_outputs": step_outputs,
        "created_at": created_at.isoformat(),
    }
    result = {
        "status": "paused",
        "pause_reason": "waiting_gate",
        "paused_step_id": step_id,
        "gate": gate_payload,
        "step_outputs": step_outputs,
        "outputs": partial_outputs,
        "checkpoint": checkpoint,
    }
    if sandbox_id:
        result["sandbox_id"] = sandbox_id
    return result
