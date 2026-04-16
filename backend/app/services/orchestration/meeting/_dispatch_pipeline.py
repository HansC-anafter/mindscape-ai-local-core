"""Dispatch/finalize pipeline helpers for ``MeetingEngine``."""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from backend.app.services.compile_job_reconciler import (
    closed_session_compile_failed,
    summarize_meeting_session_tasks,
)

logger = logging.getLogger(__name__)


def _load_executor_structured_program_spec(meeting: Any):
    from backend.app.models.program_spec import ProgramSpec

    metadata = getattr(getattr(meeting, "session", None), "metadata", None) or {}
    if metadata.get("last_program_spec_source") not in {
        "executor_structured",
        "request_contract_fallback",
    }:
        return None
    payload = metadata.get("last_program_spec")
    if not isinstance(payload, dict):
        return None
    try:
        return ProgramSpec.model_validate(payload)
    except Exception as exc:
        logger.warning("ProgramSpec bridge metadata invalid; falling back: %s", exc)
        return None


def _normalize_deliverable_specs(raw_deliverables: Any) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for raw in raw_deliverables or []:
        if hasattr(raw, "model_dump"):
            candidate = raw.model_dump()
        elif isinstance(raw, dict):
            candidate = dict(raw)
        else:
            continue
        normalized.append(candidate)
    return normalized


def _build_program_spec_deliverable_bindings(
    meeting: Any,
    *,
    program_spec: Any,
    handoff_in: Optional[Any],
) -> Dict[str, Dict[str, Any]]:
    coverage_snapshot = getattr(program_spec, "coverage_snapshot", None) or {}
    coverage_entries = (
        coverage_snapshot.get("entries")
        if isinstance(coverage_snapshot, dict)
        else None
    )
    if not isinstance(coverage_entries, list):
        coverage_entries = []

    request_contract = (
        (getattr(getattr(meeting, "session", None), "metadata", None) or {}).get(
            "request_contract"
        )
        or {}
    )
    contract_deliverables = (
        request_contract.get("deliverables")
        if isinstance(request_contract, dict)
        else None
    )
    if not isinstance(contract_deliverables, list):
        contract_deliverables = []

    handoff_deliverables = _normalize_deliverable_specs(
        getattr(handoff_in, "deliverables", None)
    )
    if not handoff_deliverables and contract_deliverables:
        handoff_deliverables = _normalize_deliverable_specs(contract_deliverables)

    bindings: Dict[str, Dict[str, Any]] = {}
    for entry in coverage_entries:
        if not isinstance(entry, dict):
            continue
        deliverable_id = str(entry.get("deliverable_id") or "").strip()
        if not deliverable_id:
            continue
        bindings.setdefault(
            deliverable_id,
            {
                "deliverable_id": deliverable_id,
                "deliverable_name": str(entry.get("deliverable_name") or "").strip()
                or None,
            },
        )

    for index, contract_entry in enumerate(contract_deliverables):
        if not isinstance(contract_entry, dict):
            continue
        deliverable_id = str(contract_entry.get("id") or "").strip()
        if not deliverable_id:
            continue
        binding = bindings.setdefault(
            deliverable_id,
            {"deliverable_id": deliverable_id},
        )
        contract_name = str(contract_entry.get("name") or "").strip()
        if contract_name and not binding.get("deliverable_name"):
            binding["deliverable_name"] = contract_name
        if index < len(handoff_deliverables):
            handoff_deliverable = handoff_deliverables[index]
            deliverable_path = str(handoff_deliverable.get("name") or "").strip()
            if deliverable_path:
                binding["deliverable_path"] = deliverable_path

    for index, entry in enumerate(coverage_entries):
        if not isinstance(entry, dict):
            continue
        deliverable_id = str(entry.get("deliverable_id") or "").strip()
        if not deliverable_id:
            continue
        if index >= len(handoff_deliverables):
            continue
        binding = bindings.setdefault(
            deliverable_id,
            {"deliverable_id": deliverable_id},
        )
        deliverable_path = str(handoff_deliverables[index].get("name") or "").strip()
        if deliverable_path and not binding.get("deliverable_path"):
            binding["deliverable_path"] = deliverable_path

    return bindings


