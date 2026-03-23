"""Scheduling helpers for workflow orchestration."""

import logging
import re
from typing import Any, Dict, List, Optional, Set

from backend.app.models.playbook import ErrorHandlingStrategy

logger = logging.getLogger(__name__)


def build_dependency_graph(steps: List[Any]) -> Dict[str, Set[str]]:
    """Build a dependency graph for workflow steps."""
    graph: Dict[str, Set[str]] = {}
    step_map = {step.playbook_code: step for step in steps}

    for step in steps:
        dependencies: Set[str] = set()

        for input_value in getattr(step, "inputs", {}).values():
            if isinstance(input_value, str) and input_value.startswith("$previous."):
                parts = input_value.split(".")
                if len(parts) >= 2 and parts[1] in step_map:
                    dependencies.add(parts[1])

        for mapping in getattr(step, "input_mapping", {}).values():
            if isinstance(mapping, str) and mapping.startswith("$previous."):
                parts = mapping.split(".")
                if len(parts) >= 2 and parts[1] in step_map:
                    dependencies.add(parts[1])

        graph[step.playbook_code] = dependencies

    return graph


def get_nested_value(obj: Dict[str, Any], path: str) -> Any:
    """Get nested value from a dict using dot notation."""
    parts = path.split(".")
    value: Any = obj
    for part in parts:
        if isinstance(value, dict):
            value = value.get(part)
        else:
            return None
        if value is None:
            return None
    return value


def has_output(
    results: Dict[str, Dict[str, Any]],
    playbook_code: str,
    output_key: str,
) -> bool:
    """Check whether a previous playbook result has a named output."""
    result = results.get(playbook_code, {})
    outputs = result.get("outputs", {})
    return output_key in outputs


def evaluate_condition(
    *,
    step: Any,
    results: Dict[str, Dict[str, Any]],
    playbook_inputs: Optional[Dict[str, Any]] = None,
    step_outputs: Optional[Dict[str, Dict[str, Any]]] = None,
) -> bool:
    """Evaluate whether a workflow step should execute."""
    if not step.condition:
        return True

    try:
        condition = step.condition.strip()

        if condition.startswith("{{") and condition.endswith("}}"):
            expr = condition[2:-2].strip()
            input_dict = playbook_inputs or {}
            try:
                python_expr = expr
                python_expr = re.sub(
                    r"input\.(\w+)",
                    r"input_dict.get('\1')",
                    python_expr,
                )
                python_expr = re.sub(
                    r"step\.(\w+)\.(\w+)\.(\w+)",
                    r"_step_get('\1', '\2', '\3')",
                    python_expr,
                )
                python_expr = re.sub(
                    r"step\.(\w+)\.(\w+)",
                    r"_step_get('\1', '\2')",
                    python_expr,
                )

                current_step_outputs = step_outputs or {}

                def _step_get(*keys):
                    value: Any = current_step_outputs
                    for key in keys:
                        if isinstance(value, dict):
                            value = value.get(key)
                        else:
                            return None
                    return value

                result_value = eval(
                    python_expr,
                    {
                        "__builtins__": {},
                        "input_dict": input_dict,
                        "_step_get": _step_get,
                    },
                )
                logger.info(
                    "Condition '%s' (expr: '%s') evaluated to: %s (bool: %s), input_dict keys: %s",
                    condition,
                    expr,
                    result_value,
                    bool(result_value),
                    list(input_dict.keys()),
                )
                return bool(result_value)
            except Exception as exc:
                logger.warning(
                    "Failed to evaluate condition '%s' for step %s: %s",
                    condition,
                    step.playbook_code,
                    exc,
                )
                return True

        if condition.startswith("$previous."):
            parts = condition.split(".")
            if len(parts) >= 3:
                prev_playbook_code = parts[1]
                field_path = ".".join(parts[2:])

                prev_result = results.get(prev_playbook_code, {})
                if prev_result.get("status") != "completed":
                    return False

                value = get_nested_value(prev_result, field_path)
                return bool(value)

        elif condition.startswith("$context."):
            field_path = condition.replace("$context.", "")
            value = get_nested_value(results, field_path)
            return bool(value)

        return bool(
            eval(
                condition,
                {
                    "__builtins__": {},
                    "results": results,
                    "previous": lambda code: results.get(code, {}),
                    "has_output": lambda code, key: has_output(results, code, key),
                },
            )
        )
    except Exception as exc:
        logger.warning(
            "Failed to evaluate condition '%s' for step %s: %s",
            step.condition,
            step.playbook_code,
            exc,
        )
        return True


