"""
Pipeline Dispatch -- Agent and LLM dispatch functions.

Handles dispatching chat messages to external agent runtimes
(e.g. Gemini CLI) or to LLM streaming providers.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.app.models.mindscape import MindEvent, EventActor, EventType

logger = logging.getLogger(__name__)


async def dispatch_to_agent(
    workspace_id: str,
    profile_id: str,
    thread_id: str,
    project_id: str,
    message: str,
    user_event_id: str,
    executor_runtime: str,
    context_str: str,
    store: Any,
    workspace: Any,
    result: Any,
    emit_pipeline_stage,
    # Fallback chain params (P0 Fail-Loud)
    execution_mode: str = "qa",
    model_name: Optional[str] = None,
    profile: Any = None,
) -> Any:
    """Dispatch to external agent runtime (e.g. Gemini CLI).

    P0 Fail-Loud: When the agent is unavailable or fails, check
    workspace.fallback_model. If set, delegate to dispatch_to_llm
    with that model. If not set, report error (no silent fallback).

    Args:
        workspace_id: Workspace ID.
        profile_id: Profile ID.
        thread_id: Thread ID.
        project_id: Project ID.
        message: User message text.
        user_event_id: User event ID.
        executor_runtime: Agent runtime name.
        context_str: Conversational context.
        store: MindscapeStore instance.
        workspace: Workspace object.
        result: PipelineResult accumulator.
        emit_pipeline_stage: Callback to emit pipeline stage events.
        execution_mode: qa | execution | hybrid (for fallback dispatch).
        model_name: LLM model name (for fallback dispatch).
        profile: UserProfile object (for fallback dispatch).

    Returns:
        Updated PipelineResult.
    """
    from backend.app.services.workspace_agent_executor import (
        WorkspaceAgentExecutor,
        AgentExecutionResponse,
    )

    executor = WorkspaceAgentExecutor(workspace)
    agent_available = await executor.check_agent_available(executor_runtime)

    if not agent_available:
        # P0 Fail-Loud: check for explicit fallback model
        fallback_model = getattr(workspace, "fallback_model", None)
        if fallback_model:
            await emit_pipeline_stage(
                workspace_id,
                profile_id,
                thread_id,
                project_id,
                "agent_fallback",
                f"Executor {executor_runtime} unavailable, using fallback model {fallback_model}",
                user_event_id,
            )
            return await dispatch_to_llm(
                workspace_id=workspace_id,
                profile_id=profile_id,
                thread_id=thread_id,
                project_id=project_id,
                message=message,
                user_event_id=user_event_id,
                execution_mode=execution_mode,
                model_name=fallback_model,
                context_str=context_str,
                store=store,
                workspace=workspace,
                profile=profile,
                result=result,
                is_fallback=True,
            )
        result.success = False
        result.error = (
            f"Executor {executor_runtime} unavailable: no runtime connected. "
            f"Start the CLI bridge or configure a fallback model."
        )
        return result

    await emit_pipeline_stage(
        workspace_id,
        profile_id,
        thread_id,
        project_id,
        "agent_dispatching",
        f"Dispatching task to agent {executor_runtime}...",
        user_event_id,
    )

    agent_response: AgentExecutionResponse = await executor.execute(
        task=message,
        agent_id=executor_runtime,
        context_overrides={
            "conversation_context": context_str or "",
            "thread_id": thread_id,
            "project_id": project_id,
        },
    )

    exec_time = agent_response.execution_time_seconds

    if agent_response.success:
        await emit_pipeline_stage(
            workspace_id,
            profile_id,
            thread_id,
            project_id,
            "agent_completed",
            f"Agent completed in {exec_time:.0f}s",
            user_event_id,
        )

        # Create assistant event
        payload = {
            "message": agent_response.output,
            "agent_id": executor_runtime,
            "trace_id": agent_response.trace_id,
            "execution_time": exec_time,
        }
        metadata = {
            "external_agent": True,
            "agent_id": executor_runtime,
        }
        if result.meeting_session_id:
            payload["meeting_session_id"] = result.meeting_session_id
            metadata["meeting_session_id"] = result.meeting_session_id

        assistant_event = MindEvent(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc),
            actor=EventActor.ASSISTANT,
            channel="local_workspace",
            profile_id=profile_id,
            project_id=project_id,
            workspace_id=workspace_id,
            thread_id=thread_id,
            event_type=EventType.MESSAGE,
            payload=payload,
            entity_ids=[],
            metadata=metadata,
        )
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            lambda: store.create_event(assistant_event),
        )

        result.response_text = agent_response.output
        result.events.append(
            assistant_event.model_dump()
            if hasattr(assistant_event, "model_dump")
            else {"id": assistant_event.id}
        )
    else:
        # P0 Fail-Loud: agent execution failed, check for fallback
        fallback_model = getattr(workspace, "fallback_model", None)
        if fallback_model:
            await emit_pipeline_stage(
                workspace_id,
                profile_id,
                thread_id,
                project_id,
                "agent_fallback",
                f"Executor {executor_runtime} failed: {agent_response.error}, using fallback model {fallback_model}",
                user_event_id,
            )
            return await dispatch_to_llm(
                workspace_id=workspace_id,
                profile_id=profile_id,
                thread_id=thread_id,
                project_id=project_id,
                message=message,
                user_event_id=user_event_id,
                execution_mode=execution_mode,
                model_name=fallback_model,
                context_str=context_str,
                store=store,
                workspace=workspace,
                profile=profile,
                result=result,
                is_fallback=True,
            )
        result.success = False
        result.error = (
            f"Executor {executor_runtime} execution failed: "
            f"{agent_response.error or 'unknown error'}. "
            f"Configure a fallback model to avoid this."
        )

    return result


async def dispatch_to_llm(
    workspace_id: str,
    profile_id: str,
    thread_id: str,
    project_id: str,
    message: str,
    user_event_id: str,
    execution_mode: str,
    model_name: Optional[str],
    context_str: str,
    store: Any,
    workspace: Any,
    profile: Any,
    result: Any,
    is_fallback: bool = False,
) -> Any:
    """Dispatch to LLM streaming (pure generation, no decisions).

    Args:
        workspace_id: Workspace ID.
        profile_id: Profile ID.
        thread_id: Thread ID.
        project_id: Project ID.
        message: User message text.
        user_event_id: User event ID.
        execution_mode: qa | execution | hybrid.
        model_name: LLM model name.
        context_str: Conversational context.
        store: MindscapeStore instance.
        workspace: Workspace object.
        profile: UserProfile object.
        result: PipelineResult accumulator.

    Returns:
        Updated PipelineResult.
    """
    from backend.features.workspace.chat.streaming.llm_streaming import (
        stream_llm_response,
    )
    from backend.features.workspace.chat.utils.llm_provider import (
        get_llm_provider_manager,
        get_llm_provider,
    )

    # Resolve model
    if not model_name:
        try:
            from backend.app.services.system_settings_store import (
                SystemSettingsStore,
            )

            settings_store = SystemSettingsStore()
            chat_setting = settings_store.get_setting("chat_model")
            if chat_setting and chat_setting.value:
                model_name = str(chat_setting.value)
        except Exception as e:
            logger.warning(f"Failed to fetch default chat model: {e}")

    if not model_name or str(model_name).strip() == "":
        result.success = False
        result.error = (
            "No chat model configured. "
            "Set chat_model in system settings or configure a fallback model."
        )
        return result

    provider_manager = get_llm_provider_manager()
    provider, provider_type = get_llm_provider(
        model_name=model_name,
        llm_provider_manager=provider_manager,
        profile_id=profile_id,
        db_path=store.db_path,
    )

    # Build messages
    messages = []
    if context_str:
        messages.append({"role": "system", "content": context_str})
    messages.append({"role": "user", "content": message})

    # SGR prompt injection
    sgr_enabled = False
    try:
        ws_metadata = workspace.metadata or {}
        sgr_enabled = ws_metadata.get("sgr_enabled", False)
    except Exception:
        pass

    if sgr_enabled:
        from backend.app.services.sgr_reasoning_service import (
            SGRReasoningService,
        )

        sgr_service = SGRReasoningService()
        messages = sgr_service.inject_sgr_prompt(messages)
        logger.info("[PipelineCore] SGR prompt injected")

    context_token_count = len(context_str) // 4 if context_str else 0

    # Collect full text from stream
    full_text = ""
    async for chunk in stream_llm_response(
        provider=provider,
        provider_type=provider_type,
        messages=messages,
        model_name=model_name,
        execution_mode=execution_mode,
        user_event_id=user_event_id,
        profile_id=profile_id,
        project_id=project_id,
        workspace_id=workspace_id,
        thread_id=thread_id,
        workspace=workspace,
        message=message,
        profile=profile,
        store=store,
        context_token_count=context_token_count,
        execution_playbook_result=None,
        openai_key=None,
        meeting_session_id=result.meeting_session_id,
        is_fallback=is_fallback,
    ):
        # Accumulate full text from chunks
        if chunk.startswith("data: "):
            try:
                data = json.loads(chunk[6:].strip())
                if data.get("type") == "chunk":
                    full_text += data.get("content", "")
            except Exception:
                pass

    result.response_text = full_text
    return result
