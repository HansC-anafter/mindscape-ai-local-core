"""Dispatch/finalize pipeline helpers for ``MeetingEngine``."""

import asyncio
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


async def stage_decompose_and_dispatch(
    meeting: Any,
    *,
    decision: str,
    action_intents: list,
    action_items: List[Dict[str, Any]],
    handoff_in: Optional[Any] = None,
) -> tuple:
    """S6: Dispatch gate → TaskDecomposer → IR compile → DispatchOrchestrator."""
    await meeting._emit_meeting_stage("dispatch", "準備派遣任務…")

    from backend.app.services.orchestration.meeting.dispatch_visibility import (
        build_gate_visibility,
        build_ir_compile_visibility,
        record_dispatch_visibility,
    )

    from backend.app.models.supervision_signals import SupervisionSignals
    from backend.app.services.orchestration.meeting.dispatch_gate import DispatchGate
    from backend.app.services.orchestration.supervision_signals_emitter import (
        SupervisionSignalsEmitter,
    )

    real_signals = SupervisionSignals()
    session_metadata = getattr(meeting.session, "metadata", None) or {}
    fallback_meta = (
        session_metadata.get("policy_gate_fallback")
        if isinstance(session_metadata, dict)
        else None
    )
    forced_dispatch_intent_ids = set()
    if isinstance(fallback_meta, dict):
        for field_name in ("replacement_intent_ids", "preserved_intent_ids"):
            raw_ids = fallback_meta.get(field_name)
            if not isinstance(raw_ids, list):
                continue
            for raw_intent_id in raw_ids:
                intent_id = str(raw_intent_id or "").strip()
                if intent_id:
                    forced_dispatch_intent_ids.add(intent_id)
    try:
        emitter = SupervisionSignalsEmitter()
        session_attempts = []
        try:
            from backend.app.models.phase_attempt import PhaseAttempt

            phase_attempts_meta = (meeting.session.metadata or {}).get(
                "phase_attempts", {}
            )
            for attempt_dict in phase_attempts_meta.values():
                try:
                    session_attempts.append(PhaseAttempt.model_validate(attempt_dict))
                except Exception:
                    pass
        except Exception:
            pass

        session_start = getattr(meeting.session, "created_at", None)
        real_signals = emitter.compute(
            attempts=session_attempts,
            session_start=session_start,
            session_metadata=meeting.session.metadata or {},
        )
        logger.debug(
            "L5→L3 signals: risk_remaining=%.2f retries=%d failure_rate=%.2f quality=%.2f acceptance=%.2f remediation_round=%d session_age=%.0fs budget_pressure=%s",
            real_signals.risk_budget_remaining,
            real_signals.retry_budget_remaining,
            real_signals.historical_failure_rate,
            real_signals.quality_score,
            real_signals.acceptance_pass_rate,
            real_signals.remediation_round,
            real_signals.session_age_s,
            real_signals.budget_pressure_high,
        )
    except Exception as exc:
        logger.warning("L5 signal computation failed, using safe defaults: %s", exc)

    dispatch_gate = DispatchGate(signals=real_signals)
    gate_result = dispatch_gate.evaluate(action_intents)
    dispatch_intent_ids = set(gate_result.dispatch_intents)
    overridden_gate_intent_ids = forced_dispatch_intent_ids - dispatch_intent_ids
    if overridden_gate_intent_ids:
        logger.info(
            "Bypassing L3 DispatchGate for policy fallback intents in session %s: %s",
            getattr(meeting.session, "id", "?"),
            sorted(overridden_gate_intent_ids),
        )
        dispatch_intent_ids |= forced_dispatch_intent_ids
    dispatchable_intents = [
        intent for intent in action_intents if intent.intent_id in dispatch_intent_ids
    ]
    record_dispatch_visibility(
        meeting.session,
        build_gate_visibility(
            gate_result,
            dispatchable_count=len(dispatchable_intents),
            forced_dispatch_intent_ids=forced_dispatch_intent_ids,
        ),
    )
    plan_only_no_actuator = bool(action_items) and all(
        str(item.get("engine") or "").strip()
        and not item.get("tool_name")
        and not item.get("playbook_code")
        and not str(item.get("engine") or "").startswith(
            ("agent:", "tool:", "playbook:")
        )
        for item in action_items
    )

    for decision_item in gate_result.clarify_intents:
        if decision_item.intent_id in overridden_gate_intent_ids:
            continue
        logger.info(
            "L3 Gate CLARIFY: intent=%s reason=%s",
            decision_item.intent_id,
            decision_item.reason,
        )
    for decision_item in gate_result.deferred_intents:
        if decision_item.intent_id in overridden_gate_intent_ids:
            continue
        logger.info(
            "L3 Gate DEFER: intent=%s reason=%s",
            decision_item.intent_id,
            decision_item.reason,
        )
    for decision_item in gate_result.shrunk_intents:
        if decision_item.intent_id in overridden_gate_intent_ids:
            continue
        logger.info(
            "L3 Gate SHRINK_SCOPE: intent=%s reason=%s",
            decision_item.intent_id,
            decision_item.reason,
        )

    from backend.app.services.orchestration.task_decomposer import TaskDecomposer

    decomposer = None
    decomposed_phases = None
    skip_decomposition = bool(
        isinstance(fallback_meta, dict) and fallback_meta.get("replacement_intent_ids")
    )
    protected_playbook_items = [
        item
        for item in action_items
        if bool(item.get("preserve_atomic_playbook"))
    ]
    if protected_playbook_items:
        skip_decomposition = True
    if plan_only_no_actuator:
        skip_decomposition = True
    if skip_decomposition:
        if protected_playbook_items:
            logger.info(
                "Skipping TaskDecomposer for session %s because deterministic playbook routes must stay atomic (playbooks=%s)",
                getattr(meeting.session, "id", "?"),
                sorted(
                    {
                        str(item.get("playbook_code") or "").strip()
                        for item in protected_playbook_items
                    }
                ),
            )
        elif plan_only_no_actuator:
            logger.info(
                "Skipping TaskDecomposer for session %s because all action items are plan-only with no actuator",
                getattr(meeting.session, "id", "?"),
            )
        else:
            logger.info(
                "Skipping TaskDecomposer for session %s because policy fallback is active (replacement_intents=%d)",
                getattr(meeting.session, "id", "?"),
                len(fallback_meta.get("replacement_intent_ids") or []),
            )
    else:
        try:
            from backend.app.services.orchestration.meeting.meeting_llm_adapter import (
                MeetingLLMAdapter,
            )
            from backend.app.services.orchestration.task_decomposer import (
                DecompositionPolicy,
            )

            llm_adapter = MeetingLLMAdapter.from_engine(meeting)
            scale = "standard"
            if meeting._request_contract:
                scale = meeting._request_contract.scale_estimate.value
            policy = DecompositionPolicy.from_scale(scale)
            decomposer = TaskDecomposer(
                llm_adapter=llm_adapter,
                model_name=meeting.model_name or "",
                decomposition_policy=policy,
                max_phases=policy.max_phases_per_wave,
            )
            decomposed_phases = await decomposer.decompose(
                decision=decision,
                action_items=action_items,
                available_playbooks=getattr(meeting, "_available_playbooks_cache", ""),
                available_tools=meeting._build_tool_inventory_block(),
                force=True,
            )
            logger.info(
                "TaskDecomposer produced %d phases from %d action items",
                len(decomposed_phases) if decomposed_phases else 0,
                len(action_items),
            )
        except Exception as exc:
            logger.warning("TaskDecomposer failed (non-fatal): %s", exc)

    compiled_ir = None
    try:
        compiled_ir = meeting._compile_to_task_ir(
            decision=decision,
            action_items=action_items,
            handoff_in=handoff_in,
            action_intents=dispatchable_intents,
        )
        if compiled_ir and decomposed_phases:
            compiled_ir.phases = decomposed_phases
            logger.info(
                "TaskIR phases replaced by decomposer output (%d phases)",
                len(decomposed_phases),
            )
    except Exception as exc:
        logger.warning("Failed to compile TaskIR from meeting: %s", exc)

    if compiled_ir is not None:
        try:
            from backend.app.models.task_ir import PhaseIR
            from backend.app.services.orchestration.meeting.planner_contract_execution.tool_plan_compiler import (
                PlannerToolPlanCompiler,
            )

            planner_tool_plan = PlannerToolPlanCompiler().compile(
                request_contract=getattr(meeting, "_request_contract", None),
                session_metadata=dict(getattr(meeting.session, "metadata", {}) or {}),
                workspace_id=str(getattr(compiled_ir, "workspace_id", "") or ""),
                meeting_id=str(getattr(meeting.session, "id", "") or ""),
            )
            if planner_tool_plan:
                phase_id = "planner_tool_plan_execute"
                phase_name = "Execute meeting planner tool plan"
                compiled_ir.phases = [
                    PhaseIR(
                        id=phase_id,
                        name=phase_name,
                        description=(
                            "Execute the meeting-level planner tool plan through "
                            "installed capability planner_contract tools."
                        ),
                        preferred_engine="tool:meeting.execute_planner_tool_plan",
                        tool_name="meeting.execute_planner_tool_plan",
                        input_params={
                            "planner_tool_plan": planner_tool_plan.as_execution_payload()
                        },
                    )
                ]
                action_items[:] = [
                    {
                        "title": phase_name,
                        "description": (
                            "Execute the meeting-level planner tool plan through "
                            "installed capability planner_contract tools."
                        ),
                        "engine": "tool:meeting.execute_planner_tool_plan",
                        "tool_name": "meeting.execute_planner_tool_plan",
                        "input_params": {
                            "planner_tool_plan": planner_tool_plan.as_execution_payload()
                        },
                    }
                ]
                if getattr(meeting.session, "metadata", None) is not None:
                    meeting.session.metadata["planner_tool_plan"] = {
                        "plan_id": planner_tool_plan.plan_id,
                        "pack_id": planner_tool_plan.pack_id,
                        "category_count": len(planner_tool_plan.categories),
                        "step_count": len(planner_tool_plan.steps),
                    }
                logger.info(
                    "Planner tool plan compiled for session %s with %d categories and %d steps",
                    getattr(meeting.session, "id", "?"),
                    len(planner_tool_plan.categories),
                    len(planner_tool_plan.steps),
                )
        except Exception as exc:
            logger.warning("Planner tool plan compile failed (non-fatal): %s", exc)

    if compiled_ir is not None:
        try:
            from backend.app.services.orchestration.meeting.planner_contract_execution.binding_service import (
                PlannerContractBindingService,
            )

            binding_report = PlannerContractBindingService().bind_task_ir(
                task_ir=compiled_ir,
                request_contract=getattr(meeting, "_request_contract", None),
                session_metadata=dict(getattr(meeting.session, "metadata", {}) or {}),
            )
            if getattr(meeting.session, "metadata", None) is not None:
                meeting.session.metadata["planner_contract_binding"] = binding_report
            if binding_report.get("bound_count", 0):
                logger.info(
                    "Planner contract binding attached %d phases",
                    binding_report.get("bound_count", 0),
                )
        except Exception as exc:
            logger.warning("Planner contract binding failed (non-fatal): %s", exc)

    record_dispatch_visibility(
        meeting.session,
        build_ir_compile_visibility(
            compiled_ir,
            decomposed_phases=decomposed_phases,
            plan_only_no_actuator=plan_only_no_actuator,
        ),
    )

    if plan_only_no_actuator:
        for item in action_items:
            item["landing_status"] = "planned"
        return compiled_ir, {
            "status": "skipped",
            "reason": "plan_only_no_actuator",
            "total": len(action_items),
            "succeeded": 0,
            "failed": 0,
            "phase_results": [],
        }

    async def _on_wave_complete(wave_summary, task_ir):
        if not decomposer:
            return None
        try:
            return await decomposer.extend(
                existing_phases=task_ir.phases,
                wave_results=wave_summary.get("phase_results", {}),
                decision=decision,
                available_playbooks=getattr(meeting, "_available_playbooks_cache", ""),
            )
        except Exception as ext_exc:
            logger.warning("Iterative decomposition failed (non-fatal): %s", ext_exc)
            return None

    from backend.app.services.orchestration.dispatch_orchestrator import (
        DispatchOrchestrator,
    )

    orchestrator = DispatchOrchestrator(
        execution_launcher=meeting.execution_launcher,
        tasks_store=meeting.tasks_store,
        session=meeting.session,
        profile_id=meeting.profile_id,
        project_id=meeting.project_id,
        on_wave_complete=_on_wave_complete,
        handoff_registry_store=meeting._get_handoff_registry_store(),
        pack_dispatch_adapter=meeting._get_pack_dispatch_adapter(),
        available_playbooks_cache=getattr(meeting, "_available_playbooks_cache", ""),
    )
    dispatch_result = await orchestrator.execute(
        task_ir=compiled_ir,
        action_items=action_items,
    )
    return compiled_ir, dispatch_result