def _reconcile_compile_job_terminal_state(
    meeting: Any,
    *,
    decision: str,
    action_items: List[Dict[str, Any]],
    dispatch_result: Optional[Dict[str, Any]],
) -> None:
    session = getattr(meeting, "session", None)
    if session is None or not getattr(session, "id", None):
        return

    try:
        from backend.app.models.meeting_session import MeetingStatus

        compile_job_store = getattr(meeting, "compile_job_store", None) or getattr(
            meeting, "_compile_job_store", None
        )
        if compile_job_store is None:
            from backend.app.services.stores.compile_job_store import CompileJobStore

            compile_job_store = CompileJobStore()
        compile_job = compile_job_store.get_latest_for_session(session.id)
        if compile_job is None or compile_job.status in {"succeeded", "failed"}:
            return

        dispatch_phase_results = (
            dispatch_result.get("phase_results")
            if isinstance(dispatch_result, dict)
            else None
        )
        terminal_metadata = {
            "session_terminal_reconciled_at": getattr(session, "ended_at", None)
            and session.ended_at.isoformat()
            or None,
            "session_terminal_status": getattr(session.status, "value", session.status),
            "dispatch_status": (
                dispatch_result.get("status")
                if isinstance(dispatch_result, dict)
                else None
            ),
        }
        program_run_id = (getattr(session, "metadata", None) or {}).get("program_run_id")
        if program_run_id:
            terminal_metadata["program_run_id"] = program_run_id
        task_summary = summarize_meeting_session_tasks(getattr(session, "id", None))
        terminal_metadata["session_task_total"] = task_summary["total"]
        terminal_metadata["session_incomplete_tasks"] = task_summary["incomplete"]
        terminal_metadata["session_task_statuses"] = task_summary["statuses"]

        if session.status == MeetingStatus.CLOSED and not task_summary["terminal"]:
            logger.info(
                "CompileJob terminal reconcile deferred for session %s: %d/%d tasks still incomplete",
                getattr(session, "id", None),
                task_summary["incomplete"],
                task_summary["total"],
            )
            return

        if session.status == MeetingStatus.CLOSED:
            if closed_session_compile_failed(
                task_summary,
                dispatch_status=terminal_metadata.get("dispatch_status"),
            ):
                compile_job_store.mark_failed(
                    compile_job.id,
                    "meeting_session_closed_with_all_failed_tasks",
                    session_id=session.id,
                    metadata=terminal_metadata,
                )
            else:
                compile_job_store.mark_succeeded(
                    compile_job.id,
                    session_id=session.id,
                    result={
                        "session_id": session.id,
                        "meeting_status": "closed",
                        "decision": decision,
                        "action_items_count": len(action_items or []),
                        "dispatch_status": terminal_metadata.get("dispatch_status"),
                        "phase_results": dispatch_phase_results or [],
                        "program_run_id": program_run_id,
                        "session_task_total": task_summary["total"],
                        "session_task_statuses": task_summary["statuses"],
                    },
                    metadata=terminal_metadata,
                )
        elif session.status == MeetingStatus.FAILED:
            compile_job_store.mark_failed(
                compile_job.id,
                "meeting_session_failed",
                session_id=session.id,
                metadata=terminal_metadata,
            )
    except Exception as exc:
        logger.warning(
            "CompileJob terminal reconciliation failed for session %s: %s",
            getattr(session, "id", None),
            exc,
        )


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

    decomposer = None
    decomposed_phases = None
    structured_program_spec = _load_executor_structured_program_spec(meeting)
    if structured_program_spec is not None:
        try:
            from backend.app.services.orchestration.meeting.program_spec_bridge import (
                phases_from_program_spec,
            )
            deliverable_bindings = _build_program_spec_deliverable_bindings(
                meeting,
                program_spec=structured_program_spec,
                handoff_in=handoff_in,
            )

            decomposed_phases = phases_from_program_spec(
                structured_program_spec,
                default_workspace_id=meeting.session.workspace_id,
                deliverable_bindings=deliverable_bindings,
            )
            logger.info(
                "ProgramSpec bridge produced %d phases from %d workstreams",
                len(decomposed_phases),
                len(structured_program_spec.workstreams),
            )
        except Exception as exc:
            logger.warning("ProgramSpec bridge dispatch fallback to decomposer: %s", exc)
            structured_program_spec = None

    if structured_program_spec is None:
        from backend.app.services.orchestration.task_decomposer import TaskDecomposer

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
    _reconcile_compile_job_terminal_state(
        meeting,
        decision=decision,
        action_items=action_items,
        dispatch_result=dispatch_result,
    )
    try:
        from backend.app.services.orchestration.meeting.program_runtime_adapter import (
            record_session_program_run,
        )

        record_session_program_run(
            meeting,
            dispatch_result=dispatch_result,
        )
    except Exception as exc:
        logger.warning(
            "ProgramRun persistence failed for session %s: %s",
            meeting.session.id,
            exc,
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
