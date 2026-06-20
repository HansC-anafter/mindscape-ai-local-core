"""Dispatch execution path helpers for DispatchOrchestrator."""

from __future__ import annotations

import logging
from typing import Any, Dict

from backend.app.models.phase_attempt import PhaseAttempt
from backend.app.models.task_ir import PhaseIR

logger = logging.getLogger(__name__)


async def launch_playbook(
    orchestrator: Any,
    *,
    playbook_code: str,
    action_item: Dict[str, Any],
    target_workspace_id: str,
    attempt: PhaseAttempt,
    ir_provenance: Dict[str, Any],
) -> Dict[str, Any]:
    """Launch a playbook through the configured execution launcher."""
    import uuid as _uuid

    from backend.app.core.domain_context import LocalDomainContext

    attempt.mark_started()

    inputs = {
        "task": action_item.get("description", ""),
        "meeting_session_id": getattr(orchestrator.session, "id", None),
        "thread_id": getattr(orchestrator.session, "thread_id", None),
        "workspace_id": target_workspace_id,
    }
    inputs["phase_attempt_id"] = attempt.id
    inputs["phase_id"] = attempt.phase_id
    inputs["task_ir_id"] = attempt.task_ir_id
    inputs["ir_provenance"] = ir_provenance

    extra_params = action_item.get("input_params")
    if isinstance(extra_params, dict):
        inputs.update(extra_params)
    orchestrator._apply_meeting_command_transport_context(inputs)

    if orchestrator._pack_dispatch_adapter:
        try:
            inputs = orchestrator._pack_dispatch_adapter.prepare_handoff(
                playbook_code=playbook_code,
                raw_inputs=inputs,
                phase=None,
                action_item=action_item,
                session=orchestrator.session,
                profile_id=orchestrator.profile_id,
                project_id=orchestrator.project_id,
            )
        except Exception as exc:
            logger.warning(
                "PackDispatchAdapter.prepare_handoff failed (non-fatal): %s", exc
            )
    orchestrator._apply_meeting_command_transport_context(inputs)

    ctx = LocalDomainContext(
        actor_id=orchestrator.profile_id,
        workspace_id=target_workspace_id,
    )
    trace_id = (
        inputs.get("trace_id")
        if isinstance(inputs.get("trace_id"), str) and inputs.get("trace_id")
        else str(_uuid.uuid4())
    )

    result = await orchestrator.execution_launcher.launch(
        playbook_code=playbook_code,
        inputs=inputs,
        ctx=ctx,
        project_id=orchestrator.project_id,
        trace_id=trace_id,
    )

    execution_id = result.get("execution_id")
    if execution_id:
        attempt.adapter_meta["execution_id"] = execution_id

    if execution_id and orchestrator.session:
        exec_ids = orchestrator.session.metadata.setdefault("execution_ids", [])
        if execution_id not in exec_ids:
            exec_ids.append(execution_id)

    return {
        "execution_id": execution_id,
        "playbook_code": playbook_code,
        "phase_id": attempt.phase_id,
        "attempt_id": attempt.id,
    }


async def dispatch_tool(
    orchestrator: Any,
    *,
    phase: PhaseIR,
    action_item: Dict[str, Any],
    target_workspace_id: str,
    attempt: PhaseAttempt,
    ir_provenance: Dict[str, Any],
) -> Dict[str, Any]:
    """Dispatch a tool_execution task."""
    import uuid

    from app.models.workspace import Task, TaskStatus
    from backend.app.services.executor_route_context import load_executor_route_context

    attempt.mark_started()
    route_context = await load_executor_route_context(target_workspace_id)
    planner_contract_binding = getattr(phase, "planner_contract_binding", None)
    planner_contract_payload = (
        planner_contract_binding.as_execution_context()
        if hasattr(planner_contract_binding, "as_execution_context")
        else planner_contract_binding.model_dump(mode="json", exclude_none=True)
        if hasattr(planner_contract_binding, "model_dump")
        else planner_contract_binding
        if isinstance(planner_contract_binding, dict)
        else None
    )
    task_params = {
        "tool_name": phase.tool_name,
        "input_params": phase.input_params or {},
        "title": phase.name,
        "description": phase.description or "",
    }
    task_execution_context = {
        "phase_id": attempt.phase_id,
        "attempt_id": attempt.id,
        "task_ir_id": attempt.task_ir_id,
        "profile_id": orchestrator.profile_id,
        "project_id": orchestrator.project_id,
        "inputs": phase.input_params or {},
        "tool_name": phase.tool_name,
        "capability_profile": phase.capability_profile,
        "executor_route_context": route_context,
        **ir_provenance,
    }
    if planner_contract_payload:
        task_params["planner_contract_binding"] = planner_contract_payload
        task_execution_context["planner_contract_binding"] = planner_contract_payload

    task = Task(
        id=str(uuid.uuid4()),
        workspace_id=target_workspace_id,
        message_id=attempt.id,
        pack_id=phase.tool_name or "meeting_dispatch",
        task_type="tool_execution",
        status=TaskStatus.PENDING,
        params=task_params,
        execution_context=task_execution_context,
        meeting_session_id=getattr(orchestrator.session, "id", None),
        project_id=orchestrator.project_id,
    )
    if orchestrator.tasks_store:
        orchestrator.tasks_store.create_task(task)
        attempt.adapter_meta["task_id"] = task.id
        attempt.adapter_meta["tool_name"] = phase.tool_name
        if planner_contract_payload:
            attempt.adapter_meta["planner_contract_binding_id"] = (
                planner_contract_payload.get("binding_id")
                if isinstance(planner_contract_payload, dict)
                else None
            )
        return {
            "task_id": task.id,
            "tool_name": phase.tool_name,
            "planner_contract_binding": planner_contract_payload,
        }
    return {
        "task_id": None,
        "tool_name": phase.tool_name,
        "planner_contract_binding": planner_contract_payload,
        "dry_run": True,
    }