def stage_finalize(
    meeting: Any,
    *,
    meeting_result_cls: Any,
    user_message: str,
    decision: str,
    critic_notes: List[str],
    action_items: List[Dict[str, Any]],
    converged: bool,
    compiled_ir: Optional[Any],
    dispatch_result: Optional[Dict[str, Any]],
) -> Any:
    """S7: Minutes render, session close, supervisor, completion status."""
    minutes_md = meeting._render_minutes(
        user_message=user_message,
        decision=decision,
        critic_notes=critic_notes,
        action_items=action_items,
        converged=converged,
    )
    try:
        from backend.app.services.orchestration.meeting.dispatch_visibility import (
            build_dispatch_result_visibility,
            record_dispatch_visibility,
        )

        record_dispatch_visibility(
            meeting.session,
            build_dispatch_result_visibility(dispatch_result),
        )
    except Exception:
        pass
    meeting._close_session(
        minutes_md=minutes_md,
        action_items=action_items,
        dispatch_result=dispatch_result,
    )
    meeting._run_l2_bridge_pipeline()
    meeting._emit_minutes_message(minutes_md)

    try:
        from backend.app.services.orchestration.meeting.meeting_supervisor import (
            MeetingSupervisor,
        )

        supervisor = MeetingSupervisor(
            tasks_store=meeting.tasks_store,
            session_store=meeting.session_store,
        )

        async def _supervisor_task():
            try:
                summary = await supervisor.on_session_closed(meeting.session.id)
                logger.info(
                    "Session %s quality score: %.2f (%d/%d succeeded)",
                    meeting.session.id,
                    summary.get("score", 0),
                    summary.get("succeeded", 0),
                    summary.get("total_tasks", 0),
                )
            except Exception as inner_exc:
                logger.warning(
                    "Supervisor scoring failed for session %s: %s",
                    meeting.session.id,
                    inner_exc,
                )

        asyncio.create_task(_supervisor_task())
    except Exception as exc:
        logger.warning(
            "Supervisor hook failed for session %s: %s",
            meeting.session.id,
            exc,
        )

    from backend.app.models.completion_status import ExecutionCompletionStatus

    completion_status = ExecutionCompletionStatus.ACCEPTED
    if dispatch_result:
        task_statuses = []
        for phase_result in dispatch_result.get("phase_results", []):
            status = phase_result.get("status", "")
            if status:
                task_statuses.append(status)
        if task_statuses:
            completion_status = ExecutionCompletionStatus.from_task_statuses(
                task_statuses,
                has_dispatched=True,
            )
        elif not dispatch_result.get("phase_results"):
            completion_status = ExecutionCompletionStatus.COMPLETED

    return meeting_result_cls(
        session_id=meeting.session.id,
        minutes_md=minutes_md,
        decision=decision,
        action_items=action_items,
        event_ids=[event.id for event in meeting._events],
        task_ir=compiled_ir,
        dispatch_result=dispatch_result,
        completion_status=completion_status.value,
    )
