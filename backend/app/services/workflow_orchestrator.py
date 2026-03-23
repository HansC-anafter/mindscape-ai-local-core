"""
Workflow Orchestrator

Executes multi-step workflows based on HandoffPlan and playbook.json.
Manages step dependencies, template resolution, and tool execution.
"""

import json
import logging
import asyncio
import os
import uuid
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


from pathlib import Path
from typing import Dict, Any, List, Optional, Set
from collections import defaultdict

from backend.app.models.playbook import (
    HandoffPlan,
    WorkflowStep,
    PlaybookJson,
    PlaybookKind,
    InteractionMode,
    RetryPolicy,
    ErrorHandlingStrategy,
)
from backend.app.services.workflow_template_engine import TemplateEngine
from backend.app.shared.tool_executor import ToolExecutor
from backend.app.services.remote_execution_child_tasks import (
    ensure_remote_workflow_step_child_shell,
)
from backend.app.services.tool_slot_resolver import (
    get_tool_slot_resolver,
    SlotNotFoundError,
)
from backend.app.services.tool_policy_engine import (
    get_tool_policy_engine,
    PolicyViolationError,
)
from backend.app.services.workflow_step_loop import WorkflowStepLoop
from backend.app.services.playbook_loaders import PlaybookJsonLoader

logger = logging.getLogger(__name__)


class RecoverableStepError(Exception):
    """Step 因暫時原因無法執行（LLM 不可用、server 離線等），可回退 PENDING 重試。"""
    def __init__(self, step_id: str, error_type: str, detail: str):
        self.step_id = step_id
        self.error_type = error_type
        self.detail = detail
        super().__init__(f"Step {step_id} recoverable error [{error_type}]: {detail}")