def get_ready_steps_for_parallel(
    *,
    pending_steps: Dict[str, Any],
    completed_steps: Set[str],
    dependency_graph: Dict[str, Set[str]],
    results: Dict[str, Dict[str, Any]],
    playbook_inputs: Optional[Dict[str, Any]] = None,
) -> List[Any]:
    """Get workflow steps that are ready to execute in parallel."""
    ready_steps = []
    playbook_inputs = playbook_inputs or {}

    for playbook_code, step in list(pending_steps.items()):
        if playbook_code in completed_steps:
            continue

        dependencies = dependency_graph.get(playbook_code, set())
        if not dependencies:
            if evaluate_condition(
                step=step,
                results=results,
                playbook_inputs=playbook_inputs,
            ):
                ready_steps.append(step)
            continue

        all_dependencies_met = True
        for dependency in dependencies:
            if dependency not in completed_steps:
                all_dependencies_met = False
                break
            dependency_result = results.get(dependency, {})
            if dependency_result.get("status") != "completed":
                all_dependencies_met = False
                break

        if all_dependencies_met:
            if evaluate_condition(
                step=step,
                results=results,
                playbook_inputs=playbook_inputs,
            ):
                ready_steps.append(step)
            else:
                logger.info("Step %s condition not met, skipping", playbook_code)
                completed_steps.add(playbook_code)
                results[playbook_code] = {
                    "status": "skipped",
                    "reason": "condition_not_met",
                }
                del pending_steps[playbook_code]

    return ready_steps


def get_ready_steps(
    *,
    steps: List[Any],
    completed_steps: Set[str],
    playbook_inputs: Optional[Dict[str, Any]] = None,
    step_outputs: Optional[Dict[str, Dict[str, Any]]] = None,
) -> List[Any]:
    """Get serial playbook steps that are ready to execute."""
    ready = []
    for step in steps:
        if step.id in completed_steps:
            continue
        if all(dep in completed_steps for dep in step.depends_on):
            if hasattr(step, "condition") and step.condition:
                results = {
                    step_id: {
                        "status": "completed",
                        "outputs": (step_outputs or {}).get(step_id, {}),
                    }
                    for step_id in completed_steps
                }
                if not evaluate_condition(
                    step=step,
                    results=results,
                    playbook_inputs=playbook_inputs,
                    step_outputs=step_outputs,
                ):
                    logger.info("Step %s condition not met, skipping", step.id)
                    completed_steps.add(step.id)
                    if step_outputs is not None:
                        step_outputs[step.id] = {
                            "status": "skipped",
                            "reason": "condition_not_met",
                        }
                    continue
            ready.append(step)
    return ready


def build_previous_results(results: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Build previous playbook outputs for downstream template resolution."""
    previous_results = {}
    for playbook_code, result in results.items():
        if isinstance(result, dict) and result.get("outputs"):
            previous_results[playbook_code] = result["outputs"]
    return previous_results


def normalize_parallel_step_result(
    *,
    step_playbook_code: str,
    step_result: Any,
) -> Dict[str, Any]:
    """Normalize gathered asyncio results into workflow step result payloads."""
    if isinstance(step_result, Exception):
        logger.error("Step %s raised exception: %s", step_playbook_code, step_result)
        return {
            "status": "error",
            "error": str(step_result),
            "error_type": "exception",
        }

    logger.info(
        "WorkflowOrchestrator: step %s result keys: %s",
        step_playbook_code,
        list(step_result.keys()) if isinstance(step_result, dict) else "not dict",
    )
    logger.info(
        "WorkflowOrchestrator: step %s result status: %s",
        step_playbook_code,
        step_result.get("status") if isinstance(step_result, dict) else "unknown",
    )
    return step_result


def build_paused_workflow_result(
    *,
    step_playbook_code: str,
    results: Dict[str, Dict[str, Any]],
    workflow_context: Dict[str, Any],
    step_result: Dict[str, Any],
) -> Dict[str, Any]:
    """Build the paused top-level workflow result payload."""
    return {
        "status": "paused",
        "steps": results,
        "context": workflow_context,
        "checkpoint": step_result.get("checkpoint"),
        "paused_step": step_playbook_code,
        "pause_reason": step_result.get("pause_reason", "waiting_gate"),
    }


def apply_step_result_to_context(
    *,
    workflow_context: Dict[str, Any],
    step_result: Dict[str, Any],
) -> None:
    """Merge completed step outputs into the mutable workflow context."""
    if step_result.get("status") == "completed" and step_result.get("outputs"):
        workflow_context.update(step_result["outputs"])


def should_stop_workflow_after_error(
    *,
    step: Any,
    step_result: Dict[str, Any],
) -> bool:
    """Return whether an errored step should stop the workflow."""
    if step_result.get("status") != "error":
        return False

    error_handling = step.error_handling
    if error_handling == ErrorHandlingStrategy.STOP_WORKFLOW:
        logger.error("Step %s failed, stopping workflow", step.playbook_code)
        return True
    if error_handling == ErrorHandlingStrategy.CONTINUE_ON_ERROR:
        logger.warning("Step %s failed, continuing workflow", step.playbook_code)
        return False
    if error_handling == ErrorHandlingStrategy.SKIP_STEP:
        logger.warning("Step %s failed, skipping step", step.playbook_code)
        return False
    if error_handling in (
        ErrorHandlingStrategy.RETRY_THEN_STOP,
        ErrorHandlingStrategy.RETRY_THEN_CONTINUE,
    ) and step_result.get("retries_exhausted"):
        if error_handling == ErrorHandlingStrategy.RETRY_THEN_STOP:
            logger.error(
                "Step %s failed after retries, stopping workflow",
                step.playbook_code,
            )
            return True
        logger.warning(
            "Step %s failed after retries, continuing workflow",
            step.playbook_code,
        )
    return False
