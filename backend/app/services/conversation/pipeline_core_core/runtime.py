"""PipelineCore runtime flow."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Optional

from backend.app.services.conversation.pipeline_core_core.artifacts import (
    append_unique,
    artifact_file_path,
    clean_string,
    task_ir_artifact_payloads,
)

logger = logging.getLogger(__name__)


async def process_pipeline(
    *,
    pipeline: Any,
    result_factory: Callable[[], Any],
    workspace_id: str,
    profile_id: str,
    thread_id: str,
    project_id: str,
    message: str,
    user_event_id: str,
    execution_mode: str = "qa",
    model_name: Optional[str] = None,
    request: Optional[Any] = None,
) -> Any:
    """
    Process a chat message through the unified pipeline.

    This is the single entry point for ALL chat processing,
    replacing the dual paths in chat_orchestrator_service.py.
    """
    from backend.app.models.route_decision import (
        RouteKind,
        TransitionKind,
    )
    from backend.app.services.conversation.ingress_router import IngressRouter
    from backend.app.services.conversation.pipeline_dispatch import (
        dispatch_to_agent,
        dispatch_to_llm,
    )
    from backend.app.services.conversation.pipeline_meeting import (
        build_execution_launcher,
        ensure_meeting_session,
        extract_handoff_in,
        finalize_meeting_session,
        persist_meeting_task_ir,
    )
    from backend.app.services.conversation.pipeline_playbook import (
        handle_post_response_playbook,
    )

    result = result_factory()
    explicit_meeting_session_id = None
    action_params = getattr(request, "action_params", None) if request else None
    if isinstance(action_params, dict):
        explicit_meeting_session_id = (
            action_params.get("meeting_session_id") or action_params.get("meeting_id")
        )
        if explicit_meeting_session_id:
            result.meeting_session_id = str(explicit_meeting_session_id)

    try:
        from backend.app.services.executor_routing_policy_service import (
            ExecutorRoutingPolicyService,
        )

        executor_runtime = (
            ExecutorRoutingPolicyService.extract_workspace_policy_snapshot(
                pipeline.workspace
            ).get("primary_executor_runtime")
        )

        router = IngressRouter()
        route_decision = await router.decide(
            execution_mode=execution_mode,
            meeting_enabled=getattr(pipeline.workspace, "meeting_enabled", False),
            executor_runtime=executor_runtime,
            entry_point="chat",
            store=pipeline.store,
            project_id=project_id,
        )

        meeting_enabled = route_decision.route_kind == RouteKind.MEETING

        session = None
        if meeting_enabled:
            session = await ensure_meeting_session(
                workspace_id,
                thread_id,
                pipeline.session_store,
                project_id,
                user_message=message,
                model_name=model_name,
                executor_runtime=executor_runtime,
                explicit_session_id=explicit_meeting_session_id,
            )
            if session:
                result.meeting_session_id = session.id

        if meeting_enabled:
            if not session:
                raise RuntimeError("Failed to initialize meeting session")

            from backend.app.services.orchestration.meeting import MeetingEngine

            execution_launcher = build_execution_launcher(pipeline.store)
            executor_runtime = (
                ExecutorRoutingPolicyService.extract_workspace_policy_snapshot(
                    pipeline.workspace
                ).get("primary_executor_runtime")
            )

            raw_files = getattr(request, "files", None) or []
            uploaded_files = []
            if raw_files:
                import json as _json
                import os
                from pathlib import Path

                workspace_id_str = getattr(pipeline.workspace, "id", None) or ""
                uploads_dir = (
                    Path(os.getenv("UPLOADS_DIR", "data/uploads")) / workspace_id_str
                )
                for file_ref in raw_files:
                    if isinstance(file_ref, dict):
                        uploaded_files.append(file_ref)
                    elif isinstance(file_ref, str):
                        file_id = file_ref
                        original_name = None
                        meta_path = uploads_dir / f"{file_id}.meta.json"
                        if meta_path.exists():
                            try:
                                with open(meta_path) as meta_file:
                                    meta = _json.load(meta_file)
                                original_name = meta.get("original_name")
                            except Exception:
                                pass

                        matched = (
                            list(uploads_dir.glob(f"{file_id}.*"))
                            if uploads_dir.exists()
                            else []
                        )
                        matched = [
                            path
                            for path in matched
                            if not path.name.endswith(".meta.json")
                            and not path.name.endswith(".analysis.json")
                        ]
                        if matched:
                            file_path = matched[0]
                            display_name = original_name or file_path.name
                            file_info = {
                                "file_id": file_id,
                                "file_name": display_name,
                                "file_path": str(file_path),
                                "file_type": file_path.suffix.lstrip("."),
                            }
                        else:
                            file_info = {"file_id": file_id}
                        uploaded_files.append(file_info)

                if uploaded_files:
                    try:
                        from backend.app.services.conversation.file_dispatch_enricher import (
                            FileDispatchEnricher,
                        )

                        enricher = FileDispatchEnricher()
                        workspace_id_for_enrich = getattr(
                            pipeline.workspace, "id", None
                        )
                        if workspace_id_for_enrich:
                            file_ctx = await enricher.enrich(
                                workspace_id_for_enrich, uploaded_files
                            )
                            uploaded_files = file_ctx.files
                    except Exception as exc:
                        logger.warning(
                            "FileDispatchEnricher failed in meeting branch: %s", exc
                        )

            from backend.app.models.meeting_execution_context import (
                MeetingExecutionContext,
            )

            runtime_snapshot = None
            try:
                from backend.app.database.engine import SessionLocalCore
                from backend.app.models.runtime_environment import RuntimeEnvironment
                from backend.app.models.runtime_observability_snapshot import (
                    RuntimeObservabilitySnapshot,
                )

                if executor_runtime:
                    db = SessionLocalCore()
                    try:
                        runtime_env = (
                            db.query(RuntimeEnvironment)
                            .filter(RuntimeEnvironment.id == executor_runtime)
                            .first()
                        )
                        if runtime_env:
                            runtime_snapshot = (
                                RuntimeObservabilitySnapshot.from_runtime_environment(
                                    runtime_env, selection_reason="primary"
                                )
                            )
                    finally:
                        db.close()
            except Exception as rt_exc:
                logger.warning("Q0 runtime snapshot failed (non-fatal): %s", rt_exc)

            execution_context = MeetingExecutionContext.assemble(
                workspace=pipeline.workspace,
                runtime_profile=pipeline.runtime_profile,
                route_decision=route_decision,
                runtime_snapshot=runtime_snapshot,
            )

            meeting_engine = MeetingEngine(
                session=session,
                store=pipeline.store,
                workspace=pipeline.workspace,
                runtime_profile=pipeline.runtime_profile,
                profile_id=profile_id,
                thread_id=thread_id,
                project_id=project_id,
                execution_launcher=execution_launcher,
                model_name=model_name,
                executor_runtime=executor_runtime,
                uploaded_files=uploaded_files,
                execution_context=execution_context,
            )

            handoff_in = extract_handoff_in(request)

            meeting_result = await meeting_engine.run(message, handoff_in=handoff_in)
            result.response_text = meeting_result.minutes_md
            result.events = [{"id": event_id} for event_id in meeting_result.event_ids]
            result.meeting_session_id = meeting_result.session_id
            result.completion_status = meeting_result.completion_status

            if meeting_result.task_ir:
                await persist_meeting_task_ir(meeting_result.task_ir)
                result.task_ir_id = meeting_result.task_ir.task_id
                result.task_ir_artifacts = task_ir_artifact_payloads(
                    meeting_result.task_ir
                )
                for artifact_payload in result.task_ir_artifacts:
                    append_unique(
                        result.artifact_ids,
                        clean_string(artifact_payload.get("id")),
                    )
                    append_unique(
                        result.artifact_file_paths,
                        artifact_file_path(artifact_payload),
                    )
                if meeting_result.dispatch_result:
                    result.dispatch_result = meeting_result.dispatch_result

            await finalize_meeting_session(result, pipeline.session_store)
            return result

        if execution_mode in ("execution", "hybrid"):
            await pipeline._emit_pipeline_stage(
                workspace_id,
                profile_id,
                thread_id,
                project_id,
                "intent_extraction",
                "Analyzing request to find suitable approach.",
                user_event_id,
            )

        await pipeline._emit_pipeline_stage(
            workspace_id,
            profile_id,
            thread_id,
            project_id,
            "context_building",
            "Preparing context: gathering relevant documents and project context.",
            user_event_id,
        )

        from backend.app.services.stores.postgres.timeline_items_store import (
            PostgresTimelineItemsStore,
        )
        from backend.features.workspace.chat.streaming.context_builder import (
            build_streaming_context,
        )

        use_agent = route_decision.route_kind == RouteKind.GOVERNED
        timeline_items_store = PostgresTimelineItemsStore()
        try:
            context_coro = build_streaming_context(
                workspace_id=workspace_id,
                message=message,
                profile_id=profile_id,
                workspace=pipeline.workspace,
                store=pipeline.store,
                timeline_items_store=timeline_items_store,
                model_name=model_name,
                thread_id=thread_id,
                side_chain_mode="off" if use_agent else "auto",
            )
            context_str = (
                await asyncio.wait_for(context_coro, timeout=20)
                if use_agent
                else await context_coro
            )
        except asyncio.TimeoutError:
            context_str = ""
            logger.warning(
                "[PipelineCore] Context build timed out for governed dispatch; "
                "continuing with minimal context (workspace=%s thread=%s)",
                workspace_id,
                thread_id,
            )
            await pipeline._emit_pipeline_stage(
                workspace_id,
                profile_id,
                thread_id,
                project_id,
                "context_building_degraded",
                "Context build timed out; dispatching with bounded workspace metadata.",
                user_event_id,
            )

        from backend.app.services.workspace_instruction_helper import (
            build_workspace_instruction_block,
        )

        ws_instruction, _src = build_workspace_instruction_block(
            pipeline.workspace, caller="pipeline"
        )
        if ws_instruction:
            context_str = (
                ws_instruction + "\n\n" + (context_str or "")
                if context_str
                else ws_instruction
            )

        if use_agent:
            uploaded_files = getattr(request, "files", None) or []

            result = await dispatch_to_agent(
                workspace_id=workspace_id,
                profile_id=profile_id,
                thread_id=thread_id,
                project_id=project_id,
                message=message,
                user_event_id=user_event_id,
                executor_runtime=executor_runtime,
                context_str=context_str,
                store=pipeline.store,
                workspace=pipeline.workspace,
                result=result,
                emit_pipeline_stage=pipeline._emit_pipeline_stage,
                execution_mode=execution_mode,
                model_name=model_name,
                profile=pipeline.profile,
                uploaded_files=uploaded_files,
            )
        else:
            result = await dispatch_to_llm(
                workspace_id=workspace_id,
                profile_id=profile_id,
                thread_id=thread_id,
                project_id=project_id,
                message=message,
                user_event_id=user_event_id,
                execution_mode=execution_mode,
                model_name=model_name,
                context_str=context_str,
                store=pipeline.store,
                workspace=pipeline.workspace,
                profile=pipeline.profile,
                result=result,
            )

        if result.success and execution_mode in ("execution", "hybrid"):
            router.record_transition(
                route_decision,
                TransitionKind.POST_RESPONSE_PLAYBOOK,
                reason=f"post_response: execution_mode={execution_mode}",
            )
            result = await handle_post_response_playbook(
                execution_mode=execution_mode,
                message=message,
                workspace=pipeline.workspace,
                workspace_id=workspace_id,
                profile_id=profile_id,
                profile=pipeline.profile,
                store=pipeline.store,
                result=result,
            )

    except Exception as exc:
        logger.error("[PipelineCore] Error: %s", exc, exc_info=True)
        result.success = False
        result.error = str(exc)

    await finalize_meeting_session(result, pipeline.session_store)

    return result
