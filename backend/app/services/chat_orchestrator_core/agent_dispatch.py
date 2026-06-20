"""Retained agent dispatch helper for ChatOrchestratorService."""

import json
import logging
import os
import uuid
from pathlib import Path

from backend.app.models.mindscape import EventActor, EventType, MindEvent
from backend.app.services.chat_orchestrator_core.events import persist_event, utc_now

logger = logging.getLogger(__name__)


async def handle_agent_dispatch(
    *,
    request,
    workspace,
    workspace_id,
    profile_id,
    session,
    executor_runtime,
    store,
    create_pipeline_event,
    create_error_event,
):
    """Route to WorkspaceAgentExecutor when agent runtime is configured."""
    logger.info("Workspace has executor_runtime=%s, routing to agent", executor_runtime)

    from backend.app.services.workspace_agent_executor import (
        AgentExecutionResponse,
        WorkspaceAgentExecutor,
    )

    executor = WorkspaceAgentExecutor(workspace)
    agent_available = await executor.check_agent_available(executor_runtime)

    if not agent_available:
        await create_error_event(
            workspace_id,
            profile_id,
            session.thread_id,
            f"Executor {executor_runtime} unavailable: no runtime connected. "
            f"Start the CLI bridge. Runtime substitution is disabled.",
        )
        logger.warning("Agent %s unavailable, no runtime connected", executor_runtime)
        return

    await create_pipeline_event(
        workspace_id,
        profile_id,
        session.thread_id,
        session.project_id,
        "agent_dispatching",
        f"Dispatching task to agent {executor_runtime}...",
        session.user_event.id,
    )

    from backend.app.services.stores.postgres.timeline_items_store import (
        PostgresTimelineItemsStore,
    )
    from backend.features.workspace.chat.streaming.context_builder import (
        build_streaming_context,
    )

    timeline_items_store = PostgresTimelineItemsStore()
    conversation_context = await build_streaming_context(
        workspace_id=workspace_id,
        message=request.message,
        profile_id=profile_id,
        workspace=workspace,
        store=store,
        timeline_items_store=timeline_items_store,
        model_name=None,
        thread_id=session.thread_id,
    )

    raw_files = getattr(request, "files", None) or []
    enriched_files = []
    if raw_files:
        uploads_dir = Path(os.getenv("UPLOADS_DIR", "data/uploads")) / workspace_id
        for file_id in raw_files:
            if not isinstance(file_id, str):
                enriched_files.append(file_id)
                continue

            meta_path = uploads_dir / f"{file_id}.meta.json"
            original_name = None
            if meta_path.exists():
                try:
                    with open(meta_path, encoding="utf-8") as meta_file:
                        original_name = json.load(meta_file).get("original_name")
                except Exception:
                    pass

            matched = (
                list(uploads_dir.glob(f"{file_id}.*")) if uploads_dir.exists() else []
            )
            matched = [
                match
                for match in matched
                if not match.name.endswith(".meta.json")
                and not match.name.endswith(".analysis.json")
            ]
            if matched:
                file_path = matched[0]
                enriched_files.append(
                    {
                        "file_id": file_id,
                        "file_name": original_name or file_path.name,
                        "file_path": str(file_path),
                        "file_type": file_path.suffix.lstrip("."),
                    }
                )
                logger.info(
                    "Enriched file %s -> %s (%s)",
                    file_id,
                    file_path.name,
                    file_path.suffix,
                )
            else:
                logger.warning("File ID %s not found in %s", file_id, uploads_dir)

    agent_response: AgentExecutionResponse = await executor.execute(
        task=request.message,
        agent_id=executor_runtime,
        context_overrides={
            "conversation_context": conversation_context or "",
            "thread_id": session.thread_id,
            "project_id": session.project_id,
            "uploaded_files": enriched_files,
        },
    )

    exec_time = agent_response.execution_time_seconds
    if agent_response.success:
        await create_pipeline_event(
            workspace_id,
            profile_id,
            session.thread_id,
            session.project_id,
            "agent_completed",
            f"Agent completed in {exec_time:.0f}s",
            session.user_event.id,
        )

        assistant_event = MindEvent(
            id=str(uuid.uuid4()),
            timestamp=utc_now(),
            actor=EventActor.ASSISTANT,
            channel="local_workspace",
            profile_id=profile_id,
            project_id=session.project_id,
            workspace_id=workspace_id,
            thread_id=session.thread_id,
            event_type=EventType.MESSAGE,
            payload={
                "message": agent_response.output,
                "agent_id": executor_runtime,
                "trace_id": agent_response.trace_id,
                "execution_time": agent_response.execution_time_seconds,
            },
            entity_ids=[],
            metadata={
                "external_agent": True,
                "agent_id": executor_runtime,
            },
        )
        await persist_event(store, assistant_event)
        logger.info(
            "External agent %s completed, trace_id=%s",
            executor_runtime,
            agent_response.trace_id,
        )
        return

    error_msg = agent_response.error or "External agent execution failed"
    await create_error_event(
        workspace_id,
        profile_id,
        session.thread_id,
        f"Executor {executor_runtime} execution failed: {error_msg}. "
        f"Runtime substitution is disabled.",
        retry_data={
            "message": request.message,
            "agent_id": executor_runtime,
        },
    )
    logger.error("External agent %s failed: %s", executor_runtime, error_msg)
