"""Single phase dispatch router helpers for DispatchOrchestrator."""

from __future__ import annotations

import logging
from typing import Any, Dict

from backend.app.models.task_ir import PhaseIR

logger = logging.getLogger(__name__)


async def dispatch_phase(
    orchestrator: Any,
    phase: PhaseIR,
    action_item: Dict[str, Any],
    task_ir_id: str,
) -> Dict[str, Any]:
    """Dispatch a single phase using the canonical orchestrator facade."""
    attempt = orchestrator._create_attempt(phase, task_ir_id)

    if orchestrator._handoff_registry_store:
        registered = orchestrator._handoff_registry_store.register_attempt(
            idempotency_key=attempt.idempotency_key,
            task_ir_id=attempt.task_ir_id,
            phase_id=attempt.phase_id,
            attempt_number=attempt.attempt_number,
        )
        if registered is False:
            attempt.mark_skipped("duplicate_dispatch_intercepted")
            logger.warning(
                "Dispatch for %s blocked by idempotency guard (key=%s)",
                phase.id,
                attempt.idempotency_key,
            )
            return {"status": "skipped", "reason": "idempotency_conflict"}
        if registered is None:
            logger.warning(
                "Dispatch for %s proceeding without idempotency registry (key=%s)",
                phase.id,
                attempt.idempotency_key,
            )

    if phase.depends_on:
        upstream_context = {}
        for dep_id in phase.depends_on:
            dep_result = orchestrator._phase_results.get(dep_id)
            if dep_result:
                upstream_context[dep_id] = dep_result
        if upstream_context:
            action_item["_upstream_context"] = upstream_context

    landing_status = action_item.get("landing_status", "")
    if landing_status in ("policy_blocked", "dispatch_error", "boundary_violation"):
        attempt.mark_skipped(f"pre_blocked:{landing_status}")
        return {"status": "skipped", "reason": landing_status}

    target_ws = (
        phase.target_workspace_id
        or action_item.get("target_workspace_id")
        or getattr(orchestrator.session, "workspace_id", None)
        or ""
    )

    if orchestrator._lens_injector:
        try:
            lens_ctx = orchestrator._lens_injector.prepare_lens_context(
                profile_id=orchestrator.profile_id,
                workspace_id=target_ws,
                session_id=getattr(orchestrator.session, "id", None),
            )
            if lens_ctx:
                action_item["_lens_context"] = {
                    "effective_lens_hash": lens_ctx.get("effective_lens_hash"),
                    "style_rules": lens_ctx.get("style_rules"),
                    "emphasized_values": lens_ctx.get("emphasized_values"),
                    "anti_goals": lens_ctx.get("anti_goals"),
                }
        except Exception as exc:
            logger.warning("Lens injection failed for phase %s: %s", phase.id, exc)

    rescued_playbook = orchestrator._resolve_phase_playbook_alias(phase.tool_name)
    if rescued_playbook:
        original_tool_name = phase.tool_name
        phase.preferred_engine = f"playbook:{rescued_playbook}"
        phase.tool_name = None
        action_item["tool_name_original"] = (
            action_item.get("tool_name_original")
            or action_item.get("tool_name")
            or original_tool_name
        )
        action_item["tool_name"] = None
        action_item["playbook_code"] = rescued_playbook
        action_item["tool_name_rerouted_to_playbook"] = True

    engine = phase.preferred_engine
    if not engine:
        if phase.tool_name:
            engine = f"tool:{phase.tool_name}"
        else:
            engine = "agent:auto"
    playbook_code = orchestrator._extract_playbook_code(engine)

    if engine and engine.startswith("tool:"):
        playbook_code = None

    ir_provenance = orchestrator._build_ir_provenance(
        phase=phase,
        action_item=action_item,
        engine=engine,
    )

    attempt.mark_dispatched(
        engine=engine,
        playbook_code=playbook_code,
        target_workspace_id=target_ws,
    )

    try:
        if playbook_code and orchestrator.execution_launcher:
            result = await orchestrator._launch_playbook(
                playbook_code=playbook_code,
                action_item=action_item,
                target_workspace_id=target_ws,
                attempt=attempt,
                ir_provenance=ir_provenance,
            )
            attempt.mark_completed(result)
            action_item["landing_status"] = "launched"
            await orchestrator._publish_activity(
                "task_dispatched",
                {
                    "phase_id": phase.id,
                    "phase_name": phase.name,
                    "engine": engine,
                    "playbook_code": playbook_code,
                    "workspace_id": target_ws,
                    "execution_id": (
                        result.get("execution_id") if isinstance(result, dict) else None
                    ),
                },
            )
            return {"status": "completed", "workspace_id": target_ws, "result": result}
        if engine.startswith("agent:"):
            result = await orchestrator._dispatch_agent(
                phase=phase,
                action_item=action_item,
                target_workspace_id=target_ws,
                attempt=attempt,
                ir_provenance=ir_provenance,
                engine=engine,
            )
            attempt.mark_completed(result)
            action_item["landing_status"] = result.get("status", "launched")
            await orchestrator._publish_activity(
                "task_dispatched",
                {
                    "phase_id": phase.id,
                    "phase_name": phase.name,
                    "engine": engine,
                    "agent_id": result.get("agent_id"),
                    "workspace_id": target_ws,
                    "execution_id": result.get("execution_id"),
                },
            )
            return {"status": "completed", "workspace_id": target_ws, "result": result}
        if phase.tool_name:
            result = await orchestrator._dispatch_tool(
                phase=phase,
                action_item=action_item,
                target_workspace_id=target_ws,
                attempt=attempt,
                ir_provenance=ir_provenance,
            )
            attempt.mark_completed(result)
            action_item["landing_status"] = "task_created"
            await orchestrator._publish_activity(
                "task_dispatched",
                {
                    "phase_id": phase.id,
                    "phase_name": phase.name,
                    "engine": engine,
                    "tool_name": phase.tool_name,
                    "workspace_id": target_ws,
                },
            )
            return {"status": "completed", "workspace_id": target_ws, "result": result}

        result = orchestrator._project_to_task(
            phase=phase,
            action_item=action_item,
            target_workspace_id=target_ws,
            ir_provenance=ir_provenance,
        )
        attempt.mark_completed(result)
        action_item["landing_status"] = "planned"
        await orchestrator._publish_activity(
            "task_dispatched",
            {
                "phase_id": phase.id,
                "phase_name": phase.name,
                "engine": engine,
                "workspace_id": target_ws,
            },
        )
        return {"status": "completed", "workspace_id": target_ws, "result": result}
    except Exception as exc:
        error_msg = str(exc)
        attempt.mark_failed(error_msg)
        action_item["landing_status"] = "dispatch_error"
        action_item["landing_error"] = error_msg
        await orchestrator._publish_activity(
            "task_dispatch_failed",
            {
                "phase_id": phase.id,
                "phase_name": phase.name,
                "error": error_msg[:200],
            },
        )
        logger.warning("Phase %s dispatch failed: %s", phase.id, exc)
        return {"status": "failed", "error": error_msg}
