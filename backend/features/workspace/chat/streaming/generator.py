"""
Main streaming response generator that coordinates all streaming modules.

This module serves as a thin coordinator. Implementation logic is delegated to:
- chat_session_setup: Unified session initialization
- quick_qa_handler: Quick QA streaming for execution/hybrid mode
- execution_plan_handler: Execution plan generation and SSE events
- llm_streaming: LLM response streaming
- context_builder: Context building for LLM prompts
- prompt_builder: Enhanced prompt construction
"""

import json
import logging
from typing import AsyncGenerator, Any, Optional

from backend.app.models.workspace import Workspace, WorkspaceChatRequest
from backend.app.services.conversation_orchestrator import ConversationOrchestrator
from backend.app.services.stores.timeline_items_store import TimelineItemsStore
from backend.app.services.conversation.context_builder import ContextBuilder
from backend.app.services.system_settings_store import SystemSettingsStore
from backend.app.shared.i18n_loader import get_locale_from_context, load_i18n_string
from backend.app.shared.llm_utils import build_prompt

from .chat_session_setup import (
    setup_chat_session,
    get_or_create_default_thread,
    smart_truncate_message,
)
from .context_builder import build_streaming_context, load_available_playbooks
from .prompt_builder import (
    build_enhanced_prompt,
    inject_execution_mode_prompt,
    parse_prompt_parts,
)
from .execution_plan_handler import handle_execution_plan
from .quick_qa_handler import stream_quick_qa_response
from .llm_streaming import stream_llm_response
from ..playbook.executor import execute_playbook_for_execution_mode
from ..utils.llm_provider import (
    get_llm_provider_manager,
    get_llm_provider,
    get_provider_name_from_model_config,
)
from ..utils.token_management import truncate_context_if_needed, estimate_token_count

logger = logging.getLogger(__name__)

# Backward compatibility re-exports (used by 5 external importers)
_get_or_create_default_thread = get_or_create_default_thread
_smart_truncate_message = smart_truncate_message