class WorkflowOrchestrator:
    """Orchestrates multi-step workflow execution"""

    def __init__(self, store=None):
        self.tool_executor = ToolExecutor()
        self.template_engine = TemplateEngine()
        self.step_loop = WorkflowStepLoop(
            self.template_engine, self.tool_executor, store
        )
        self.store = store

    def _get_cloud_connector(self):
        """Best-effort access to CloudConnector without depending on route modules."""
        try:
            from backend.app.main import app

            connector = getattr(app.state, "cloud_connector", None)
            if connector is not None:
                return connector
        except Exception:
            pass

        try:
            from backend.app.services.cloud_connector.connector import CloudConnector

            return CloudConnector()
        except Exception:
            logger.debug("WorkflowOrchestrator: CloudConnector unavailable", exc_info=True)
            return None

    def _resolve_remote_tool_route(
        self,
        playbook_inputs: Optional[Dict[str, Any]],
        *,
        step_id: str,
        tool_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Resolve a generic workflow-level remote tool route."""
        if not isinstance(playbook_inputs, dict):
            return None

        routes = playbook_inputs.get("_remote_tool_routes")
        if not isinstance(routes, dict):
            routes = playbook_inputs.get("remote_tool_routes")
        if not isinstance(routes, dict):
            return None

        for route_key in (step_id, tool_id):
            route = routes.get(route_key)
            if not isinstance(route, dict):
                continue
            execution_backend = str(
                route.get("execution_backend", "remote")
            ).strip().lower()
            if execution_backend != "remote":
                continue

            resolved_route = dict(route)
            resolved_route.setdefault("job_type", "tool")
            resolved_route.setdefault("tool_name", tool_id)
            if not resolved_route.get("capability_code") and "." in str(
                resolved_route["tool_name"]
            ):
                resolved_route["capability_code"] = str(
                    resolved_route["tool_name"]
                ).split(".", 1)[0]
            return resolved_route

        return None

    def _resolve_tool_model_override(
        self,
        *,
        tool_id: str,
        playbook_inputs: Optional[Dict[str, Any]],
        remote_route: Optional[Dict[str, Any]] = None,
        execution_profile: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Resolve model override for a tool execution.

        Default rule:
        - Local LLM tools inherit playbook-level ``_model_override``.
        - Remote LLM tools do NOT inherit local ``_model_override`` unless the
          route explicitly opts in with ``inherit_model_override=true``.
        - Remote routes may provide their own ``model_override`` /
          ``_model_override`` for runtime-specific selection.
        - Otherwise remote LLM tools prefer deployment-scoped cloud bindings.
        """
        if not (tool_id.startswith("core_llm.") or "llm" in tool_id.lower()):
            return None

        local_override = None
        if isinstance(playbook_inputs, dict):
            local_override = playbook_inputs.get("_model_override")

        if isinstance(remote_route, dict):
            explicit_override = (
                remote_route.get("model_override")
                or remote_route.get("_model_override")
            )
            if explicit_override:
                return str(explicit_override)

            if execution_profile:
                try:
                    from backend.app.services.capability_profile_resolver import (
                        CapabilityProfileResolver,
                    )

                    cap_profile = execution_profile.get("reasoning", "standard")
                    deployment_scope = str(
                        remote_route.get("model_deployment_scope", "cloud")
                    )
                    resolved_model, _variant = CapabilityProfileResolver().resolve(
                        cap_profile,
                        execution_profile=execution_profile,
                        deployment_scope=deployment_scope,
                    )
                    if resolved_model:
                        return str(resolved_model)
                except Exception as exc:
                    logger.warning(
                        "remote deployment-scoped model resolve failed (non-fatal): %s",
                        exc,
                    )

            if remote_route.get("inherit_model_override") and local_override:
                return str(local_override)
            return None

        if local_override:
            return str(local_override)
        return None

    async def _maybe_execute_tool_via_remote_route(
        self,
        *,
        step_id: str,
        tool_id: str,
        tool_inputs: Dict[str, Any],
        playbook_inputs: Dict[str, Any],
        execution_id: Optional[str],
        workspace_id: Optional[str],
    ) -> tuple[bool, Any]:
        """Dispatch a workflow tool step to remote execution when configured."""
        route = self._resolve_remote_tool_route(
            playbook_inputs,
            step_id=step_id,
            tool_id=tool_id,
        )
        if not route:
            return False, None

        if str(route.get("job_type", "tool")).strip().lower() != "tool":
            raise ValueError(
                f"Unsupported remote workflow job_type for step {step_id}: "
                f"{route.get('job_type')}"
            )

        if not workspace_id:
            raise ValueError(
                f"workspace_id is required for remote tool routing on step {step_id}"
            )

        connector = self._get_cloud_connector()
        if connector is None:
            error = "CloudConnector unavailable for remote tool routing"
            if route.get("fallback_local_on_error"):
                logger.warning(
                    "WorkflowOrchestrator: %s; falling back to local tool %s",
                    error,
                    tool_id,
                )
                return False, None
            raise RecoverableStepError(step_id, "remote_connector_unavailable", error)

        parent_trace_id = (
            playbook_inputs.get("trace_id")
            or execution_id
            or str(uuid.uuid4())
        )
        child_execution_id = str(uuid.uuid4())
        tenant_id = (
            route.get("tenant_id")
            or playbook_inputs.get("tenant_id")
            or os.getenv("CLOUD_TENANT_ID")
            or getattr(connector, "tenant_id", "default")
            or "default"
        )
        site_key = (
            route.get("site_key")
            or playbook_inputs.get("site_key")
            or tenant_id
        )
        target_device_id = route.get("target_device_id")
        timeout_seconds = float(route.get("timeout_seconds", 900.0))
        poll_interval_seconds = float(route.get("poll_interval_seconds", 2.0))
        tool_name = str(route.get("tool_name") or tool_id)
        capability_code = route.get("capability_code")
        remote_inputs = dict(tool_inputs or {})
        remote_inputs.setdefault("workspace_id", workspace_id)
        remote_inputs.setdefault("execution_id", child_execution_id)
        remote_inputs.setdefault("trace_id", parent_trace_id)
        remote_inputs.setdefault("tenant_id", tenant_id)
        if execution_id:
            remote_inputs.setdefault("parent_execution_id", execution_id)
        remote_inputs.setdefault("workflow_step_id", step_id)
        request_payload = {
            "tool_name": tool_name,
            "inputs": dict(remote_inputs),
        }
        parent_playbook_code = (
            playbook_inputs.get("playbook_code")
            if isinstance(playbook_inputs, dict)
            else None
        )
        child_tasks_store = None
        child_task = None
        try:
            child_tasks_store, child_task = ensure_remote_workflow_step_child_shell(
                child_execution_id=child_execution_id,
                parent_execution_id=execution_id,
                workspace_id=workspace_id,
                project_id=playbook_inputs.get("project_id")
                if isinstance(playbook_inputs, dict)
                else None,
                tenant_id=str(tenant_id),
                trace_id=str(parent_trace_id),
                step_id=step_id,
                tool_name=tool_name,
                capability_code=capability_code,
                parent_playbook_code=parent_playbook_code,
                request_payload=request_payload,
                target_device_id=(
                    str(target_device_id).strip() if target_device_id else None
                ),
                callback_payload={"mode": "local_core_terminal_event"},
            )
        except Exception:
            logger.warning(
                "WorkflowOrchestrator: failed to create remote child shell for %s/%s",
                step_id,
                tool_id,
                exc_info=True,
            )

        try:
            await connector.start_remote_execution(
                tenant_id=str(tenant_id),
                playbook_code=str(route.get("playbook_code") or tool_name),
                request_payload=request_payload,
                workspace_id=workspace_id,
                capability_code=capability_code,
                execution_id=child_execution_id,
                trace_id=str(parent_trace_id),
                job_type="tool",
                callback_payload={"mode": "local_core_terminal_event"},
                target_device_id=(
                    str(target_device_id).strip() if target_device_id else None
                ),
                site_key=str(site_key),
            )
            terminal_result = await connector.wait_for_remote_execution_terminal_result(
                child_execution_id,
                tenant_id=str(tenant_id),
                timeout_seconds=timeout_seconds,
                poll_interval_seconds=poll_interval_seconds,
            )
        except Exception as exc:
            if child_tasks_store and child_task:
                try:
                    failure_ctx = dict(child_task.execution_context or {})
                    failure_remote_execution = dict(
                        failure_ctx.get("remote_execution") or {}
                    )
                    failure_remote_execution["cloud_dispatch_state"] = "dispatch_failed"
                    failure_remote_execution["error"] = str(exc)
                    failure_ctx["remote_execution"] = failure_remote_execution
                    child_tasks_store.update_task(
                        child_task.id,
                        execution_context=failure_ctx,
                    )
                    from backend.app.models.workspace import TaskStatus

                    child_tasks_store.update_task_status(
                        child_task.id,
                        TaskStatus.FAILED,
                        result={
                            "remote_terminal_status": "dispatch_failed",
                            "provider_metadata": {},
                            "result_payload": None,
                        },
                        error=str(exc),
                        completed_at=_utc_now(),
                    )
                except Exception:
                    logger.warning(
                        "WorkflowOrchestrator: failed to mark child shell dispatch failure",
                        exc_info=True,
                    )
            if route.get("fallback_local_on_error"):
                logger.warning(
                    "WorkflowOrchestrator: remote dispatch failed for %s/%s: %s; "
                    "falling back to local execution",
                    step_id,
                    tool_id,
                    exc,
                )
                return False, None
            raise RecoverableStepError(
                step_id,
                "remote_tool_dispatch_failed",
                str(exc),
            ) from exc

        try:
            from backend.app.services.orchestration.governance_engine import (
                GovernanceEngine,
            )

            local_status = terminal_result.get("status")
            if local_status == "completed":
                callback_status = "succeeded"
            else:
                callback_status = local_status
            GovernanceEngine().process_remote_terminal_event(
                tenant_id=str(tenant_id),
                workspace_id=workspace_id,
                execution_id=child_execution_id,
                trace_id=str(parent_trace_id),
                status=str(callback_status),
                result_payload=terminal_result.get("result_payload"),
                error_message=terminal_result.get("error_message"),
                job_type="tool",
                capability_code=capability_code,
                playbook_code=str(route.get("playbook_code") or tool_name),
                provider_metadata={
                    "cloud_execution_id": child_execution_id,
                    "cloud_state": terminal_result.get("status"),
                    "workflow_step_id": step_id,
                    "tool_name": tool_name,
                },
            )
        except Exception:
            logger.warning(
                "WorkflowOrchestrator: failed to sync local child shell terminal result "
                "for %s/%s",
                step_id,
                tool_id,
                exc_info=True,
            )

        terminal_status = str(terminal_result.get("status") or "").strip().lower()
        if terminal_status == "completed":
            result_payload = terminal_result.get("result_payload")
            if isinstance(result_payload, dict) and "result" in result_payload:
                return True, result_payload.get("result")
            return True, result_payload

        error_message = (
            terminal_result.get("error_message")
            or f"remote tool execution ended with status={terminal_status}"
        )
        if route.get("fallback_local_on_error"):
            logger.warning(
                "WorkflowOrchestrator: remote execution failed for %s/%s with %s; "
                "falling back to local execution",
                step_id,
                tool_id,
                terminal_status,
            )
            return False, None
        if terminal_status in {"cancelled", "timeout"}:
            raise RecoverableStepError(
                step_id,
                f"remote_tool_{terminal_status}",
                error_message,
            )
        raise ValueError(f"Remote tool execution failed: {error_message}")

    def load_playbook_json(self, playbook_code: str) -> Optional[PlaybookJson]:
        """
        Load playbook.json file using PlaybookJsonLoader

        Args:
            playbook_code: Playbook code

        Returns:
            PlaybookJson model or None if not found
        """
        return PlaybookJsonLoader.load_playbook_json(playbook_code)

    async def execute_workflow(
        self,
        handoff_plan: HandoffPlan,
        execution_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        profile_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute workflow from HandoffPlan with parallel execution support

        Args:
            handoff_plan: HandoffPlan with workflow steps

        Returns:
            Dict with execution results for each step
        """
        results = {}
        workflow_context = handoff_plan.context.copy()
        # playbook_inputs are stored in workflow_context
        playbook_inputs = workflow_context.copy()

        dependency_graph = self._build_dependency_graph(handoff_plan.steps)
        completed_steps: Set[str] = set()
        pending_steps = {step.playbook_code: step for step in handoff_plan.steps}

        while pending_steps:
            ready_steps = self._get_ready_steps_for_parallel(
                pending_steps,
                completed_steps,
                dependency_graph,
                results,
                playbook_inputs,
            )

            if not ready_steps:
                remaining = list(pending_steps.keys())
                logger.error(
                    f"No ready steps found. Remaining: {remaining}, Completed: {completed_steps}"
                )
                break

            logger.info(
                f"Executing {len(ready_steps)} steps in parallel: {[s.playbook_code for s in ready_steps]}"
            )

            previous_results = {}
            for prev_playbook_code, prev_result in results.items():
                if prev_result.get("outputs"):
                    previous_results[prev_playbook_code] = prev_result["outputs"]

            step_tasks = [
                self._execute_step_with_retry(
                    step,
                    workflow_context,
                    previous_results,
                    execution_id=execution_id,
                    workspace_id=workspace_id,
                    profile_id=profile_id,
                    project_id=project_id,
                    step_index=len(completed_steps),
                )
                for step in ready_steps
            ]

            step_results = await asyncio.gather(*step_tasks, return_exceptions=True)

            for step, step_result in zip(ready_steps, step_results):
                if isinstance(step_result, Exception):
                    logger.error(
                        f"Step {step.playbook_code} raised exception: {step_result}"
                    )
                    step_result = {
                        "status": "error",
                        "error": str(step_result),
                        "error_type": "exception",
                    }

                logger.info(
                    f"WorkflowOrchestrator: step {step.playbook_code} result keys: {list(step_result.keys()) if isinstance(step_result, dict) else 'not dict'}"
                )
                logger.info(
                    f"WorkflowOrchestrator: step {step.playbook_code} result status: {step_result.get('status') if isinstance(step_result, dict) else 'unknown'}"
                )
                results[step.playbook_code] = step_result
                completed_steps.add(step.playbook_code)
                del pending_steps[step.playbook_code]

                if (
                    isinstance(step_result, dict)
                    and step_result.get("status") == "paused"
                ):
                    # Stop the workflow immediately. Caller can resume using checkpoint.
                    return {
                        "status": "paused",
                        "steps": results,
                        "context": workflow_context,
                        "checkpoint": step_result.get("checkpoint"),
                        "paused_step": step.playbook_code,
                        "pause_reason": step_result.get("pause_reason", "waiting_gate"),
                    }

                if step_result.get("status") == "completed" and step_result.get(
                    "outputs"
                ):
                    workflow_context.update(step_result["outputs"])

                if step_result.get("status") == "error":
                    error_handling = step.error_handling
                    if error_handling == ErrorHandlingStrategy.STOP_WORKFLOW:
                        logger.error(
                            f"Step {step.playbook_code} failed, stopping workflow"
                        )
                        pending_steps.clear()
                        break
                    elif error_handling == ErrorHandlingStrategy.CONTINUE_ON_ERROR:
                        logger.warning(
                            f"Step {step.playbook_code} failed, continuing workflow"
                        )
                    elif error_handling == ErrorHandlingStrategy.SKIP_STEP:
                        logger.warning(
                            f"Step {step.playbook_code} failed, skipping step"
                        )
                    elif error_handling in [
                        ErrorHandlingStrategy.RETRY_THEN_STOP,
                        ErrorHandlingStrategy.RETRY_THEN_CONTINUE,
                    ]:
                        if step_result.get("retries_exhausted"):
                            if error_handling == ErrorHandlingStrategy.RETRY_THEN_STOP:
                                logger.error(
                                    f"Step {step.playbook_code} failed after retries, stopping workflow"
                                )
                                pending_steps.clear()
                                break
                            else:
                                logger.warning(
                                    f"Step {step.playbook_code} failed after retries, continuing workflow"
                                )

        logger.info(
            f"WorkflowOrchestrator.execute_workflow: returning results with {len(results)} steps"
        )
        logger.info(
            f"WorkflowOrchestrator.execute_workflow: results keys: {list(results.keys())}"
        )
        return {"status": "completed", "steps": results, "context": workflow_context}

    def _build_dependency_graph(self, steps: List[WorkflowStep]) -> Dict[str, Set[str]]:
        """
        Build dependency graph for workflow steps

        Args:
            steps: List of workflow steps

        Returns:
            Dict mapping step playbook_code to set of dependencies (playbook_codes it depends on)
        """
        graph = {}
        step_map = {step.playbook_code: step for step in steps}

        for step in steps:
            dependencies = set()

            for input_name, input_value in step.inputs.items():
                if isinstance(input_value, str) and input_value.startswith(
                    "$previous."
                ):
                    parts = input_value.split(".")
                    if len(parts) >= 2:
                        prev_playbook_code = parts[1]
                        if prev_playbook_code in step_map:
                            dependencies.add(prev_playbook_code)

            for mapping in step.input_mapping.values():
                if isinstance(mapping, str) and mapping.startswith("$previous."):
                    parts = mapping.split(".")
                    if len(parts) >= 2:
                        prev_playbook_code = parts[1]
                        if prev_playbook_code in step_map:
                            dependencies.add(prev_playbook_code)

            graph[step.playbook_code] = dependencies

        return graph

    def _get_ready_steps_for_parallel(
        self,
        pending_steps: Dict[str, WorkflowStep],
        completed_steps: Set[str],
        dependency_graph: Dict[str, Set[str]],
        results: Dict[str, Dict[str, Any]],
        playbook_inputs: Optional[Dict[str, Any]] = None,
    ) -> List[WorkflowStep]:
        """
        Get steps that are ready to execute in parallel

        Args:
            pending_steps: Dict of pending steps by playbook_code
            completed_steps: Set of completed step playbook_codes
            dependency_graph: Dependency graph
            results: Current execution results
            playbook_inputs: Playbook inputs for condition evaluation

        Returns:
            List of ready steps that can be executed in parallel
        """
        ready_steps = []
        playbook_inputs = playbook_inputs or {}

        for playbook_code, step in pending_steps.items():
            if playbook_code in completed_steps:
                continue

            dependencies = dependency_graph.get(playbook_code, set())

            if not dependencies:
                if self._evaluate_condition(step, results, playbook_inputs):
                    ready_steps.append(step)
                continue

            all_dependencies_met = True
            for dep in dependencies:
                if dep not in completed_steps:
                    all_dependencies_met = False
                    break
                dep_result = results.get(dep, {})
                if dep_result.get("status") != "completed":
                    all_dependencies_met = False
                    break

            if all_dependencies_met:
                if self._evaluate_condition(step, results, playbook_inputs):
                    ready_steps.append(step)
                else:
                    logger.info(f"Step {playbook_code} condition not met, skipping")
                    completed_steps.add(playbook_code)
                    results[playbook_code] = {
                        "status": "skipped",
                        "reason": "condition_not_met",
                    }
                    del pending_steps[playbook_code]

        return ready_steps

    def _evaluate_condition(
        self,
        step: WorkflowStep,
        results: Dict[str, Dict[str, Any]],
        playbook_inputs: Optional[Dict[str, Any]] = None,
        step_outputs: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> bool:
        """
        Evaluate condition for workflow step

        Args:
            step: WorkflowStep with optional condition
            results: Current execution results
            playbook_inputs: Playbook inputs for template evaluation
            step_outputs: Step outputs dict for resolving step.X.Y references

        Returns:
            True if step should execute, False if should skip
        """
        if not step.condition:
            return True

        try:
            condition = step.condition.strip()

            # Handle Jinja2 template syntax: {{input.xxx or input.yyy}}
            if condition.startswith("{{") and condition.endswith("}}"):
                # Extract expression from {{...}}
                expr = condition[2:-2].strip()

                # Direct evaluation: input.xxx or input.yyy -> playbook_inputs.get('xxx') or playbook_inputs.get('yyy')
                input_dict = playbook_inputs or {}
                try:
                    # Replace input.xxx with input_dict.get('xxx')
                    import re

                    python_expr = expr
                    # Replace all input.xxx patterns with input_dict.get('xxx')
                    python_expr = re.sub(
                        r"input\.(\w+)", r"input_dict.get('\1')", python_expr
                    )
                    # Replace step.X.Y.Z with step_proxy['X']['Y']['Z']
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

                    _so = step_outputs or {}

                    def _step_get(*keys):
                        """Resolve step.X.Y.Z from step_outputs."""
                        val = _so
                        for k in keys:
                            if isinstance(val, dict):
                                val = val.get(k)
                            else:
                                return None
                        return val

                    result_value = eval(
                        python_expr,
                        {
                            "__builtins__": {},
                            "input_dict": input_dict,
                            "_step_get": _step_get,
                        },
                    )
                    logger.info(
                        f"Condition '{condition}' (expr: '{expr}') evaluated to: {result_value} (bool: {bool(result_value)}), input_dict keys: {list(input_dict.keys())}"
                    )
                    return bool(result_value)
                except Exception as e:
                    logger.warning(
                        f"Failed to evaluate condition '{condition}' for step {step.playbook_code}: {e}"
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

                    value = self._get_nested_value(prev_result, field_path)
                    return bool(value)

            elif condition.startswith("$context."):
                field_path = condition.replace("$context.", "")
                value = self._get_nested_value(results, field_path)
                return bool(value)

            else:
                return eval(
                    condition,
                    {
                        "__builtins__": {},
                        "results": results,
                        "previous": lambda code: results.get(code, {}),
                        "has_output": lambda code, key: self._has_output(
                            results, code, key
                        ),
                    },
                )

        except Exception as e:
            logger.warning(
                f"Failed to evaluate condition '{step.condition}' for step {step.playbook_code}: {e}"
            )
            return True

    def _get_nested_value(self, obj: Dict[str, Any], path: str) -> Any:
        """Get nested value from dict using dot notation"""
        parts = path.split(".")
        value = obj
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
            else:
                return None
            if value is None:
                return None
        return value

    def _has_output(
        self, results: Dict[str, Dict[str, Any]], playbook_code: str, output_key: str
    ) -> bool:
        """Check if a playbook has a specific output"""
        result = results.get(playbook_code, {})
        outputs = result.get("outputs", {})
        return output_key in outputs

    async def execute_workflow_step(
        self,
        step: WorkflowStep,
        workflow_context: Dict[str, Any],
        previous_results: Dict[str, Dict[str, Any]],
        execution_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        profile_id: Optional[str] = None,
        project_id: Optional[str] = None,
        step_index: int = 0,
    ) -> Dict[str, Any]:
        """
        Execute a single workflow step

        Args:
            step: WorkflowStep to execute
            workflow_context: Current workflow context
            previous_results: Results from previous steps

        Returns:
            Step execution result with outputs
        """
        playbook_json = self.load_playbook_json(step.playbook_code)
        if not playbook_json:
            raise ValueError(f"playbook.json not found for {step.playbook_code}")

        resolved_inputs = self.template_engine.prepare_workflow_step_inputs(
            step, previous_results, workflow_context
        )

        # Merge workflow_context into resolved_inputs to ensure inputs are available for template resolution
        # This is critical for playbook.json steps that use {{input.xxx}} templates
        # The workflow_context contains the original inputs passed to the playbook execution
        if workflow_context:
            # Merge workflow_context into resolved_inputs, but don't overwrite existing keys
            # IMPORTANT: playbook_inputs (from plan_preparer) should take precedence over workflow_context
            for key, value in workflow_context.items():
                if key not in resolved_inputs:
                    resolved_inputs[key] = value
            logger.info(
                f"WorkflowOrchestrator.execute_workflow_step: Merged workflow_context into resolved_inputs for {step.playbook_code}. Keys: {list(resolved_inputs.keys())}"
            )

        if step.kind == PlaybookKind.SYSTEM_TOOL:
            if InteractionMode.SILENT in step.interaction_mode:
                return await self._execute_silently(
                    playbook_json,
                    resolved_inputs,
                    execution_id,
                    workspace_id,
                    profile_id,
                    project_id,
                )
            else:
                return await self._execute_with_minimal_ui(
                    playbook_json,
                    resolved_inputs,
                    execution_id,
                    workspace_id,
                    profile_id,
                    project_id,
                )

        elif step.kind == PlaybookKind.USER_WORKFLOW:
            if InteractionMode.NEEDS_REVIEW in step.interaction_mode:
                logger.info(f"Step {step.playbook_code} requires review")
            if InteractionMode.CONVERSATIONAL in step.interaction_mode:
                return await self._execute_with_progress(
                    playbook_json,
                    resolved_inputs,
                    execution_id,
                    workspace_id,
                    profile_id,
                    project_id,
                )
            else:
                return await self._execute_with_minimal_ui(
                    playbook_json,
                    resolved_inputs,
                    execution_id,
                    workspace_id,
                    profile_id,
                    project_id,
                )

        else:
            raise ValueError(f"Unknown playbook kind: {step.kind}")

    async def _execute_silently(
        self,
        playbook_json: PlaybookJson,
        inputs: Dict[str, Any],
        execution_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        profile_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute playbook silently (system tool)"""
        return await self._execute_playbook_steps(
            playbook_json, inputs, execution_id, workspace_id, profile_id, project_id
        )

    async def _execute_with_minimal_ui(
        self,
        playbook_json: PlaybookJson,
        inputs: Dict[str, Any],
        execution_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        profile_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute playbook with minimal UI feedback"""
        return await self._execute_playbook_steps(
            playbook_json, inputs, execution_id, workspace_id, profile_id, project_id
        )

    async def _execute_with_progress(
        self,
        playbook_json: PlaybookJson,
        inputs: Dict[str, Any],
        execution_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        profile_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute playbook with progress feedback"""
        return await self._execute_playbook_steps(
            playbook_json, inputs, execution_id, workspace_id, profile_id, project_id
        )

    async def _execute_playbook_steps(
        self,
        playbook_json: PlaybookJson,
        playbook_inputs: Dict[str, Any],
        execution_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        profile_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute all steps in playbook.json

        Args:
            playbook_json: PlaybookJson definition
            playbook_inputs: Resolved playbook inputs
            execution_id: Execution ID
            workspace_id: Workspace ID
            profile_id: Profile ID
            project_id: Project ID for sandbox context

        Returns:
            Dict with step outputs and final playbook outputs
        """
        # Best-effort resume support:
        # - If _workflow_checkpoint is provided in inputs, reuse sandbox + step_outputs.
        # - Gate decisions are passed via inputs.gate_decisions[step_id].action = "approved"|"rejected".
        resume_checkpoint = None
        try:
            if isinstance(playbook_inputs, dict):
                candidate = playbook_inputs.get("_workflow_checkpoint")
                if isinstance(candidate, dict):
                    if candidate.get("execution_id") == execution_id and candidate.get(
                        "playbook_code"
                    ) == getattr(playbook_json, "playbook_code", None):
                        resume_checkpoint = candidate
        except Exception:
            resume_checkpoint = None

        # Create sandbox for execution (with or without project), unless resuming with a known sandbox_id
        sandbox_id = None
        if isinstance(resume_checkpoint, dict):
            sandbox_id = resume_checkpoint.get("sandbox_id") or None
        logger.info(
            f"WorkflowOrchestrator._execute_playbook_steps: Starting execution. project_id={project_id}, workspace_id={workspace_id}, playbook_inputs keys: {list(playbook_inputs.keys())}"
        )
        if workspace_id:
            try:
                from backend.app.services.sandbox.sandbox_manager import SandboxManager

                sandbox_manager = SandboxManager(self.store)

                if project_id and not sandbox_id:
                    # Create sandbox for project
                    try:
                        from backend.app.services.project.project_manager import (
                            ProjectManager,
                        )
                        from backend.app.services.sandbox.playbook_integration import (
                            SandboxPlaybookAdapter,
                        )

                        project_manager = ProjectManager(self.store)
                        logger.info(
                            f"WorkflowOrchestrator: Getting project {project_id} for workspace {workspace_id}"
                        )
                        project_obj = await project_manager.get_project(
                            project_id, workspace_id=workspace_id
                        )
                        logger.info(
                            f"WorkflowOrchestrator: project_obj={project_obj is not None}"
                        )
                        if project_obj:
                            logger.info(
                                f"WorkflowOrchestrator: Playbook execution in Project mode: {project_id}"
                            )
                            sandbox_adapter = SandboxPlaybookAdapter(self.store)
                            try:
                                logger.info(
                                    f"WorkflowOrchestrator: Creating sandbox for project {project_id}"
                                )
                                sandbox_id = await sandbox_adapter.get_or_create_sandbox_for_project(
                                    project_id=project_id, workspace_id=workspace_id
                                )
                                logger.info(
                                    f"WorkflowOrchestrator: Using unified sandbox {sandbox_id} for project {project_id}"
                                )
                            except Exception as e:
                                logger.error(
                                    f"WorkflowOrchestrator: Failed to get unified sandbox: {e}",
                                    exc_info=True,
                                )
                        else:
                            logger.warning(
                                f"WorkflowOrchestrator: Project {project_id} not found or doesn't belong to workspace {workspace_id}"
                            )
                    except Exception as e:
                        logger.error(
                            f"WorkflowOrchestrator: Failed to create sandbox for project: {e}",
                            exc_info=True,
                        )

                # If no sandbox created yet (no project or project sandbox creation failed), create execution sandbox
                if not sandbox_id:
                    try:
                        logger.info(
                            f"WorkflowOrchestrator: Creating execution sandbox for workspace {workspace_id}"
                        )
                        sandbox_id = await sandbox_manager.create_sandbox(
                            sandbox_type="project_repo",
                            workspace_id=workspace_id,
                            context={
                                "execution_id": execution_id,
                                "playbook_code": getattr(
                                    playbook_json, "playbook_code", None
                                ),
                            },
                        )
                        logger.info(
                            f"WorkflowOrchestrator: Created execution sandbox {sandbox_id}"
                        )
                    except Exception as e:
                        logger.error(
                            f"WorkflowOrchestrator: Failed to create execution sandbox: {e}",
                            exc_info=True,
                        )
            except Exception as e:
                logger.error(
                    f"WorkflowOrchestrator: Failed to create sandbox: {e}",
                    exc_info=True,
                )
        else:
            logger.warning(
                f"WorkflowOrchestrator: No workspace_id provided, skipping sandbox creation"
            )

        step_outputs: Dict[str, Dict[str, Any]] = {}
        completed_steps: Set[str] = set()

        if isinstance(resume_checkpoint, dict):
            cp_step_outputs = resume_checkpoint.get("step_outputs")
            cp_completed_steps = resume_checkpoint.get("completed_steps")
            if isinstance(cp_step_outputs, dict):
                step_outputs = cp_step_outputs
            if isinstance(cp_completed_steps, list):
                completed_steps = set(
                    [s for s in cp_completed_steps if isinstance(s, str)]
                )

            # If resuming a paused gate step, require explicit approval before marking it completed.
            paused_step_id = resume_checkpoint.get("paused_step_id")
            if isinstance(paused_step_id, str) and paused_step_id:
                decisions = {}
                if isinstance(playbook_inputs, dict) and isinstance(
                    playbook_inputs.get("gate_decisions"), dict
                ):
                    decisions = playbook_inputs.get("gate_decisions") or {}
                decision = (
                    decisions.get(paused_step_id)
                    if isinstance(decisions, dict)
                    else None
                )
                action = (
                    decision.get("action") if isinstance(decision, dict) else decision
                )
                if action == "approved":
                    completed_steps.add(paused_step_id)

        # ── v3.1 Gap-A: execution_profile → resolver → _model_override ──
        # If playbook declares execution_profile and no _model_override is already present,
        # resolve it via CapabilityProfileResolver to determine the model for LLM steps.
        if (
            hasattr(playbook_json, "execution_profile")
            and playbook_json.execution_profile
            and not playbook_inputs.get("_model_override")
        ):
            try:
                from backend.app.services.capability_profile_resolver import (
                    CapabilityProfileResolver,
                )

                ep = playbook_json.execution_profile
                # Use reasoning tier as capability_profile, defaulting to 'standard'
                cap_profile = ep.get("reasoning", "standard")
                resolved_model, _variant = CapabilityProfileResolver().resolve(
                    cap_profile,
                    execution_profile=ep,
                    deployment_scope="local",
                )
                if resolved_model:
                    playbook_inputs["_model_override"] = resolved_model
                    logger.info(
                        "v3.1: execution_profile resolved _model_override=%s "
                        "(profile=%s, modalities=%s, locality=%s)",
                        resolved_model,
                        cap_profile,
                        ep.get("modalities"),
                        ep.get("locality"),
                    )
            except Exception as exc:
                logger.warning(
                    "v3.1: execution_profile resolve failed (non-fatal): %s", exc
                )

        while len(completed_steps) < len(playbook_json.steps):
            ready_steps = self._get_ready_steps(
                playbook_json.steps, completed_steps, playbook_inputs, step_outputs
            )
            logger.debug(
                f"WorkflowOrchestrator._execute_playbook_steps: Found {len(ready_steps)} ready steps, playbook_inputs keys: {list(playbook_inputs.keys())}"
            )

            if not ready_steps:
                raise RuntimeError(
                    "Circular dependency or missing dependencies detected"
                )

            for step in ready_steps:
                try:
                    step_index = len(completed_steps)
                    # Log playbook_inputs for debugging
                    logger.debug(
                        f"WorkflowOrchestrator._execute_playbook_steps: Executing step {step.id}, playbook_inputs keys: {list(playbook_inputs.keys())}"
                    )

                    # P3-4c: pre_step hook (failure prevents step execution)
                    if hasattr(step, "hooks") and step.hooks and step.hooks.pre_step:
                        try:
                            from backend.app.services.step_hook_invoker import (
                                invoke_step_hook,
                            )

                            await invoke_step_hook(
                                hook_name=f"pre_step:{step.id}",
                                hook_spec_model=step.hooks.pre_step,
                                playbook_inputs=playbook_inputs,
                                execution_id=execution_id,
                                workspace_id=workspace_id,
                                profile_id=profile_id,
                                step_id=step.id,
                                step_outputs=step_outputs,
                            )
                        except Exception as hook_err:
                            logger.error(
                                f"Step {step.id} pre_step hook failed, skipping step: {hook_err}"
                            )
                            raise ValueError(
                                f"pre_step hook failed for step '{step.id}': {hook_err}"
                            ) from hook_err

                    step_result = await self._execute_single_step(
                        step,
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
                        list(step_result.keys())
                        if isinstance(step_result, dict)
                        else "N/A"
                    )
                    step_result_preview = {}
                    if isinstance(step_result, dict):
                        for k, v in step_result.items():
                            if isinstance(v, (list, dict)):
                                step_result_preview[k] = (
                                    f"{type(v).__name__}(len={len(v)})"
                                )
                            else:
                                step_result_preview[k] = (
                                    str(v)[:100] if len(str(v)) > 100 else str(v)
                                )
                    logger.info(
                        f"Step {step.id} completed successfully. Output keys: {step_result_keys}, Preview: {step_result_preview}"
                    )

                    # P3-4c: post_step hook (non-fatal)
                    if hasattr(step, "hooks") and step.hooks and step.hooks.post_step:
                        try:
                            from backend.app.services.step_hook_invoker import (
                                invoke_step_hook,
                            )

                            await invoke_step_hook(
                                hook_name=f"post_step:{step.id}",
                                hook_spec_model=step.hooks.post_step,
                                playbook_inputs=playbook_inputs,
                                execution_id=execution_id,
                                workspace_id=workspace_id,
                                profile_id=profile_id,
                                step_id=step.id,
                                step_outputs=step_outputs,
                            )
                        except Exception as hook_err:
                            logger.warning(
                                f"Step {step.id} post_step hook failed (non-fatal): {hook_err}"
                            )

                    # Gate pause: stop after completing the step, wait for external approval.
                    gate = getattr(step, "gate", None)
                    if gate and getattr(gate, "required", False):
                        decisions = {}
                        if isinstance(playbook_inputs, dict) and isinstance(
                            playbook_inputs.get("gate_decisions"), dict
                        ):
                            decisions = playbook_inputs.get("gate_decisions") or {}
                        decision = (
                            decisions.get(step.id)
                            if isinstance(decisions, dict)
                            else None
                        )
                        action = (
                            decision.get("action")
                            if isinstance(decision, dict)
                            else decision
                        )
                        if action == "rejected":
                            raise RuntimeError(f"Gate rejected for step {step.id}")
                        if action != "approved":
                            partial_outputs = self._collect_final_outputs(
                                playbook_json.outputs, step_outputs
                            )
                            checkpoint = {
                                "execution_id": execution_id,
                                "playbook_code": getattr(
                                    playbook_json, "playbook_code", None
                                ),
                                "sandbox_id": sandbox_id,
                                "paused_step_id": step.id,
                                "gate": (
                                    gate.model_dump()
                                    if hasattr(gate, "model_dump")
                                    else gate
                                ),
                                "completed_steps": list(completed_steps),
                                "step_outputs": step_outputs,
                                "created_at": _utc_now().isoformat(),
                            }
                            result = {
                                "status": "paused",
                                "pause_reason": "waiting_gate",
                                "paused_step_id": step.id,
                                "gate": (
                                    gate.model_dump()
                                    if hasattr(gate, "model_dump")
                                    else gate
                                ),
                                "step_outputs": step_outputs,
                                "outputs": partial_outputs,
                                "checkpoint": checkpoint,
                            }
                            if sandbox_id:
                                result["sandbox_id"] = sandbox_id
                            return result
                        # Approved: mark the step completed and continue.
                        completed_steps.add(step.id)
                        continue

                    completed_steps.add(step.id)
                except Exception as e:
                    error_msg = str(e)[:500] if len(str(e)) > 500 else str(e)
                    logger.error(f"Step {step.id} failed: {error_msg}")
                    if execution_id and workspace_id and self.store:
                        self._create_step_event(
                            execution_id=execution_id,
                            workspace_id=workspace_id,
                            profile_id=profile_id,
                            step_id=step.id,
                            step_name=step.id,
                            step_index=len(completed_steps),
                            status="failed",
                            error=str(e),
                        )

                    # P3-4c: on_error hook (non-fatal)
                    if hasattr(step, "hooks") and step.hooks and step.hooks.on_error:
                        try:
                            from backend.app.services.step_hook_invoker import (
                                invoke_step_hook,
                            )

                            await invoke_step_hook(
                                hook_name=f"on_error:{step.id}",
                                hook_spec_model=step.hooks.on_error,
                                playbook_inputs=playbook_inputs,
                                execution_id=execution_id,
                                workspace_id=workspace_id,
                                profile_id=profile_id,
                                step_id=step.id,
                                step_outputs=step_outputs,
                                error=error_msg,
                            )
                        except Exception as hook_err:
                            logger.warning(
                                f"Step {step.id} on_error hook failed (non-fatal): {hook_err}"
                            )

                    raise

        final_outputs = self._collect_final_outputs(playbook_json.outputs, step_outputs)

        # Create artifacts from output_artifacts definitions if available
        if execution_id and workspace_id and self.store:
            try:
                from backend.app.services.playbook_output_artifact_creator import (
                    PlaybookOutputArtifactCreator,
                )
                from backend.app.services.stores.postgres.artifacts_store import (
                    PostgresArtifactsStore,
                )

                artifacts_store = PostgresArtifactsStore()
                artifact_creator = PlaybookOutputArtifactCreator(artifacts_store)

                # Get playbook_code and metadata
                playbook_code = getattr(playbook_json, "playbook_code", None)
                if (
                    not playbook_code
                    and hasattr(playbook_json, "metadata")
                    and playbook_json.metadata
                ):
                    playbook_code = getattr(
                        playbook_json.metadata, "playbook_code", None
                    )

                if not playbook_code:
                    logger.warning(
                        "Cannot determine playbook_code for artifact creation"
                    )
                    playbook_code = "unknown"

                # Get playbook metadata (contains output_artifacts)
                playbook_metadata = {}
                if playbook_code and playbook_code != "unknown":
                    from backend.app.services.playbook_service import PlaybookService

                    playbook_service = PlaybookService(store=self.store)
                    playbook = await playbook_service.get_playbook(playbook_code)
                    if playbook and hasattr(playbook, "metadata") and playbook.metadata:
                        # Convert metadata to dict
                        if hasattr(playbook.metadata, "__dict__"):
                            playbook_metadata = playbook.metadata.__dict__
                        elif isinstance(playbook.metadata, dict):
                            playbook_metadata = playbook.metadata
                        # Check for output_artifacts in playbook_json directly
                        if hasattr(playbook_json, "output_artifacts"):
                            playbook_metadata["output_artifacts"] = (
                                playbook_json.output_artifacts
                            )

                # Also check playbook_json directly for output_artifacts (from JSON file)
                # PlaybookJson model doesn't have output_artifacts field, but JSON file does
                # So we need to load it from the JSON file directly
                if playbook_code and playbook_code != "unknown":
                    try:
                        base_dir = Path(__file__).parent.parent.parent
                        playbook_json_path = (
                            base_dir / "playbooks" / "specs" / f"{playbook_code}.json"
                        )
                        if playbook_json_path.exists():
                            with open(playbook_json_path, "r", encoding="utf-8") as f:
                                playbook_json_data = json.load(f)
                                if "output_artifacts" in playbook_json_data:
                                    playbook_metadata["output_artifacts"] = (
                                        playbook_json_data["output_artifacts"]
                                    )
                    except Exception as e:
                        logger.warning(
                            f"Failed to load output_artifacts from JSON file: {e}"
                        )

                # Create artifacts
                if playbook_metadata.get("output_artifacts"):
                    # Build execution_context with sandbox_id if available
                    execution_context = {"execution_id": execution_id}
                    if sandbox_id:
                        execution_context["sandbox_id"] = sandbox_id
                        logger.info(
                            f"🔍 WorkflowOrchestrator: Passing sandbox_id={sandbox_id} to artifact creator"
                        )
                    else:
                        logger.warning(
                            f"🔍 WorkflowOrchestrator: No sandbox_id available for execution {execution_id}"
                        )

                    created_artifacts = (
                        await artifact_creator.create_artifacts_from_playbook_outputs(
                            playbook_code=playbook_code,
                            execution_id=execution_id,
                            workspace_id=workspace_id,
                            playbook_metadata=playbook_metadata,
                            step_outputs=step_outputs,
                            inputs=playbook_inputs,
                            execution_context=execution_context,
                        )
                    )

                    if created_artifacts:
                        logger.info(
                            f"Created {len(created_artifacts)} artifacts from playbook execution"
                        )
            except Exception as e:
                logger.error(
                    f"Failed to create artifacts from playbook outputs: {e}",
                    exc_info=True,
                )
                # Don't fail the execution if artifact creation fails

            # Preserve sandbox_id in execution_context if available
            logger.debug(
                f"Preserve sandbox_id check: sandbox_id={sandbox_id}, execution_id={execution_id}, workspace_id={workspace_id}"
            )
            if sandbox_id and execution_id and workspace_id:
                try:
                    from backend.app.services.stores.tasks_store import TasksStore

                    tasks_store = TasksStore()
                    logger.debug(f"Getting task by execution_id: {execution_id}")
                    task = tasks_store.get_task_by_execution_id(execution_id)
                    logger.debug(f"Task found: {task is not None}")
                    if task:
                        execution_context = task.execution_context or {}
                        execution_context["sandbox_id"] = sandbox_id
                        logger.debug(
                            f"Updating task {task.id} with sandbox_id={sandbox_id}"
                        )
                        tasks_store.update_task(
                            task.id, execution_context=execution_context
                        )
                        logger.debug(
                            f"WorkflowOrchestrator: Preserved sandbox_id={sandbox_id} in execution_context for execution {execution_id}"
                        )
                    else:
                        logger.debug(
                            f"Task not found for execution_id: {execution_id}"
                        )
                except Exception as e:
                    logger.error(
                        f"🔍 WorkflowOrchestrator: Failed to preserve sandbox_id in execution_context: {e}",
                        exc_info=True,
                    )
            else:
                logger.debug(
                    f"🔍 Skipping sandbox_id preservation: sandbox_id={sandbox_id}, execution_id={execution_id}, workspace_id={workspace_id}"
                )

        result = {
            "status": "completed",
            "step_outputs": step_outputs,
            "outputs": final_outputs,
        }

        # Include sandbox_id in result metadata so it can be saved by the caller
        if sandbox_id:
            result["sandbox_id"] = sandbox_id

        return result

    def _get_ready_steps(
        self,
        steps: List[Any],
        completed_steps: set,
        playbook_inputs: Optional[Dict[str, Any]] = None,
        step_outputs: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> List[Any]:
        """
        Get steps that are ready to execute (dependencies satisfied)

        Args:
            steps: List of steps to check
            completed_steps: Set of completed step IDs (will be modified if steps are skipped)
            playbook_inputs: Playbook inputs for condition evaluation
            step_outputs: Step outputs dict (will be updated with skipped steps)
        """
        ready = []
        for step in steps:
            if step.id in completed_steps:
                continue
            if all(dep in completed_steps for dep in step.depends_on):
                # Check condition if present
                if hasattr(step, "condition") and step.condition:
                    # Build results dict for condition evaluation
                    results = {
                        step_id: {
                            "status": "completed",
                            "outputs": (step_outputs or {}).get(step_id, {}),
                        }
                        for step_id in completed_steps
                    }
                    if not self._evaluate_condition(
                        step, results, playbook_inputs, step_outputs=step_outputs
                    ):
                        logger.info(f"Step {step.id} condition not met, skipping")
                        # Mark step as completed (skipped) to avoid circular dependency
                        completed_steps.add(step.id)
                        # Record skipped status in step_outputs if provided
                        if step_outputs is not None:
                            step_outputs[step.id] = {
                                "status": "skipped",
                                "reason": "condition_not_met",
                            }
                        continue
                ready.append(step)
        return ready

    async def _execute_single_step_iteration(
        self,
        step: Any,
        playbook_inputs: Dict[str, Any],
        step_outputs: Dict[str, Dict[str, Any]],
        playbook_input_defs: Dict[str, Any],
        execution_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        profile_id: Optional[str] = None,
        project_id: Optional[str] = None,
        step_index: int = 0,
    ) -> Dict[str, Any]:
        """Execute a single step iteration (used by loop handler)"""
        # Mark step as in loop iteration to prevent recursion
        step._in_loop_iteration = True
        try:
            return await self._execute_single_step(
                step,
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
            # Clean up the flag
            if hasattr(step, "_in_loop_iteration"):
                delattr(step, "_in_loop_iteration")

    async def _execute_single_step(
        self,
        step: Any,
        playbook_inputs: Dict[str, Any],
        step_outputs: Dict[str, Dict[str, Any]],
        playbook_input_defs: Dict[str, Any],
        execution_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        profile_id: Optional[str] = None,
        project_id: Optional[str] = None,
        step_index: int = 0,
    ) -> Dict[str, Any]:
        """
        Execute a single playbook step

        Args:
            step: PlaybookStep to execute
            playbook_inputs: Playbook input values
            step_outputs: Completed step outputs
            playbook_input_defs: Playbook input definitions

        Returns:
            Step output dict
        """
        step_started_at = _utc_now()

        if execution_id and workspace_id and self.store:
            self._create_step_event(
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
            # Check if step has for_each (loop support)
            # Only handle for_each at the top level, not in iterations
            if (
                hasattr(step, "for_each")
                and step.for_each
                and not hasattr(step, "_in_loop_iteration")
            ):
                # Execute step for each item in the array using loop handler
                return await self.step_loop.execute_step_with_loop(
                    step,
                    self._execute_single_step_iteration,
                    playbook_inputs,
                    step_outputs,
                    playbook_input_defs,
                    execution_id=execution_id,
                    workspace_id=workspace_id,
                    profile_id=profile_id,
                    project_id=project_id,
                    step_index=step_index,
                )

            # Add workspace_id to playbook_inputs for template resolution
            # This allows {{workspace_id}} template variable to be resolved
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

            resolved_inputs = self.template_engine.prepare_playbook_inputs(
                step, playbook_inputs_with_context, step_outputs, workflow_context
            )

            # Resolve tool: use tool_slot field (tool field is deprecated and removed)
            tool_id = None
            if hasattr(step, "tool_slot") and step.tool_slot:
                # Slot-based mode: resolve slot to tool_id
                slot_resolver = get_tool_slot_resolver(store=self.store)
                try:
                    tool_id = await slot_resolver.resolve(
                        slot=step.tool_slot,
                        workspace_id=workspace_id or "",
                        project_id=project_id,  # Use project_id from execution context
                    )
                    logger.info(
                        f"Resolved tool slot '{step.tool_slot}' to tool '{tool_id}'"
                    )
                except SlotNotFoundError as e:
                    logger.error(f"Failed to resolve tool slot '{step.tool_slot}': {e}")
                    raise ValueError(
                        f"Tool slot '{step.tool_slot}' not configured. Please set up a mapping in workspace settings."
                    )
            elif hasattr(step, "playbook_slot") and step.playbook_slot:
                # Composition slot: sub-playbook invocation (P3-4d)
                import os as _os

                if (
                    _os.getenv("ENABLE_PLAYBOOK_SLOT_RUNTIME", "false").lower()
                    != "true"
                ):
                    raise ValueError(
                        f"Step '{step.id}' uses playbook_slot '{step.playbook_slot}' "
                        f"but runtime dispatch is not enabled. "
                        f"Set ENABLE_PLAYBOOK_SLOT_RUNTIME=true to enable."
                    )

                # Depth guard: prevent unbounded recursion (max 3 levels)
                _MAX_PLAYBOOK_SLOT_DEPTH = 3
                _current_depth = getattr(self, "_playbook_slot_depth", 0)
                if _current_depth >= _MAX_PLAYBOOK_SLOT_DEPTH:
                    raise ValueError(
                        f"playbook_slot nesting depth exceeded max={_MAX_PLAYBOOK_SLOT_DEPTH} "
                        f"at step '{step.id}' -> '{step.playbook_slot}'"
                    )

                # Load sub-playbook spec
                sub_playbook_json = self.load_playbook_json(step.playbook_slot)
                if not sub_playbook_json:
                    raise ValueError(
                        f"Sub-playbook '{step.playbook_slot}' not found for "
                        f"playbook_slot step '{step.id}'"
                    )

                logger.info(
                    f"playbook_slot dispatch: step '{step.id}' -> "
                    f"sub-playbook '{step.playbook_slot}' (depth={_current_depth + 1})"
                )

                # Execute sub-playbook recursively with incremented depth
                _prev_depth = getattr(self, "_playbook_slot_depth", 0)
                self._playbook_slot_depth = _prev_depth + 1
                try:
                    sub_result = await self._execute_playbook_steps(
                        sub_playbook_json,
                        resolved_inputs,
                        execution_id=execution_id,
                        workspace_id=workspace_id,
                        profile_id=profile_id,
                        project_id=project_id,
                    )
                finally:
                    self._playbook_slot_depth = _prev_depth

                # Map sub-playbook final outputs through step.outputs
                # step.outputs = {"summary": "report", "grade": "score"}
                # sub_result = {"report": "...", "score": 42}
                step_output = {}
                for output_name, source_field in step.outputs.items():
                    step_output[output_name] = sub_result.get(source_field)
                return step_output

            else:
                raise ValueError(
                    "PlaybookStep must have 'tool', 'tool_slot', or 'playbook_slot'"
                )

            # Check policy constraints if tool_policy is specified
            if hasattr(step, "tool_policy") and step.tool_policy:
                policy_engine = get_tool_policy_engine()
                try:
                    policy_engine.check(
                        tool_id=tool_id,
                        policy=step.tool_policy,
                        workspace_id=workspace_id,
                    )
                except PolicyViolationError as e:
                    logger.error(f"Tool '{tool_id}' violates policy: {e}")
                    raise ValueError(f"Tool execution blocked by policy: {str(e)}")

            # Execute tool - pass profile_id only for tools that need it (e.g., LLM tools)
            tool_inputs = resolved_inputs.copy()
            # Only add profile_id for core_llm tools or tools that explicitly require it
            if profile_id and (
                tool_id.startswith("core_llm.") or "llm" in tool_id.lower()
            ):
                tool_inputs["profile_id"] = profile_id

            remote_route = self._resolve_remote_tool_route(
                playbook_inputs,
                step_id=step.id,
                tool_id=tool_id,
            )

            # v3.1: Propagate _model_override to local LLM tools, but do not
            # leak workstation runtime selection into remote executors unless a
            # route explicitly requests it.
            _model_override = self._resolve_tool_model_override(
                tool_id=tool_id,
                playbook_inputs=playbook_inputs,
                remote_route=remote_route,
                execution_profile=getattr(playbook_json, "execution_profile", None),
            )
            if _model_override:
                tool_inputs["_model_override"] = _model_override

            handled_remotely, remote_tool_result = (
                await self._maybe_execute_tool_via_remote_route(
                    step_id=step.id,
                    tool_id=tool_id,
                    tool_inputs=tool_inputs,
                    playbook_inputs=playbook_inputs,
                    execution_id=execution_id,
                    workspace_id=workspace_id,
                )
            )
            if handled_remotely:
                tool_result = remote_tool_result
            else:
                tool_result = await self.tool_executor.execute_tool(tool_id, **tool_inputs)

            if isinstance(tool_result, dict) and tool_result.get("status") == "error":
                error_msg = tool_result.get("error", "Unknown tool error")
                if tool_result.get("recoverable"):
                    raise RecoverableStepError(step.id, error_type=tool_result.get("error_type", "recoverable"), detail=error_msg)
                else:
                    raise ValueError(f"Step {step.id} tool error: {error_msg}")

            step_output = {}
            for output_name, tool_field in step.outputs.items():
                if isinstance(tool_result, dict):
                    # Handle empty tool_field (use entire tool_result)
                    if not tool_field or tool_field == "":
                        value = tool_result
                        logger.debug(
                            f"Step {step.id} output mapping: output_name={output_name}, using entire tool_result (len={len(tool_result)})"
                        )
                    else:
                        # Handle dot-separated field paths (e.g., "extracted_data.topics")
                        value = tool_result
                        tool_result_keys = (
                            list(tool_result.keys())
                            if isinstance(tool_result, dict)
                            else "N/A"
                        )
                        logger.debug(
                            f"Step {step.id} output mapping: output_name={output_name}, tool_field={tool_field}, tool_result_keys={tool_result_keys}"
                        )
                        for field_part in tool_field.split("."):
                            if isinstance(value, dict):
                                value = value.get(field_part)
                                logger.debug(
                                    f"Step {step.id} output mapping: field_part={field_part}, value_type={type(value).__name__ if value is not None else 'None'}"
                                )
                            else:
                                value = None
                                break
                            if value is None:
                                break

                        if value is None:
                            raise ValueError(
                                f"Step {step.id} required output '{output_name}' "
                                f"(field='{tool_field}') not found in tool result"
                            )
                        else:
                            value_preview = (
                                f"{type(value).__name__}(len={len(value)})"
                                if isinstance(value, (list, dict))
                                else str(value)[:100]
                            )
                            logger.debug(
                                f"Step {step.id} output mapping success: {output_name}={value_preview}"
                            )
                    step_output[output_name] = value
                else:
                    step_output[output_name] = tool_result

            step_completed_at = _utc_now()

            if execution_id and workspace_id and self.store:
                self._create_step_event(
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
        except Exception as e:
            step_completed_at = _utc_now()
            if execution_id and workspace_id and self.store:
                self._create_step_event(
                    execution_id=execution_id,
                    workspace_id=workspace_id,
                    profile_id=profile_id,
                    step_id=step.id,
                    step_name=step.id,
                    step_index=step_index,
                    status="failed",
                    started_at=step_started_at,
                    completed_at=step_completed_at,
                    error=str(e),
                )
            raise

    def _collect_final_outputs(
        self, output_defs: Dict[str, Any], step_outputs: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Collect final playbook outputs from step outputs

        Args:
            output_defs: Playbook output definitions
            step_outputs: All step outputs

        Returns:
            Final playbook outputs
        """
        final_outputs = {}
        for output_name, output_def in output_defs.items():
            source_path = output_def.source
            parts = source_path.split(".")
            if len(parts) >= 3 and parts[0] == "step":
                step_id = parts[1]
                output_key = ".".join(parts[2:])
                if step_id in step_outputs:
                    final_outputs[output_name] = step_outputs[step_id].get(output_key)
        return final_outputs

    def _create_step_event(
        self,
        execution_id: str,
        workspace_id: str,
        profile_id: Optional[str],
        step_id: str,
        step_name: str,
        step_index: int,
        status: str,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        error: Optional[str] = None,
    ):
        """Create PLAYBOOK_STEP event for step timeline"""
        if not self.store:
            return

        try:
            from backend.app.models.mindscape import MindEvent, EventType, EventActor

            event = MindEvent(
                id=str(uuid.uuid4()),
                timestamp=_utc_now(),
                actor=EventActor.SYSTEM,
                channel="workflow_orchestrator",
                profile_id=profile_id or "default-user",
                project_id=None,
                workspace_id=workspace_id,
                event_type=EventType.PLAYBOOK_STEP,
                payload={
                    "execution_id": execution_id,
                    "step_id": step_id,
                    "step_name": step_name,
                    "step_index": step_index,
                    "status": status,
                    "started_at": started_at.isoformat() if started_at else None,
                    "completed_at": completed_at.isoformat() if completed_at else None,
                    "error": error,
                },
                entity_ids=[execution_id, step_id],
                metadata={},
            )

            self.store.create_event(event, generate_embedding=False)
            logger.debug(
                f"Created PLAYBOOK_STEP event for step {step_id} (index {step_index})"
            )
        except Exception as e:
            logger.warning(f"Failed to create PLAYBOOK_STEP event: {e}")

    async def _execute_step_with_retry(
        self,
        step: WorkflowStep,
        workflow_context: Dict[str, Any],
        previous_results: Dict[str, Dict[str, Any]],
        execution_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        profile_id: Optional[str] = None,
        project_id: Optional[str] = None,
        step_index: int = 0,
    ) -> Dict[str, Any]:
        """
        Execute workflow step with retry logic

        Args:
            step: WorkflowStep to execute
            workflow_context: Current workflow context
            previous_results: Results from previous steps

        Returns:
            Step execution result with outputs or error
        """
        retry_policy = step.retry_policy
        if not retry_policy:
            retry_policy = self._get_default_retry_policy(step.kind)

        last_error = None
        for attempt in range(retry_policy.max_retries + 1):
            try:
                if attempt > 0:
                    delay = self._calculate_retry_delay(attempt, retry_policy)
                    logger.info(
                        f"Retrying step {step.playbook_code} (attempt {attempt + 1}/{retry_policy.max_retries + 1}) after {delay}s"
                    )
                    import asyncio

                    await asyncio.sleep(delay)

                result = await self.execute_workflow_step(
                    step,
                    workflow_context,
                    previous_results,
                    execution_id=execution_id,
                    workspace_id=workspace_id,
                    profile_id=profile_id,
                    project_id=project_id,
                    step_index=step_index,
                )

                if result.get("status") == "completed":
                    if attempt > 0:
                        logger.info(
                            f"Step {step.playbook_code} succeeded after {attempt} retries"
                        )
                    return result

                last_error = result.get("error", "Unknown error")
                error_type = self._classify_error(last_error)

                if (
                    retry_policy.retryable_errors
                    and error_type not in retry_policy.retryable_errors
                ):
                    logger.warning(
                        f"Error type {error_type} is not retryable for step {step.playbook_code}"
                    )
                    return result

            except Exception as e:
                last_error = str(e)
                error_type = self._classify_error(last_error)
                logger.warning(
                    f"Step {step.playbook_code} failed (attempt {attempt + 1}/{retry_policy.max_retries + 1}): {e}"
                )

                if (
                    retry_policy.retryable_errors
                    and error_type not in retry_policy.retryable_errors
                ):
                    logger.warning(
                        f"Error type {error_type} is not retryable for step {step.playbook_code}"
                    )
                    return {
                        "status": "error",
                        "error": last_error,
                        "error_type": error_type,
                        "attempts": attempt + 1,
                        "retries_exhausted": False,
                    }

                if attempt < retry_policy.max_retries:
                    continue
                else:
                    return {
                        "status": "error",
                        "error": last_error,
                        "error_type": error_type,
                        "attempts": attempt + 1,
                        "retries_exhausted": True,
                    }

        return {
            "status": "error",
            "error": last_error or "Unknown error",
            "attempts": retry_policy.max_retries + 1,
            "retries_exhausted": True,
        }

    def _get_default_retry_policy(self, kind: PlaybookKind) -> RetryPolicy:
        """Get default retry policy based on playbook kind"""
        if kind == PlaybookKind.SYSTEM_TOOL:
            return RetryPolicy(
                max_retries=3,
                retry_delay=1.0,
                exponential_backoff=True,
                retryable_errors=[],
            )
        else:
            return RetryPolicy(
                max_retries=1,
                retry_delay=2.0,
                exponential_backoff=False,
                retryable_errors=[],
            )

    def _calculate_retry_delay(self, attempt: int, retry_policy: RetryPolicy) -> float:
        """Calculate retry delay based on attempt number and policy"""
        if retry_policy.exponential_backoff:
            return retry_policy.retry_delay * (2 ** (attempt - 1))
        else:
            return retry_policy.retry_delay

    def _classify_error(self, error: str) -> str:
        """Classify error type for retry decision"""
        error_lower = error.lower()
        if "timeout" in error_lower or "timed out" in error_lower:
            return "timeout"
        elif "network" in error_lower or "connection" in error_lower:
            return "network"
        elif "rate limit" in error_lower or "quota" in error_lower:
            return "rate_limit"
        elif "not found" in error_lower or "missing" in error_lower:
            return "not_found"
        elif "permission" in error_lower or "unauthorized" in error_lower:
            return "permission"
        elif "validation" in error_lower or "invalid" in error_lower:
            return "validation"
        else:
            return "unknown"
