"""
Workspace Chat Routes

Handles /workspaces/{id}/chat endpoint and CTA actions.
"""

import logging
import traceback
import sys
import json
from fastapi import APIRouter, HTTPException, Path, Body, Depends, Request
from fastapi.responses import StreamingResponse

from ..models.workspace import Workspace, WorkspaceChatRequest, WorkspaceChatResponse
from ..routes.workspace_dependencies import (
    get_workspace,
    get_orchestrator
)
from ..services.conversation_orchestrator import ConversationOrchestrator

router = APIRouter(tags=["workspaces-chat"])
logger = logging.getLogger(__name__)


@router.post("/{workspace_id}/chat", response_model=WorkspaceChatResponse)
async def workspace_chat(
    workspace_id: str = Path(..., description="Workspace ID"),
    request: WorkspaceChatRequest = Body(...),
    workspace: Workspace = Depends(get_workspace),
    orchestrator: ConversationOrchestrator = Depends(get_orchestrator)
):
    """
    Workspace chat endpoint - unified entry point for all interactions

    Handles:
    - User messages
    - File uploads
    - Playbook triggering
    - QA responses
    - CTA actions (via timeline_item_id + action)
    - Dynamic suggestion actions (via action + action_params)
    """
    try:
        profile_id = workspace.owner_user_id

        if request.timeline_item_id and request.action:
            result = await orchestrator.handle_cta(
                workspace_id=workspace_id,
                profile_id=profile_id,
                timeline_item_id=request.timeline_item_id,
                action=request.action,
                confirm=request.confirm,
                project_id=workspace.primary_project_id
            )
            return WorkspaceChatResponse(**result)

        if request.action and not request.timeline_item_id:
            # Generate message_id for suggestion action if not provided
            import uuid
            message_id = request.message_id if hasattr(request, 'message_id') and request.message_id else str(uuid.uuid4())
            result = await orchestrator.handle_suggestion_action(
                workspace_id=workspace_id,
                profile_id=profile_id,
                action=request.action,
                action_params=request.action_params or {},
                project_id=workspace.primary_project_id,
                message_id=message_id
            )
            return WorkspaceChatResponse(**result)

        if not request.message:
            raise HTTPException(status_code=400, detail="Message is required for non-CTA requests")

        logger.info(f"WorkspaceChat: Received message request, stream={request.stream}, message={request.message[:50]}...")
        print(f"WorkspaceChat: Received message request, stream={request.stream}, message={request.message[:50]}...", file=sys.stderr)

        # Handle streaming requests
        if request.stream:
            logger.info(f"WorkspaceChat: Using STREAMING path (bypasses route_message)")
            print(f"WorkspaceChat: Using STREAMING path (bypasses route_message)", file=sys.stderr)
            from fastapi.responses import StreamingResponse
            import asyncio

            async def generate_stream():
                """Generate streaming response"""
                try:
                    # Create user event first
                    from ..models.mindscape import MindEvent, EventType, EventActor
                    from datetime import datetime
                    import uuid

                    user_event = MindEvent(
                        id=str(uuid.uuid4()),
                        timestamp=datetime.utcnow(),
                        actor=EventActor.USER,
                        channel="local_workspace",
                        profile_id=profile_id,
                        project_id=workspace.primary_project_id,
                        workspace_id=workspace_id,
                        event_type=EventType.MESSAGE,
                        payload={"message": request.message, "files": request.files, "mode": request.mode},
                        entity_ids=[],
                        metadata={}
                    )
                    orchestrator.store.create_event(user_event)
                    logger.info(f"WorkspaceChat: Created user_event {user_event.id} in streaming path")
                    print(f"WorkspaceChat: Created user_event {user_event.id} in streaming path", file=sys.stderr)

                    # CRITICAL: Also call intent extractor and execution coordinator in streaming path
                    # This ensures AI team collaboration is triggered even for streaming requests
                    logger.info(f"WorkspaceChat: Calling intent extractor in streaming path")
                    print(f"WorkspaceChat: Calling intent extractor in streaming path", file=sys.stderr)
                    try:
                        timeline_item = await orchestrator.intent_extractor.extract_and_create_timeline_item(
                            workspace_id=workspace_id,
                            profile_id=profile_id,
                            message=request.message,
                            message_id=user_event.id,
                            locale=workspace.default_locale or "zh-TW"
                        )
                        if timeline_item:
                            logger.info(f"WorkspaceChat: Intent extractor created timeline_item {timeline_item.id} in streaming path")
                            print(f"WorkspaceChat: Intent extractor created timeline_item {timeline_item.id} in streaming path", file=sys.stderr)
                    except Exception as e:
                        logger.warning(f"WorkspaceChat: Intent extractor failed in streaming path: {e}", exc_info=True)
                        print(f"WorkspaceChat: Intent extractor failed in streaming path: {e}", file=sys.stderr)

                    # Generate execution plan and execute (non-blocking for streaming)
                    logger.info(f"WorkspaceChat: Generating execution plan in streaming path")
                    print(f"WorkspaceChat: Generating execution plan in streaming path", file=sys.stderr)
                    try:
                        # Use LLM-based planning as primary, fallback to rule-based if LLM fails
                        execution_plan = await orchestrator.plan_builder.generate_execution_plan(
                            message=request.message,
                            files=request.files,
                            workspace_id=workspace_id,
                            profile_id=profile_id,
                            message_id=user_event.id,
                            use_llm=True  # Priority: LLM-based analysis, fallback to rule-based
                        )
                        logger.info(f"WorkspaceChat: Generated execution plan with {len(execution_plan.tasks)} tasks in streaming path")
                        print(f"WorkspaceChat: Generated execution plan with {len(execution_plan.tasks)} tasks in streaming path", file=sys.stderr)

                        if execution_plan.tasks:
                            # Execute plan asynchronously (don't block streaming)
                            execution_results = await orchestrator.execution_coordinator.execute_plan(
                                execution_plan=execution_plan,
                                workspace_id=workspace_id,
                                profile_id=profile_id,
                                message_id=user_event.id,
                                files=request.files,
                                message=request.message,
                                project_id=workspace.primary_project_id
                            )
                            logger.info(f"WorkspaceChat: Execution plan completed in streaming path - executed: {len(execution_results.get('executed_tasks', []))}, suggestions: {len(execution_results.get('suggestion_cards', []))}")
                            print(f"WorkspaceChat: Execution plan completed in streaming path - executed: {len(execution_results.get('executed_tasks', []))}, suggestions: {len(execution_results.get('suggestion_cards', []))}", file=sys.stderr)
                    except Exception as e:
                        logger.warning(f"WorkspaceChat: Execution plan failed in streaming path: {e}", exc_info=True)
                        print(f"WorkspaceChat: Execution plan failed in streaming path: {e}", file=sys.stderr)

                    # Send initial event
                    yield f"data: {json.dumps({'type': 'user_message', 'event_id': user_event.id})}\n\n"

                    # Generate streaming response
                    from ..services.conversation.qa_response_generator import QAResponseGenerator
                    from ..services.stores.timeline_items_store import TimelineItemsStore
                    from ..routes.workspace_dependencies import get_timeline_items_store

                    timeline_items_store = TimelineItemsStore(orchestrator.store.db_path)

                    # Get locale from workspace and profile context
                    from ..shared.i18n_loader import get_locale_from_context
                    profile = None
                    try:
                        if profile_id:
                            profile = orchestrator.store.get_profile(profile_id)
                    except Exception:
                        pass
                    locale = get_locale_from_context(profile=profile, workspace=workspace) or "zh-TW"

                    qa_generator = QAResponseGenerator(
                        store=orchestrator.store,
                        timeline_items_store=timeline_items_store,
                        default_locale=locale
                    )

                    # Stream LLM response
                    from ..services.conversation.context_builder import ContextBuilder
                    from ..capabilities.core_llm.services.generate import run as generate_text
                    from ..services.system_settings_store import SystemSettingsStore

                    model_name = None
                    try:
                        settings_store = SystemSettingsStore()
                        chat_setting = settings_store.get_setting("chat_model")
                        if chat_setting and chat_setting.value:
                            model_name = str(chat_setting.value)
                    except Exception:
                        pass

                    context_builder = ContextBuilder(
                        store=orchestrator.store,
                        timeline_items_store=timeline_items_store,
                        model_name=model_name
                    )
                    context = await context_builder.build_qa_context(
                        workspace_id=workspace_id,
                        message=request.message,
                        profile_id=profile_id,
                        workspace=workspace,
                        hours=24
                    )

                    # Get available playbooks for workspace context
                    # Merge playbooks from both sources:
                    # 1. PlaybookLoader (file system) - system default playbooks
                    # 2. PlaybookStore (database) - user-imported and personalized playbooks
                    available_playbooks = []
                    playbook_codes_seen = set()

                    try:
                        # First, load from file system (system defaults)
                        from ..services.playbook_loader import PlaybookLoader
                        playbook_loader = PlaybookLoader()
                        file_playbooks = playbook_loader.load_all_playbooks()

                        for pb in file_playbooks:
                            metadata = pb.metadata if hasattr(pb, 'metadata') else None
                            if metadata and metadata.playbook_code:
                                # Extract output_types from playbook manifest or metadata
                                output_types = []
                                if hasattr(pb, 'manifest') and pb.manifest:
                                    output_types = pb.manifest.get('output_types', []) or []
                                elif hasattr(metadata, 'output_types'):
                                    output_types = metadata.output_types or []

                                available_playbooks.append({
                                    'playbook_code': metadata.playbook_code,
                                    'name': metadata.name,
                                    'description': metadata.description or '',
                                    'tags': metadata.tags or [],
                                    'output_type': output_types[0] if output_types else None,
                                    'output_types': output_types
                                })
                                playbook_codes_seen.add(metadata.playbook_code)

                        logger.info(f"Loaded {len(available_playbooks)} playbooks from file system")
                    except Exception as e:
                        logger.warning(f"Failed to load playbooks from file system: {e}", exc_info=True)

                    try:
                        # Then, load from database (user-imported and personalized)
                        from ..services.playbook_store import PlaybookStore
                        playbook_store = PlaybookStore(orchestrator.store.db_path)
                        db_playbooks = playbook_store.list_playbooks()

                        db_count = 0
                        for pb in db_playbooks:
                            # Skip if already loaded from file system
                            if pb.playbook_code in playbook_codes_seen:
                                continue

                            # Extract output_types (database playbooks may have different structure)
                            output_types = getattr(pb, 'output_types', []) or []
                            if isinstance(output_types, str):
                                output_types = [output_types] if output_types else []

                            available_playbooks.append({
                                'playbook_code': pb.playbook_code,
                                'name': pb.name,
                                'description': pb.description or '',
                                'tags': pb.tags or [],
                                'output_type': output_types[0] if output_types else None,
                                'output_types': output_types
                            })
                            playbook_codes_seen.add(pb.playbook_code)
                            db_count += 1

                        if db_count > 0:
                            logger.info(f"Loaded {db_count} additional playbooks from database")
                    except Exception as e:
                        logger.warning(f"Failed to load playbooks from database: {e}", exc_info=True)

                    logger.info(f"Found {len(available_playbooks)} total playbooks for workspace context")

                    # Log context content for debugging
                    if context is not None:
                        logger.info(f"Built context length: {len(context)} chars")
                        logger.info(f"Context contains - Intents: {'Active Intents' in context}, Tasks: {'Current Tasks' in context}, History: {'Recent Conversation' in context}, Timeline: {'Recent Timeline Activity' in context}")
                    else:
                        logger.warning("Context is None, using empty string")
                        context = ""

                    enhanced_prompt = context_builder.build_enhanced_prompt(
                        message=request.message,
                        context=context or ""
                    )

                    if enhanced_prompt is not None:
                        logger.info(f"Enhanced prompt length: {len(enhanced_prompt)} chars")
                        # Log enhanced_prompt to see actual content
                        if "Context from this workspace:" in enhanced_prompt:
                            ctx_start = enhanced_prompt.find("Context from this workspace:")
                            logger.info(f"Enhanced prompt contains context at position {ctx_start}")
                            logger.info(f"Context section preview (first 1000 chars after 'Context from this workspace:'): {enhanced_prompt[ctx_start:ctx_start+1000]}...")
                        else:
                            logger.warning("Enhanced prompt does NOT contain 'Context from this workspace:' marker!")
                    else:
                        logger.warning("Enhanced prompt is None, using empty string")
                        enhanced_prompt = ""

                    # Inject playbook capabilities into system prompt
                    if available_playbooks:
                        try:
                            from ..shared.prompt_templates import build_workspace_context_prompt
                            from ..shared.i18n_loader import get_locale_from_context

                            # Get locale for language policy
                            profile = None
                            try:
                                if profile_id:
                                    profile = orchestrator.store.get_profile(profile_id)
                            except Exception:
                                pass
                            locale = get_locale_from_context(profile=profile, workspace=workspace) or "zh-TW"

                            # Build workspace context with playbook capabilities
                            workspace_context_with_playbooks = build_workspace_context_prompt(
                                preferred_language=locale,
                                include_language_policy=True,
                                workspace_id=workspace_id,
                                available_playbooks=available_playbooks
                            )

                            # Replace the base system instructions in enhanced_prompt with the enhanced version
                            # Find where system instructions start
                            if "You are an intelligent workspace assistant" in enhanced_prompt:
                                # Find the end of system instructions (before "Context from this workspace")
                                sys_start = enhanced_prompt.find("You are an intelligent workspace assistant")
                                ctx_marker = "Context from this workspace:"
                                if ctx_marker in enhanced_prompt:
                                    ctx_start = enhanced_prompt.find(ctx_marker)
                                    # Replace system instructions part with enhanced version
                                    # Keep everything from context marker onwards
                                    context_part = enhanced_prompt[ctx_start:]
                                    # Combine new system instructions with existing context
                                    enhanced_prompt = workspace_context_with_playbooks + "\n\n" + context_part
                                    logger.info("Injected playbook capabilities into system prompt")
                        except Exception as e:
                            logger.warning(f"Failed to inject playbook capabilities: {e}", exc_info=True)

                    # Calculate context token count for display
                    try:
                        context_token_count = context_builder.estimate_token_count(enhanced_prompt, model_name) or 0
                    except Exception as e:
                        logger.warning(f"Failed to estimate token count: {e}")
                        context_token_count = 0

                    # Stream from LLM
                    from ..services.agent_runner import LLMProviderManager
                    from ..services.config_store import ConfigStore
                    import os

                    config_store = ConfigStore()
                    config = config_store.get_or_create_config("default-user")
                    openai_key = config.agent_backend.openai_api_key or os.getenv("OPENAI_API_KEY")
                    anthropic_key = config.agent_backend.anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")
                    llm_provider = LLMProviderManager(openai_key=openai_key, anthropic_key=anthropic_key)

                    provider = llm_provider.get_provider()
                    if not provider:
                        yield f"data: {json.dumps({'type': 'error', 'message': 'No LLM provider available'})}\n\n"
                        return

                    # For SSE streaming, we need direct access to the stream object to yield chunks
                    # provider.chat_completion(stream=True) collects all chunks and returns full text,
                    # which doesn't work for SSE. So we need provider-specific streaming.
                    # TODO: Improve provider abstraction to support stream object return for SSE
                    provider_type = type(provider).__name__

                    if provider_type == 'OpenAIProvider':
                        # Use provider's streaming method for SSE (improved abstraction)
                        # This uses the new chat_completion_stream method that returns stream object
                        use_provider_stream = hasattr(provider, 'chat_completion_stream')

                        if not use_provider_stream:
                            # Fallback to direct client (for backward compatibility)
                            logger.warning("Provider does not support chat_completion_stream, using direct client")
                            import openai
                            openai_key_for_streaming = provider.api_key if hasattr(provider, 'api_key') else openai_key
                            client = openai.AsyncOpenAI(api_key=openai_key_for_streaming)

                        # Build messages - enhanced_prompt contains system instructions + context + user question
                        # enhanced_prompt format:
                        # {system_instructions}
                        #
                        # User question: {message}
                        #
                        # Context from this workspace:
                        # {context}
                        #
                        # Please answer...
                        #
                        # We need to extract:
                        # - system_part = system_instructions + context (everything up to and including context)
                        # - user_part = original user message
                        from ..shared.llm_utils import build_prompt

                        # Extract system part: everything before "User question:" (system_instructions)
                        # PLUS everything from "Context from this workspace:" to "Please answer" (context)
                        if "User question:" in enhanced_prompt and "Context from this workspace:" in enhanced_prompt:
                            # Split at "User question:" to get system_instructions
                            parts1 = enhanced_prompt.split("User question:", 1)
                            system_instructions_part = parts1[0].strip()

                            logger.info(f"system_instructions_part length: {len(system_instructions_part)} chars")
                            logger.info(f"system_instructions_part preview (first 500 chars): {system_instructions_part[:500]}...")
                            logger.info(f"system_instructions_part end (last 500 chars): ...{system_instructions_part[-500:]}")
                            logger.info(f"After split at 'User question:', parts1[1] length: {len(parts1[1])} chars")
                            logger.info(f"parts1[1] preview: {parts1[1][:200]}...")

                            # Extract context part (between "Context from this workspace:" and "Please answer")
                            if "Please answer" in parts1[1]:
                                context_section = parts1[1].split("Please answer", 1)[0]
                                logger.info(f"Context section length: {len(context_section)} chars")
                                logger.info(f"Context section preview: {context_section[:300]}...")

                                # Extract just the context content (remove "Context from this workspace:" label)
                                if "Context from this workspace:" in context_section:
                                    context_content = context_section.split("Context from this workspace:", 1)[1].strip()
                                    logger.info(f"Extracted context_content length: {len(context_content)} chars")
                                    logger.info(f"Context content preview (first 500 chars): {context_content[:500]}...")
                                    logger.info(f"Context content end (last 500 chars): ...{context_content[-500:]}")
                                    system_part = f"{system_instructions_part}\n\nContext from this workspace:\n{context_content}"
                                    logger.info(f"Final system_part length: {len(system_part)} chars")
                                    logger.info(f"Final system_part end (last 500 chars): ...{system_part[-500:]}")
                                else:
                                    logger.warning("'Context from this workspace:' not found in context_section!")
                                    logger.warning(f"context_section content: {context_section[:500]}...")
                                    system_part = f"{system_instructions_part}\n\n{context_section.strip()}"
                            else:
                                logger.warning("'Please answer' not found in parts1[1]!")
                                logger.warning(f"parts1[1] content: {parts1[1][:500]}...")
                                system_part = system_instructions_part

                            user_part = request.message
                        elif "User question:" in enhanced_prompt:
                            # Fallback: if no context section, just use system_instructions
                            parts = enhanced_prompt.split("User question:", 1)
                            system_part = parts[0].strip()
                            user_part = request.message
                        else:
                            # Fallback: use enhanced_prompt as system, message as user
                            system_part = enhanced_prompt
                            user_part = request.message

                        # Log context information for debugging
                        context_has_intents = "Active Intents" in system_part
                        context_has_tasks = "Current Tasks" in system_part
                        context_has_history = "Recent Conversation" in system_part
                        context_has_timeline = "Recent Timeline Activity" in system_part

                        logger.info(f"Context check - Intents: {context_has_intents}, Tasks: {context_has_tasks}, History: {context_has_history}, Timeline: {context_has_timeline}")
                        logger.info(f"System prompt length: {len(system_part)} chars, User prompt: {user_part[:100]}...")

                        # Log actual system prompt content (first 500 chars) for debugging
                        logger.info(f"System prompt preview (first 500 chars): {system_part[:500]}...")

                        # Check token count and truncate if necessary
                        from ..services.conversation.model_context_presets import get_context_preset
                        from ..services.conversation.context_builder import ContextBuilder

                        # Get model's context limit
                        model_to_use = model_name or "gpt-4o-mini"
                        preset = get_context_preset(model_to_use)
                        # Most models reserve ~4k tokens for output, so reduce input limit accordingly
                        # For gpt-3.5-turbo (16k), reserve 4k for output = 12k for input
                        # For gpt-4o (128k), reserve 8k for output = 120k for input
                        model_context_limits = {
                            "gpt-3.5-turbo": 12000,  # 16k - 4k reserve
                            "gpt-4": 12000,  # 16k - 4k reserve
                            "gpt-4-turbo": 12000,  # 16k - 4k reserve
                            "gpt-4o": 120000,  # 128k - 8k reserve
                            "gpt-4o-mini": 120000,  # 128k - 8k reserve
                            "gpt-5.1": 120000,  # 128k - 8k reserve
                            "gpt-4.1": 120000,  # 128k - 8k reserve
                        }
                        max_input_tokens = model_context_limits.get(model_to_use, 12000)  # Default to 12k for safety

                        # Estimate token count for system prompt
                        context_builder = ContextBuilder(model_name=model_to_use)
                        system_tokens = context_builder.estimate_token_count(system_part, model_to_use)
                        user_tokens = context_builder.estimate_token_count(user_part, model_to_use)
                        total_tokens = system_tokens + user_tokens

                        logger.info(f"Token count check - System: {system_tokens}, User: {user_tokens}, Total: {total_tokens}, Limit: {max_input_tokens}")

                        # Truncate system prompt if exceeds limit
                        if total_tokens > max_input_tokens:
                            excess_tokens = total_tokens - max_input_tokens
                            logger.warning(f"Context exceeds token limit by {excess_tokens} tokens, truncating system prompt...")

                            # Priority order: keep workspace context, intents, tasks first, then timeline, then conversation history
                            # Find sections and truncate from least important (conversation history)
                            if "## Recent Conversation:" in system_part:
                                # Truncate conversation history section
                                conv_start = system_part.find("## Recent Conversation:")
                                # Keep everything before conversation history, truncate the rest
                                system_part = system_part[:conv_start] + "\n## Recent Conversation:\n[Conversation history truncated due to token limit]"
                                logger.info("Truncated conversation history section")

                            # Re-estimate after truncation
                            system_tokens = context_builder.estimate_token_count(system_part, model_to_use)
                            total_tokens = system_tokens + user_tokens

                            # If still too long, truncate timeline
                            if total_tokens > max_input_tokens and "## Recent Timeline Activity:" in system_part:
                                timeline_start = system_part.find("## Recent Timeline Activity:")
                                conv_section = "\n## Recent Conversation:\n[Conversation history truncated due to token limit]"
                                system_part = system_part[:timeline_start] + "\n## Recent Timeline Activity:\n[Timeline truncated due to token limit]" + conv_section
                                logger.info("Truncated timeline section")

                            # Final check - if still too long, keep only essential parts
                            system_tokens = context_builder.estimate_token_count(system_part, model_to_use)
                            total_tokens = system_tokens + user_tokens
                            if total_tokens > max_input_tokens:
                                # Keep only workspace context, intents, and tasks
                                essential_parts = []
                                if "## Workspace Context:" in system_part:
                                    ws_start = system_part.find("## Workspace Context:")
                                    ws_end = system_part.find("\n##", ws_start + 1)
                                    if ws_end == -1:
                                        ws_end = len(system_part)
                                    essential_parts.append(system_part[ws_start:ws_end])
                                if "## Active Intents" in system_part:
                                    intents_start = system_part.find("## Active Intents")
                                    intents_end = system_part.find("\n##", intents_start + 1)
                                    if intents_end == -1:
                                        intents_end = len(system_part)
                                    essential_parts.append(system_part[intents_start:intents_end])
                                if "## Current Tasks:" in system_part:
                                    tasks_start = system_part.find("## Current Tasks:")
                                    tasks_end = system_part.find("\n##", tasks_start + 1)
                                    if tasks_end == -1:
                                        tasks_end = len(system_part)
                                    essential_parts.append(system_part[tasks_start:tasks_end])

                                # Rebuild system_part with only essential parts
                                system_instructions_start = system_part.find("You are an intelligent workspace assistant")
                                if system_instructions_start != -1:
                                    instructions_end = system_part.find("\n## Workspace Context:")
                                    if instructions_end == -1:
                                        instructions_end = system_part.find("\n## Active Intents")
                                    if instructions_end != -1:
                                        system_instructions = system_part[system_instructions_start:instructions_end]
                                        system_part = system_instructions + "\n\n" + "\n\n".join(essential_parts)
                                        logger.warning("Truncated to essential context only (workspace, intents, tasks)")

                            # Final token count after truncation
                            system_tokens = context_builder.estimate_token_count(system_part, model_to_use)
                            total_tokens = system_tokens + user_tokens
                            logger.info(f"After truncation - System: {system_tokens}, User: {user_tokens}, Total: {total_tokens}, Limit: {max_input_tokens}")

                        messages = build_prompt(
                            system_prompt=system_part,
                            user_prompt=user_part
                        )

                        # Log final message structure
                        if messages and len(messages) > 0:
                            system_msg = messages[0] if messages[0].get('role') == 'system' else None
                            if system_msg:
                                system_msg_content = system_msg.get('content', '')
                                system_msg_len = len(system_msg_content)
                                logger.info(f"Final messages: {len(messages)} messages, system message length: {system_msg_len} chars")
                                # Log actual system message content preview
                                logger.info(f"System message preview (first 500 chars): {system_msg_content[:500]}...")
                                # Log a sample from the middle to see context content
                                if len(system_msg_content) > 2000:
                                    mid_start = len(system_msg_content) // 2
                                    logger.info(f"System message middle sample (chars {mid_start}-{mid_start+500}): {system_msg_content[mid_start:mid_start+500]}...")
                                # Log end sample to see if context is there
                                if len(system_msg_content) > 1000:
                                    logger.info(f"System message end sample (last 500 chars): ...{system_msg_content[-500:]}")
                                # Check if context sections are actually in the final message
                                logger.info(f"Final system message contains - Intents: {'Active Intents' in system_msg_content}, Tasks: {'Current Tasks' in system_msg_content}, History: {'Recent Conversation' in system_msg_content}, Timeline: {'Recent Timeline Activity' in system_msg_content}")
                                # Check for workspace title in context
                                if workspace:
                                    logger.info(f"Workspace title in system message: {workspace.title in system_msg_content if workspace.title else 'N/A'}")
                            else:
                                logger.warning("No system message found in messages")
                        else:
                            logger.warning("Final messages is empty or None")

                        # Stream response
                        model_to_use = model_name or "gpt-4o-mini"
                        full_text = ""

                        if use_provider_stream:
                            # Use improved provider abstraction
                            async for chunk_content in provider.chat_completion_stream(
                                messages=messages,
                                model=model_to_use,
                                temperature=0.7,
                                max_tokens=8000
                            ):
                                full_text += chunk_content
                                yield f"data: {json.dumps({'type': 'chunk', 'content': chunk_content})}\n\n"
                        else:
                            # Fallback: direct client usage
                            request_params = {
                                "model": model_to_use,
                                "messages": messages,
                                "temperature": 0.7,
                                "stream": True
                            }

                            # Handle max_completion_tokens for newer models
                            model_lower = model_to_use.lower()
                            is_newer_model = "gpt-5" in model_lower or "o1" in model_lower or "o3" in model_lower
                            if is_newer_model:
                                request_params["extra_body"] = {"max_completion_tokens": 8000}
                            else:
                                request_params["max_tokens"] = 8000

                            # Create streaming request - await the coroutine to get the stream
                            stream = await client.chat.completions.create(**request_params)
                            async for chunk in stream:
                                if chunk.choices and len(chunk.choices) > 0:
                                    delta = chunk.choices[0].delta
                                    if hasattr(delta, 'content') and delta.content:
                                        full_text += delta.content
                                        yield f"data: {json.dumps({'type': 'chunk', 'content': delta.content})}\n\n"

                        # Create assistant event
                        from ..models.mindscape import MindEvent, EventType, EventActor
                        assistant_event = MindEvent(
                            id=str(uuid.uuid4()),
                            timestamp=datetime.utcnow(),
                            actor=EventActor.ASSISTANT,
                            channel="local_workspace",
                            profile_id=profile_id,
                            project_id=workspace.primary_project_id,
                            workspace_id=workspace_id,
                            event_type=EventType.MESSAGE,
                            payload={"message": full_text, "response_to": user_event.id},
                            entity_ids=[],
                            metadata={}
                        )
                        orchestrator.store.create_event(assistant_event)

                        # Send completion event with context token count
                        yield f"data: {json.dumps({'type': 'complete', 'event_id': assistant_event.id, 'context_tokens': context_token_count})}\n\n"
                    elif provider_type == 'AnthropicProvider':
                        # Anthropic streaming support (if needed in future)
                        # For now, fall back to non-streaming
                        logger.warning(f"AnthropicProvider streaming not yet implemented for SSE")
                        yield f"data: {json.dumps({'type': 'error', 'message': 'Streaming not supported for Anthropic provider yet'})}\n\n"
                    else:
                        # Other providers - not yet supported for SSE streaming
                        logger.warning(f"Provider {provider_type} streaming not yet implemented for SSE")
                        yield f"data: {json.dumps({'type': 'error', 'message': f'Streaming not supported for {provider_type}'})}\n\n"

                except Exception as e:
                    logger.error(f"Streaming error: {str(e)}", exc_info=True)
                    yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

            return StreamingResponse(
                generate_stream(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no"
                }
            )

        # Non-streaming mode (existing logic)
        result = await orchestrator.route_message(
            workspace_id=workspace_id,
            profile_id=profile_id,
            message=request.message,
            files=request.files,
            mode=request.mode,
            project_id=workspace.primary_project_id,
            workspace=workspace
        )

        return WorkspaceChatResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Workspace chat error: {str(e)}\n{traceback.format_exc()}")
        print(f"ERROR: Workspace chat error: {str(e)}", file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
        raise HTTPException(status_code=500, detail=f"Failed to process workspace chat: {str(e)}")
