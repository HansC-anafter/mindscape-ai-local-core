"""Compile HandoffIn payloads through the existing MeetingEngine path."""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from backend.app.models.handoff import HandoffIn
from backend.app.services.handoff_bundle_recovery import (
    build_compile_job_recovery_request,
    looks_like_orphan_compile_session,
    reuse_terminal_compile_result,
    should_supersede_active_session,
)

logger = logging.getLogger(__name__)


async def compile_handoff_in(
    *,
    handoff_in: HandoffIn,
    workspace: Any,
    runtime_profile: Any,
    profile_id: str,
    thread_id: str,
    project_id: str,
    model_name: Optional[str] = None,
    source_device_id: Optional[str] = None,
    route_decision: Any = None,
) -> Dict[str, Any]:
    """Compile a HandoffIn via MeetingEngine using the existing runtime path."""
    from backend.app.models.meeting_execution_context import (
        MeetingExecutionContext,
    )
    from backend.app.services.orchestration.meeting import MeetingEngine
    from backend.app.services.stores.meeting_session_store import (
        MeetingSessionStore,
        is_active_session_fresh,
    )

    session_store = MeetingSessionStore()
    workspace_id = getattr(workspace, "id", handoff_in.workspace_id)
    executor_runtime = getattr(workspace, "resolved_executor_runtime", None)
    compile_job_id = str(uuid4())
    compile_job_store = None
    compile_job_created = False
    cleanup_compile_job_session_ids = []
    stale_compile_job_cleaned_session_ids = set()
    superseded_active_sessions: List[Any] = []
    superseded_active_session_ids = set()
    try:
        from backend.app.models.compile_job import CompileJob, CompileJobStatus
        from backend.app.services.stores.compile_job_store import CompileJobStore

        compile_job_store = CompileJobStore()
    except Exception as exc:
        logger.warning("[HandoffBundle] Compile job store unavailable: %s", exc)
    try:
        listed_sessions = session_store.list_by_workspace(
            workspace_id,
            project_id=project_id,
            limit=100,
            offset=0,
        )
        if not isinstance(listed_sessions, list):
            listed_sessions = list(listed_sessions or [])
        for candidate in listed_sessions:
            if project_id and getattr(candidate, "project_id", None) != project_id:
                continue
            if thread_id and getattr(candidate, "thread_id", None) != thread_id:
                continue
            if getattr(candidate, "is_active", False):
                if is_active_session_fresh(candidate):
                    existing_candidate_compile_job = None
                    if compile_job_store is not None:
                        try:
                            existing_candidate_compile_job = (
                                compile_job_store.get_latest_for_session(candidate.id)
                            )
                        except Exception as exc:
                            logger.warning(
                                "[HandoffBundle] Failed to inspect candidate session %s for supersede check: %s",
                                candidate.id,
                                exc,
                            )
                    if should_supersede_active_session(
                        candidate,
                        existing_candidate_compile_job,
                        incoming_handoff_id=getattr(handoff_in, "handoff_id", None),
                    ):
                        superseded_active_sessions.append(candidate)
                        superseded_active_session_ids.add(candidate.id)
                    continue
                cleanup_compile_job_session_ids.append(candidate.id)
                continue
            cleanup_compile_job_session_ids.append(candidate.id)
    except Exception as exc:
        logger.warning(
            "[HandoffBundle] Failed to enumerate stale active sessions for workspace=%s project=%s thread=%s: %s",
            workspace_id,
            project_id,
            thread_id,
            exc,
        )

    try:
        session_store.close_stale_active_sessions(
            workspace_id,
            project_id=project_id,
            thread_id=thread_id,
            reason="stale_replaced_by_compile",
        )
    except Exception as exc:
        logger.warning(
            "[HandoffBundle] Failed to close stale active sessions for workspace=%s project=%s thread=%s: %s",
            workspace_id,
            project_id,
            thread_id,
            exc,
        )
    if cleanup_compile_job_session_ids and compile_job_store is not None:
        for stale_session_id in cleanup_compile_job_session_ids:
            try:
                compile_job_store.mark_incomplete_for_session(
                    stale_session_id,
                    error="compile_session_replaced_by_new_intake",
                    metadata={"abort_reason": "stale_replaced_by_compile"},
                )
            except Exception as exc:
                logger.warning(
                    "[HandoffBundle] Failed to fail stale compile jobs for session=%s: %s",
                    stale_session_id,
                    exc,
                )
            else:
                stale_compile_job_cleaned_session_ids.add(stale_session_id)
    if superseded_active_sessions:
        for superseded_session in superseded_active_sessions:
            metadata = {
                "abort_reason": "superseded_by_new_handoff",
                "superseded_by_handoff_id": getattr(handoff_in, "handoff_id", None),
            }
            if compile_job_store is not None:
                try:
                    compile_job_store.mark_incomplete_for_session(
                        superseded_session.id,
                        error="compile_session_superseded_by_new_handoff",
                        metadata=metadata,
                    )
                except Exception as exc:
                    logger.warning(
                        "[HandoffBundle] Failed to fail superseded compile jobs for session=%s: %s",
                        superseded_session.id,
                        exc,
                    )
                else:
                    stale_compile_job_cleaned_session_ids.add(superseded_session.id)
            try:
                superseded_session.abort(reason="superseded_by_new_handoff")
                superseded_session.metadata["superseded_by_handoff_id"] = getattr(
                    handoff_in, "handoff_id", None
                )
                session_store.update(superseded_session)
            except Exception as exc:
                logger.warning(
                    "[HandoffBundle] Failed to abort superseded session %s: %s",
                    superseded_session.id,
                    exc,
                )
    session = session_store.get_active_session(
        workspace_id,
        project_id,
        thread_id,
    )

    orphan_compile_session = False
    existing_compile_job = None
    if session and compile_job_store is not None:
        try:
            existing_compile_job = compile_job_store.get_latest_for_session(session.id)
            orphan_compile_session = looks_like_orphan_compile_session(
                session,
                existing_compile_job,
            )
        except Exception as exc:
            logger.warning(
                "[HandoffBundle] Failed to inspect existing compile session %s: %s",
                session.id,
                exc,
            )
            existing_compile_job = None

    if session and (orphan_compile_session or not is_active_session_fresh(session)):
        logger.info(
            "[HandoffBundle] Ignoring stale/orphan active session %s for workspace=%s project=%s",
            session.id,
            workspace_id,
            project_id,
        )
        if (
            compile_job_store is not None
            and session.id not in stale_compile_job_cleaned_session_ids
        ):
            try:
                compile_job_store.mark_incomplete_for_session(
                    session.id,
                    error="compile_session_replaced_by_new_intake",
                    metadata={"abort_reason": "stale_replaced_by_compile"},
                )
            except Exception as exc:
                logger.warning(
                    "[HandoffBundle] Failed to fail stale compile jobs for session=%s: %s",
                    session.id,
                    exc,
                )
        try:
            session_store.end_session(
                session.id,
                state_after={"abort_reason": "stale_replaced_by_compile"},
            )
        except Exception as exc:
            logger.warning(
                "[HandoffBundle] Failed to close stale session %s: %s",
                session.id,
                exc,
            )
        session = None
        existing_compile_job = None
    elif session and session.id in superseded_active_session_ids:
        logger.info(
            "[HandoffBundle] Ignoring superseded active session %s for workspace=%s project=%s thread=%s",
            session.id,
            workspace_id,
            project_id,
            thread_id,
        )
        session = None
        existing_compile_job = None

    reused_compile_result = reuse_terminal_compile_result(
        session,
        existing_compile_job,
        incoming_handoff_id=getattr(handoff_in, "handoff_id", None),
    )
    if reused_compile_result is not None:
        logger.info(
            "[HandoffBundle] Reusing terminal compile job %s for active session %s handoff=%s",
            getattr(existing_compile_job, "id", None),
            getattr(session, "id", None),
            getattr(handoff_in, "handoff_id", None),
        )
        return reused_compile_result

    if not session:
        from backend.app.models.meeting_session import MeetingSession

        lens_id = None
        try:
            from backend.app.services.lens.effective_lens_resolver import (
                EffectiveLensResolver,
            )
            from backend.app.services.lens.session_override_store import (
                InMemorySessionStore,
            )
            from backend.app.services.stores.graph_store import GraphStore

            graph_store = GraphStore()
            session_override_store = InMemorySessionStore()
            resolver = EffectiveLensResolver(graph_store, session_override_store)
            effective = resolver.resolve(
                profile_id=profile_id,
                workspace_id=workspace_id,
            )
            lens_id = effective.global_preset_id
        except Exception as exc:
            logger.warning("[HandoffBundle] Failed to resolve lens_id: %s", exc)

        session = MeetingSession.new(
            workspace_id=workspace_id,
            project_id=project_id,
            thread_id=thread_id,
            lens_id=lens_id,
            agenda=(
                [g[:200].strip() for g in (handoff_in.goals or []) if g.strip()][:10]
                or [handoff_in.intent_summary[:200].strip()]
                if hasattr(handoff_in, "intent_summary") and handoff_in.intent_summary
                else None
            ),
        )
        session_store.create(session)

    if compile_job_store is not None:
        try:
            compile_job_store.create(
                CompileJob(
                    id=compile_job_id,
                    workspace_id=workspace_id,
                    project_id=project_id,
                    thread_id=thread_id,
                    profile_id=profile_id,
                    session_id=session.id,
                    handoff_id=handoff_in.handoff_id,
                    source_device_id=source_device_id,
                    status=CompileJobStatus.RUNNING,
                    metadata={
                        "workspace_id": workspace_id,
                        "executor_runtime": executor_runtime,
                        "route_kind": getattr(route_decision, "route_kind", None),
                        "recovery_request": build_compile_job_recovery_request(
                            handoff_in=handoff_in,
                            workspace_id=workspace_id,
                            project_id=project_id,
                            thread_id=thread_id,
                            profile_id=profile_id,
                            model_name=model_name,
                            source_device_id=source_device_id,
                        ),
                    },
                    started_at=datetime.now(timezone.utc),
                )
            )
            compile_job_created = True
        except Exception as exc:
            logger.warning(
                "[HandoffBundle] Failed to create compile job %s: %s",
                compile_job_id,
                exc,
            )

    from backend.app.services.conversation.pipeline_meeting import (
        build_execution_launcher,
    )
    from backend.app.services.mindscape_store import MindscapeStore

    execution_context = MeetingExecutionContext.assemble(
        workspace=workspace,
        runtime_profile=runtime_profile,
        route_decision=route_decision,
    )
    store = MindscapeStore()
    execution_launcher = build_execution_launcher(store)

    engine = MeetingEngine(
        session=session,
        store=store,
        workspace=workspace,
        runtime_profile=runtime_profile,
        profile_id=profile_id,
        thread_id=thread_id,
        project_id=project_id,
        execution_launcher=execution_launcher,
        model_name=model_name,
        executor_runtime=executor_runtime,
        uploaded_files=None,
        execution_context=execution_context,
    )

    intake_message = (
        f"[Handoff Intake] {handoff_in.intent_summary}\n"
        f"Goals: {', '.join(handoff_in.goals)}\n"
        f"Source: {source_device_id or 'unknown'}"
    )

    try:
        meeting_result = await engine.run(intake_message, handoff_in=handoff_in)
    except Exception as exc:
        if compile_job_store is not None and compile_job_created:
            try:
                compile_job_store.mark_failed(
                    compile_job_id,
                    str(exc),
                    session_id=session.id,
                    metadata={
                        "workspace_id": workspace_id,
                        "executor_runtime": executor_runtime,
                    },
                )
            except Exception as mark_exc:
                logger.warning(
                    "[HandoffBundle] Failed to mark compile job %s failed: %s",
                    compile_job_id,
                    mark_exc,
                )
        raise

    result = {
        "status": "compiled",
        "compile_job_id": compile_job_id,
        "job_id": compile_job_id,
        "session_id": meeting_result.session_id,
        "decision": meeting_result.decision,
        "action_items_count": len(meeting_result.action_items),
        "task_ir_id": None,
        "persisted": False,
    }

    if meeting_result.task_ir:
        result["task_ir_id"] = meeting_result.task_ir.task_id
        try:
            from backend.app.services.stores.postgres.task_ir_store import (
                PostgresTaskIRStore,
            )

            ir_store = PostgresTaskIRStore()
            ir_store.replace_task_ir(meeting_result.task_ir)
            result["persisted"] = True
            logger.info(
                "Persisted TaskIR %s from intake",
                meeting_result.task_ir.task_id,
            )
        except Exception as exc:
            logger.warning(
                "Failed to persist TaskIR from intake: %s",
                exc,
                exc_info=True,
            )

    if compile_job_store is not None and compile_job_created:
        try:
            compile_job_store.mark_succeeded(
                compile_job_id,
                session_id=meeting_result.session_id,
                result=result,
                metadata={
                    "workspace_id": workspace_id,
                    "executor_runtime": executor_runtime,
                },
            )
        except Exception as exc:
            logger.warning(
                "[HandoffBundle] Failed to mark compile job %s succeeded: %s",
                compile_job_id,
                exc,
            )

    logger.info(
        "Intake complete: handoff %s -> TaskIR %s (persisted=%s)",
        handoff_in.handoff_id,
        result["task_ir_id"],
        result["persisted"],
    )
    return result
