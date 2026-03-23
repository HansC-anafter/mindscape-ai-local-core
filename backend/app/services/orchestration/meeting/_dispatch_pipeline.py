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

    from backend.app.models.supervision_signals import SupervisionSignals
    from backend.app.services.orchestration.meeting.dispatch_gate import DispatchGate
    from backend.app.services.orchestration.supervision_signals_emitter import (
        SupervisionSignalsEmitter,
    )

    real_signals = SupervisionSignals()
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
    dispatchable_intents = [
        intent for intent in action_intents if intent.intent_id in dispatch_intent_ids
    ]

    for decision_item in gate_result.clarify_intents:
        logger.info(
            "L3 Gate CLARIFY: intent=%s reason=%s",
            decision_item.intent_id,
            decision_item.reason,
        )
    for decision_item in gate_result.deferred_intents:
        logger.info(
            "L3 Gate DEFER: intent=%s reason=%s",
            decision_item.intent_id,
            decision_item.reason,
        )
    for decision_item in gate_result.shrunk_intents:
        logger.info(
            "L3 Gate SHRINK_SCOPE: intent=%s reason=%s",
            decision_item.intent_id,
            decision_item.reason,
        )

    from backend.app.services.orchestration.task_decomposer import TaskDecomposer

    decomposer = None
    decomposed_phases = None
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
