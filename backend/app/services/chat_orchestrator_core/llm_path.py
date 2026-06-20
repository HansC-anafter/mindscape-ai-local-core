"""Retained LLM streaming helper for ChatOrchestratorService."""

import logging

from backend.features.workspace.chat.streaming.llm_streaming import stream_llm_response

logger = logging.getLogger(__name__)


async def handle_llm_path(
    *,
    request,
    workspace,
    workspace_id,
    profile_id,
    session,
    orchestrator_store,
    create_error_event,
    model_name_override: str = None,
):
    """Generate response via default LLM streaming path."""
    from backend.features.workspace.chat.utils.llm_provider import (
        get_llm_provider,
        get_llm_provider_manager,
    )

    model_name = model_name_override or request.model_name
    if not model_name:
        try:
            from backend.app.shared.llm_provider_helper import (
                get_model_name_from_chat_model,
            )

            model_name = get_model_name_from_chat_model()
        except Exception as exc:
            logger.warning("Failed to fetch registry chat model: %s", exc)

    if not model_name or str(model_name).strip() == "":
        await create_error_event(
            workspace_id,
            profile_id,
            session.thread_id,
            "No chat model configured in model-routing-registry.",
        )
        return

    provider_manager = get_llm_provider_manager()
    provider, provider_type = get_llm_provider(
        model_name=model_name,
        llm_provider_manager=provider_manager,
        profile_id=profile_id,
        db_path=orchestrator_store.db_path,
    )

    from backend.app.services.stores.postgres.timeline_items_store import (
        PostgresTimelineItemsStore,
    )
    from backend.features.workspace.chat.streaming.context_builder import (
        build_streaming_context,
    )

    timeline_items_store = PostgresTimelineItemsStore()
    context_str = await build_streaming_context(
        workspace_id=workspace_id,
        message=request.message,
        profile_id=profile_id,
        workspace=workspace,
        store=orchestrator_store,
        timeline_items_store=timeline_items_store,
        model_name=model_name,
        thread_id=session.thread_id,
    )

    from backend.app.services.workspace_instruction_helper import (
        build_workspace_instruction_block,
    )

    ws_instruction, _src = build_workspace_instruction_block(
        workspace, caller="background"
    )
    if ws_instruction:
        context_str = (
            ws_instruction + "\n\n" + (context_str or "")
            if context_str
            else ws_instruction
        )

    messages = []
    if context_str:
        messages.append({"role": "system", "content": context_str})
    messages.append({"role": "user", "content": request.message})

    sgr_enabled = False
    try:
        ws_metadata = workspace.metadata or {}
        sgr_enabled = ws_metadata.get("sgr_enabled", False)
    except Exception:
        pass

    if sgr_enabled:
        from backend.app.services.sgr_reasoning_service import SGRReasoningService

        sgr_service = SGRReasoningService()
        messages = sgr_service.inject_sgr_prompt(messages)
        logger.info("SGR prompt injected into messages")

    context_token_count = len(context_str) // 4 if context_str else 0

    logger.info("Consuming LLM stream for mode %s", session.execution_mode)

    async for _ in stream_llm_response(
        provider=provider,
        provider_type=provider_type,
        messages=messages,
        model_name=model_name,
        execution_mode=session.execution_mode,
        user_event_id=session.user_event.id,
        profile_id=profile_id,
        project_id=session.project_id,
        workspace_id=workspace_id,
        thread_id=session.thread_id,
        workspace=workspace,
        message=request.message,
        profile=session.profile,
        store=orchestrator_store,
        context_token_count=context_token_count,
        execution_playbook_result=None,
    ):
        pass