async def dispatch_agent(
    orchestrator: Any,
    *,
    phase: PhaseIR,
    action_item: Dict[str, Any],
    target_workspace_id: str,
    attempt: PhaseAttempt,
    ir_provenance: Dict[str, Any],
    engine: str,
) -> Dict[str, Any]:
    """Dispatch a phase directly to the workspace executor runtime."""
    attempt.mark_started()

    workspace = await orchestrator._load_workspace(target_workspace_id)
    if workspace is None:
        return {"status": "planned", "reason": "workspace_not_found"}

    runtime_id = orchestrator._resolve_agent_runtime(engine=engine, workspace=workspace)
    if not runtime_id:
        return {"status": "planned", "reason": "no_executor_runtime"}

    from backend.app.services.workspace_agent_executor import WorkspaceAgentExecutor

    executor = WorkspaceAgentExecutor(workspace)
    available = await executor.check_agent_available(runtime_id)
    if not available:
        raise RuntimeError(
            f"Executor {runtime_id} unavailable for workspace {target_workspace_id}"
        )

    inputs = dict(action_item.get("input_params") or phase.input_params or {})
    inputs.setdefault("workspace_id", target_workspace_id)
    if orchestrator.project_id and "project_id" not in inputs:
        inputs["project_id"] = orchestrator.project_id
    if getattr(orchestrator.session, "thread_id", None) and "thread_id" not in inputs:
        inputs["thread_id"] = getattr(orchestrator.session, "thread_id", None)
    if getattr(orchestrator.session, "id", None) and "meeting_session_id" not in inputs:
        inputs["meeting_session_id"] = getattr(orchestrator.session, "id", None)
    meeting_command_context = orchestrator._apply_meeting_command_transport_context(
        inputs
    )

    conversation_context = orchestrator._build_agent_conversation_context(
        action_item=action_item,
        inputs=inputs,
        ir_provenance=ir_provenance,
    )
    task = orchestrator._build_agent_task(
        phase=phase,
        action_item=action_item,
        inputs=inputs,
    )
    context_overrides: Dict[str, Any] = {
        "meeting_session_id": getattr(orchestrator.session, "id", None),
        "thread_id": getattr(orchestrator.session, "thread_id", None),
        "project_id": orchestrator.project_id,
        "conversation_context": conversation_context,
        "inputs": inputs,
        "ir_provenance": ir_provenance,
        "file_hint": inputs.get("deliverable_path") or "",
    }
    context_overrides.update(meeting_command_context)
    try:
        from backend.app.services.executor_route_context import (
            build_executor_route_context,
        )

        route_context = build_executor_route_context(workspace)
        if route_context:
            context_overrides["executor_route_context"] = route_context
    except Exception:
        logger.warning(
            "Failed to build executor route context for workspace %s",
            target_workspace_id,
            exc_info=True,
        )
    result = await executor.execute(
        task=task,
        agent_id=runtime_id,
        context_overrides=context_overrides,
    )
    if not result.success:
        raise RuntimeError(result.error or f"{runtime_id} execution failed")

    execution_id = result.execution_id
    if execution_id:
        attempt.adapter_meta["execution_id"] = execution_id
        if orchestrator.session:
            exec_ids = orchestrator.session.metadata.setdefault("execution_ids", [])
            if execution_id not in exec_ids:
                exec_ids.append(execution_id)

    return {
        "status": "launched",
        "execution_id": execution_id,
        "agent_id": runtime_id,
        "trace_id": result.trace_id,
        "phase_id": attempt.phase_id,
        "attempt_id": attempt.id,
    }


def project_to_task(
    orchestrator: Any,
    *,
    phase: PhaseIR,
    action_item: Dict[str, Any],
    target_workspace_id: str,
    ir_provenance: Dict[str, Any],
) -> Dict[str, Any]:
    """Write a projection record to legacy tasks store."""
    if orchestrator.tasks_store:
        try:
            import uuid

            from app.models.workspace import Task, TaskStatus
            from backend.app.services.executor_route_context import (
                build_executor_route_context,
            )

            workspace = orchestrator._workspace_cache.get(target_workspace_id)
            route_context = (
                build_executor_route_context(workspace) if workspace is not None else None
            )

            task = Task(
                id=str(uuid.uuid4()),
                workspace_id=target_workspace_id,
                message_id=phase.id,
                pack_id="meeting_projection",
                task_type="planned",
                status=TaskStatus.PENDING,
                params={
                    "title": phase.name,
                    "description": phase.description
                    or action_item.get("description", ""),
                },
                execution_context={
                    "profile_id": orchestrator.profile_id,
                    "project_id": orchestrator.project_id,
                    "executor_route_context": route_context,
                    "ir_provenance": ir_provenance,
                },
                project_id=orchestrator.project_id,
            )
            orchestrator.tasks_store.create_task(task)
            return {"task_id": task.id, "projected": True}
        except Exception as exc:
            logger.warning("Projection write failed (non-fatal): %s", exc)
    return {"projected": False}