async def generate_streaming_response(
    request: WorkspaceChatRequest,
    workspace: Workspace,
    workspace_id: str,
    profile_id: str,
    orchestrator: ConversationOrchestrator,
) -> AsyncGenerator[str, None]:
    """
    Generate streaming response for workspace chat.

    Coordinates session setup, pipeline stages, execution plan,
    and LLM streaming through delegated modules.

    Args:
        request: Chat request.
        workspace: Workspace object.
        workspace_id: Workspace ID.
        profile_id: Profile ID.
        orchestrator: Conversation orchestrator.

    Yields:
        SSE event strings.
    """
    try:
        # 1. Unified session setup
        session = await setup_chat_session(
            request=request,
            workspace=workspace,
            workspace_id=workspace_id,
            profile_id=profile_id,
            store=orchestrator.store,
        )

        # 2. Emit intent extraction stage (execution/hybrid mode)
        if session.execution_mode in ("execution", "hybrid"):
            user_message_preview = smart_truncate_message(
                request.message, max_length=60
            )
            intent_message = load_i18n_string(
                "workspace.pipeline_stage.intent_extraction",
                locale=session.locale,
                default=f"Analyzing: understanding your request '{user_message_preview}', finding a suitable Playbook.",
            ).format(user_message=user_message_preview)
            yield f"data: {json.dumps({'type': 'pipeline_stage', 'run_id': session.user_event.id, 'stage': 'intent_extraction', 'message': intent_message, 'streaming': True})}\n\n"

        # 3. Emit user_message event
        yield f"data: {json.dumps({'type': 'user_message', 'event_id': session.user_event.id})}\n\n"

        # 4. Context building stage
        context_message = load_i18n_string(
            "workspace.pipeline_stage.context_building",
            locale=session.locale,
            default="Preparing context: gathering relevant documents and project context.",
        )
        yield f"data: {json.dumps({'type': 'pipeline_stage', 'run_id': session.user_event.id, 'stage': 'context_building', 'message': context_message, 'streaming': True})}\n\n"

        # 5. Intent extraction
        try:
            from backend.app.core.domain_context import LocalDomainContext

            ctx = LocalDomainContext(workspace_id=workspace_id, actor_id=profile_id)
            await orchestrator.intent_extractor.extract_and_create_timeline_item(
                ctx=ctx,
                message=request.message,
                message_id=session.user_event.id,
                locale=workspace.default_locale or "zh-TW",
                thread_id=session.thread_id,
            )
        except Exception as e:
            logger.warning("Intent extractor failed in streaming path: %s", e)

        # 6. Resolve model name
        model_name = _resolve_model_name(request)

        # 7. Get execution settings
        timeline_items_store = TimelineItemsStore(orchestrator.store.db_path)
        expected_artifacts = getattr(workspace, "expected_artifacts", None)
        execution_priority = getattr(workspace, "execution_priority", None) or "medium"

        # 8. Quick QA response (execution/hybrid mode)
        if session.execution_mode in ("execution", "hybrid") and model_name:
            async for event in stream_quick_qa_response(
                request=request,
                user_event_id=session.user_event.id,
                locale=session.locale,
                model_name=model_name,
                profile_id=profile_id,
                db_path=orchestrator.store.db_path,
            ):
                yield event

        # 9. Build context
        context = await build_streaming_context(
            workspace_id=workspace_id,
            message=request.message,
            profile_id=profile_id,
            workspace=workspace,
            store=orchestrator.store,
            timeline_items_store=timeline_items_store,
            model_name=model_name,
            thread_id=session.thread_id,
            hours=24,
        )

        # 10. Load playbooks and build enhanced prompt
        available_playbooks = await load_available_playbooks(
            workspace_id=workspace_id,
            locale=session.locale,
            store=orchestrator.store,
        )

        context_builder = ContextBuilder(
            store=orchestrator.store,
            timeline_items_store=timeline_items_store,
            model_name=model_name,
        )
        enhanced_prompt = build_enhanced_prompt(
            message=request.message,
            context=context or "",
            context_builder=context_builder,
        )

        # 11. Execution plan (execution/hybrid mode)
        execution_playbook_result = None
        if session.execution_mode in ("execution", "hybrid") and model_name:
            async for event in handle_execution_plan(
                user_event_id=session.user_event.id,
                request=request,
                workspace=workspace,
                workspace_id=workspace_id,
                profile_id=profile_id,
                project_id=session.project_id,
                thread_id=session.thread_id,
                execution_mode=session.execution_mode,
                model_name=model_name,
                available_playbooks=available_playbooks,
                profile=session.profile,
                orchestrator=orchestrator,
                locale=session.locale,
            ):
                yield event

        # 12. Direct playbook execution for execution mode
        if session.execution_mode == "execution":
            execution_playbook_result = await execute_playbook_for_execution_mode(
                message=request.message,
                workspace_id=workspace_id,
                profile_id=profile_id,
                profile=session.profile,
                store=orchestrator.store,
                project_id=session.project_id,
                files=request.files,
                model_name=model_name,
            )
            if execution_playbook_result:
                logger.info("Direct playbook execution succeeded")
                yield f"data: {json.dumps({'type': 'execution_mode_playbook_executed', **execution_playbook_result})}\n\n"
                summary_text = (
                    f"I've started executing the playbook "
                    f"'{execution_playbook_result.get('playbook_code', 'unknown')}'. "
                    f"Check the execution panel for progress."
                )
                yield f"data: {json.dumps({'type': 'chunk', 'content': summary_text})}\n\n"

        # 13. Inject execution mode prompt
        enhanced_prompt = inject_execution_mode_prompt(
            enhanced_prompt=enhanced_prompt,
            execution_mode=session.execution_mode,
            locale=session.locale,
            workspace_id=workspace_id,
            available_playbooks=available_playbooks,
            expected_artifacts=expected_artifacts,
            execution_priority=execution_priority,
            runtime_profile=session.runtime_profile,
        )

        # 14. Prepare messages for LLM
        context_token_count = 0
        try:
            context_token_count = estimate_token_count(enhanced_prompt, model_name) or 0
        except Exception:
            pass

        system_part, user_part = parse_prompt_parts(enhanced_prompt, request.message)
        system_part, _, _ = truncate_context_if_needed(
            system_part=system_part, user_part=user_part, model_name=model_name
        )
        messages = build_prompt(system_prompt=system_part, user_prompt=user_part)

        # 15. Check model availability
        if not model_name:
            yield f"data: {json.dumps({'type': 'error', 'message': 'Cannot generate response: chat_model not configured in system settings'})}\n\n"
            return

        # 16. Stream LLM response
        try:
            llm_provider_manager = get_llm_provider_manager(
                profile_id=profile_id,
                db_path=orchestrator.store.db_path,
                use_default_user=True,
            )
            provider_name, _ = get_provider_name_from_model_config(model_name)
            if not provider_name:
                yield f"data: {json.dumps({'type': 'error', 'message': f'Cannot determine LLM provider for model {model_name}'})}\n\n"
                return

            provider, provider_type = get_llm_provider(
                model_name=model_name,
                llm_provider_manager=llm_provider_manager,
                profile_id=profile_id,
                db_path=orchestrator.store.db_path,
            )

            # SGR prompt injection (feature-gated)
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
                logger.info("SGR prompt injected into messages")

            async for event in stream_llm_response(
                provider=provider,
                provider_type=provider_type,
                messages=messages,
                model_name=model_name,
                execution_mode=session.execution_mode,
                user_event_id=session.user_event.id,
                profile_id=profile_id,
                project_id=workspace.primary_project_id,
                workspace_id=workspace_id,
                thread_id=session.thread_id,
                workspace=workspace,
                message=request.message,
                profile=session.profile,
                store=orchestrator.store,
                context_token_count=context_token_count,
                execution_playbook_result=execution_playbook_result,
                openai_key=None,
            ):
                yield event

        except Exception as e:
            logger.error("LLM streaming error: %s", e, exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

        # 17. Background thread summarization
        _trigger_thread_summarization(
            orchestrator.store, workspace_id, session.thread_id
        )

    except Exception as e:
        logger.error("Streaming error: %s", e, exc_info=True)
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"


def _resolve_model_name(request) -> Optional[str]:
    """Resolve model name from request or system settings."""
    model_name = getattr(request, "model_name", None)
    if not model_name:
        try:
            settings_store = SystemSettingsStore()
            chat_setting = settings_store.get_setting("chat_model")
            if chat_setting and chat_setting.value:
                model_name = str(chat_setting.value)
        except Exception as e:
            logger.warning("Failed to fetch model_name from settings: %s", e)

    if not model_name or str(model_name).strip() == "":
        model_name = "gpt-4"
        logger.info("Using ultimate fallback model_name: %s", model_name)

    return model_name


def _trigger_thread_summarization(store, workspace_id: str, thread_id: str):
    """Trigger background thread summarization if thread needs it."""
    try:
        thread = store.conversation_threads.get_thread(thread_id)
        default_titles = ["New Conversation", "Untitled", "Default Conversation"]
        if thread and (not thread.title or thread.title in default_titles):
            logger.info("Triggering background summarization for thread %s", thread_id)
            from ..utils.thread_summarizer import summarize_thread
            import asyncio

            asyncio.create_task(
                summarize_thread(
                    workspace_id=workspace_id,
                    thread_id=thread_id,
                    store=store,
                    model_name="gemini-2.5-flash-lite",
                )
            )
    except Exception as e:
        logger.warning("Failed to trigger thread summarization: %s", e)
