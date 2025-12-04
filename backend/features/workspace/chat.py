"""
Workspace Chat Routes

Handles /workspaces/{id}/chat endpoint and CTA actions.
"""

import logging
import traceback
import sys
import json
import re
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Path, Body, Depends, Request
from fastapi.responses import StreamingResponse

from backend.app.models.workspace import Workspace, WorkspaceChatRequest, WorkspaceChatResponse
from backend.app.routes.workspace_dependencies import (
    get_workspace,
    get_orchestrator
)
from backend.app.services.conversation_orchestrator import ConversationOrchestrator

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces-chat"])
logger = logging.getLogger(__name__)


# Playbook trigger pattern: [EXECUTE_PLAYBOOK: playbook_code]
PLAYBOOK_TRIGGER_PATTERN = re.compile(r'\[EXECUTE_PLAYBOOK:\s*([a-zA-Z0-9_-]+)\]')


async def _check_and_trigger_playbook(
    full_text: str,
    workspace: Workspace,
    workspace_id: str,
    profile_id: str,
    execution_mode: str
) -> Optional[Dict[str, Any]]:
    """
    Check if LLM response contains playbook trigger marker and execute if found

    Args:
        full_text: Full LLM response text
        workspace: Workspace object
        workspace_id: Workspace ID
        profile_id: User profile ID
        execution_mode: Current execution mode

    Returns:
        Dict with execution info if triggered, None otherwise
    """
    logger.info(f"[PlaybookTrigger] Checking for playbook trigger. execution_mode={execution_mode}, text_length={len(full_text)}")

    # Only process triggers in execution or hybrid mode
    if execution_mode not in ("execution", "hybrid"):
        logger.info(f"[PlaybookTrigger] Skipping trigger check: execution_mode='{execution_mode}' is not 'execution' or 'hybrid'")
        return None

    # Find playbook trigger marker
    match = PLAYBOOK_TRIGGER_PATTERN.search(full_text)
    if not match:
        logger.info(f"[PlaybookTrigger] No playbook trigger marker found in response text")
        # Log a sample of the text for debugging
        sample_text = full_text[:200] + "..." if len(full_text) > 200 else full_text
        logger.debug(f"[PlaybookTrigger] Response text sample: {sample_text}")
        return None

    playbook_code = match.group(1)
    logger.info(f"[PlaybookTrigger] Found trigger for playbook: {playbook_code}")

    try:
        from backend.app.services.playbook_run_executor import PlaybookRunExecutor
        from backend.app.services.playbook_loader import PlaybookLoader

        # Verify playbook exists
        loader = PlaybookLoader()
        playbook_run = loader.load_playbook_run(playbook_code=playbook_code)
        if not playbook_run:
            logger.warning(f"[PlaybookTrigger] Playbook not found: {playbook_code}, using fallback")

            # MVP Fallback: Use generic drafting when playbook not found
            expected_artifacts = getattr(workspace, 'expected_artifacts', None)
            if execution_mode in ("execution", "hybrid"):
                from backend.app.services.execution_fallback_service import generate_fallback_artifact
                fallback_result = await generate_fallback_artifact(
                    user_request=f"Execute playbook: {playbook_code}",
                    workspace_id=workspace_id,
                    profile_id=profile_id,
                    expected_artifacts=expected_artifacts
                )
                return {
                    "status": "fallback",
                    "playbook_code": playbook_code,
                    "message": f"Playbook '{playbook_code}' not found, using generic drafting",
                    "fallback_result": fallback_result
                }

            return {
                "status": "error",
                "playbook_code": playbook_code,
                "message": f"Playbook '{playbook_code}' not found"
            }

        # Execute playbook
        executor = PlaybookRunExecutor()
        result = await executor.execute_playbook_run(
            playbook_code=playbook_code,
            profile_id=profile_id,
            workspace_id=workspace_id,
            inputs=None,
            target_language=workspace.default_locale
        )

        logger.info(f"[PlaybookTrigger] Playbook {playbook_code} executed successfully")
        return {
            "status": "triggered",
            "playbook_code": playbook_code,
            "playbook_name": playbook_run.playbook.metadata.name if playbook_run.playbook else playbook_code,
            "execution_mode": result.get("execution_mode", "workflow"),
            "execution_id": result.get("execution_id") or result.get("result", {}).get("execution_id")
        }

    except Exception as e:
        logger.error(f"[PlaybookTrigger] Failed to execute playbook {playbook_code}: {e}", exc_info=True)
        return {
            "status": "error",
            "playbook_code": playbook_code,
            "message": str(e)
        }


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
                    from backend.app.models.mindscape import MindEvent, EventType, EventActor
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

                    # Execution plan generation is unified in non-streaming path to avoid duplication
                    logger.info(f"WorkspaceChat: Execution plan generation moved to non-streaming path to avoid duplication")
                    print(f"WorkspaceChat: Execution plan generation moved to non-streaming path to avoid duplication", file=sys.stderr)

                    # Send initial event
                    yield f"data: {json.dumps({'type': 'user_message', 'event_id': user_event.id})}\n\n"

                    # Generate streaming response
                    from backend.app.services.conversation.qa_response_generator import QAResponseGenerator
                    from backend.app.services.stores.timeline_items_store import TimelineItemsStore
                    from backend.app.routes.workspace_dependencies import get_timeline_items_store

                    timeline_items_store = TimelineItemsStore(orchestrator.store.db_path)

                    # Get locale from workspace and profile context
                    from backend.app.shared.i18n_loader import get_locale_from_context
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
                    from backend.app.services.conversation.context_builder import ContextBuilder
                    from backend.app.capabilities.core_llm.services.generate import run as generate_text
                    from backend.app.services.system_settings_store import SystemSettingsStore

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
                        from backend.app.services.playbook_loader import PlaybookLoader
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
                        from backend.app.services.playbook_store import PlaybookStore
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

                    # Inject playbook capabilities into system prompt based on execution mode
                    try:
                        from backend.app.shared.prompt_templates import (
                            build_workspace_context_prompt,
                            build_execution_mode_prompt
                        )
                        from backend.app.shared.i18n_loader import get_locale_from_context

                        # Get locale for language policy
                        profile = None
                        try:
                            if profile_id:
                                profile = orchestrator.store.get_profile(profile_id)
                        except Exception:
                            pass
                        locale = get_locale_from_context(profile=profile, workspace=workspace) or "zh-TW"

                        # Get execution mode settings from workspace
                        execution_mode = getattr(workspace, 'execution_mode', None) or "qa"
                        expected_artifacts = getattr(workspace, 'expected_artifacts', None)
                        execution_priority = getattr(workspace, 'execution_priority', None) or "medium"

                        # Generate ExecutionPlan (Chain-of-Thought) for execution/hybrid mode
                        execution_plan = None
                        if execution_mode in ("execution", "hybrid"):
                            try:
                                from backend.app.services.execution_plan_generator import (
                                    generate_execution_plan,
                                    record_execution_plan_event
                                )
                                execution_plan = await generate_execution_plan(
                                    user_request=request.message,
                                    workspace_id=workspace_id,
                                    message_id=user_event.id,
                                    execution_mode=execution_mode,
                                    expected_artifacts=expected_artifacts,
                                    available_playbooks=available_playbooks,
                                    llm_provider=None,  # Will use fallback for now
                                    model_name=model_name or "gpt-4o-mini"
                                )
                                if execution_plan:
                                    # Record plan as EXECUTION_PLAN MindEvent
                                    await record_execution_plan_event(
                                        plan=execution_plan,
                                        profile_id=profile_id,
                                        project_id=workspace.primary_project_id
                                    )
                                    # Send plan to frontend via SSE
                                    plan_payload = execution_plan.to_event_payload()
                                    logger.info(f"[ExecutionPlan] Generated ExecutionPlan with {len(execution_plan.steps)} steps, {len(execution_plan.tasks)} tasks, plan_id={execution_plan.id}")
                                    logger.info(f"[ExecutionPlan] Plan payload keys: {list(plan_payload.keys())}, step_count={plan_payload.get('step_count', 0)}")
                                    logger.info(f"[ExecutionPlan] Steps in payload: {[s.get('step_id', 'unknown') for s in plan_payload.get('steps', [])]}")
                                    print(f"[ExecutionPlan] Sending execution_plan SSE event with {len(execution_plan.steps)} steps", file=sys.stderr)
                                    yield f"data: {json.dumps({'type': 'execution_plan', 'plan': plan_payload})}\n\n"
                                    logger.info(f"[ExecutionPlan] ExecutionPlan SSE event sent successfully")

                                    # Execute plan if it has tasks (unified execution path)
                                    if execution_plan.tasks:
                                        try:
                                            # Collect task updates for SSE notification
                                            task_updates = []

                                            def task_event_callback(event_type: str, task_data: Dict[str, Any]):
                                                """Callback to collect task updates for SSE notification"""
                                                task_updates.append({
                                                    'event_type': event_type,
                                                    'task_data': task_data
                                                })

                                            # Execute plan asynchronously (don't block streaming)
                                            execution_results = await orchestrator.execution_coordinator.execute_plan(
                                                execution_plan=execution_plan,
                                                workspace_id=workspace_id,
                                                profile_id=profile_id,
                                                message_id=user_event.id,
                                                files=request.files,
                                                message=request.message,
                                                project_id=workspace.primary_project_id,
                                                task_event_callback=task_event_callback
                                            )
                                            logger.info(f"[ExecutionPlan] Execution completed - executed: {len(execution_results.get('executed_tasks', []))}, suggestions: {len(execution_results.get('suggestion_cards', []))}")
                                            print(f"[ExecutionPlan] Execution completed - executed: {len(execution_results.get('executed_tasks', []))}, suggestions: {len(execution_results.get('suggestion_cards', []))}", file=sys.stderr)

                                            # Send task updates via SSE immediately when tasks are created
                                            for update in task_updates:
                                                logger.info(f"[ExecutionPlan] Sending task_update event via SSE: {update['event_type']}, task_id={update['task_data'].get('id')}")
                                                print(f"[ExecutionPlan] Sending task_update event via SSE: {update['event_type']}, task_id={update['task_data'].get('id')}", file=sys.stderr)
                                                yield f"data: {json.dumps({'type': 'task_update', 'event_type': update['event_type'], 'task': update['task_data']})}\n\n"

                                            # Also send execution results summary
                                            if execution_results.get('executed_tasks') or execution_results.get('suggestion_cards'):
                                                logger.info(f"[ExecutionPlan] Sending execution_results summary via SSE: {len(execution_results.get('executed_tasks', []))} executed, {len(execution_results.get('suggestion_cards', []))} suggestions")
                                                print(f"[ExecutionPlan] Sending execution_results summary via SSE: {len(execution_results.get('executed_tasks', []))} executed, {len(execution_results.get('suggestion_cards', []))} suggestions", file=sys.stderr)
                                                yield f"data: {json.dumps({'type': 'execution_results', 'executed_tasks': execution_results.get('executed_tasks', []), 'suggestion_cards': execution_results.get('suggestion_cards', [])})}\n\n"
                                        except Exception as exec_error:
                                            logger.warning(f"[ExecutionPlan] Execution failed: {exec_error}", exc_info=True)
                                            print(f"[ExecutionPlan] Execution failed: {exec_error}", file=sys.stderr)
                            except Exception as e:
                                logger.warning(f"Failed to generate ExecutionPlan: {e}", exc_info=True)

                        # Build system prompt based on execution mode
                        if execution_mode == "execution":
                            workspace_system_prompt = build_execution_mode_prompt(
                                preferred_language=locale,
                                include_language_policy=True,
                                workspace_id=workspace_id,
                                available_playbooks=available_playbooks,
                                expected_artifacts=expected_artifacts,
                                execution_priority=execution_priority
                            )
                            logger.info(f"Using EXECUTION mode prompt (priority={execution_priority})")
                        elif execution_mode == "hybrid":
                            qa_prompt = build_workspace_context_prompt(
                                preferred_language=locale,
                                include_language_policy=False,
                                workspace_id=workspace_id,
                                available_playbooks=available_playbooks
                            )
                            execution_prompt = build_execution_mode_prompt(
                                preferred_language=locale,
                                include_language_policy=True,
                                workspace_id=workspace_id,
                                available_playbooks=available_playbooks,
                                expected_artifacts=expected_artifacts,
                                execution_priority=execution_priority
                            )
                            workspace_system_prompt = f"""{qa_prompt}

---

**EXECUTION MODE ACTIVE:**
{execution_prompt}
"""
                            logger.info(f"Using HYBRID mode prompt (priority={execution_priority})")
                        else:
                            workspace_system_prompt = build_workspace_context_prompt(
                                preferred_language=locale,
                                include_language_policy=True,
                                workspace_id=workspace_id,
                                available_playbooks=available_playbooks
                            )
                            logger.info("Using QA mode prompt")

                        # Replace the base system instructions in enhanced_prompt
                        if "You are an intelligent workspace assistant" in enhanced_prompt or "You are an **Execution Agent**" in enhanced_prompt:
                            ctx_marker = "Context from this workspace:"
                            if ctx_marker in enhanced_prompt:
                                ctx_start = enhanced_prompt.find(ctx_marker)
                                context_part = enhanced_prompt[ctx_start:]
                            enhanced_prompt = workspace_system_prompt + "\n\n" + context_part
                            logger.info(f"Injected {execution_mode} mode prompt into system prompt")
                        else:
                            enhanced_prompt = workspace_system_prompt + "\n\n" + enhanced_prompt
                            logger.info(f"Prepended {execution_mode} mode prompt to system prompt")
                    except Exception as e:
                        logger.warning(f"Failed to inject execution mode prompt: {e}", exc_info=True)

                    # Calculate context token count for display
                    try:
                        context_token_count = context_builder.estimate_token_count(enhanced_prompt, model_name) or 0
                    except Exception as e:
                        logger.warning(f"Failed to estimate token count: {e}")
                        context_token_count = 0

                    # Stream from LLM
                    from backend.app.services.agent_runner import LLMProviderManager
                    from backend.app.services.config_store import ConfigStore
                    from backend.app.services.model_config_store import ModelConfigStore
                    from backend.app.services.system_settings_store import SystemSettingsStore
                    import os

                    # Get model configuration to determine provider
                    model_store = ModelConfigStore()
                    settings_store = SystemSettingsStore()
                    model_config = None
                    provider_name = None

                    if model_name:
                        try:
                            # Try to find model by name (search in all models)
                            from backend.app.models.model_provider import ModelType
                            all_models = model_store.get_all_models(model_type=ModelType.CHAT, enabled=True)
                            for model in all_models:
                                if model.model_name == model_name:
                                    model_config = model
                                    provider_name = model.provider_name
                                    break

                            # If not found, check if it's a gemini model
                            if not model_config and "gemini" in model_name.lower():
                                provider_name = "vertex-ai"
                                logger.info(f"Model {model_name} not found in config, but detected as Gemini model, using vertex-ai provider")
                        except Exception as e:
                            logger.warning(f"Failed to get model config for {model_name}: {e}")
                            # Fallback: if model name contains "gemini", use vertex-ai
                            if "gemini" in model_name.lower():
                                provider_name = "vertex-ai"

                    config_store = ConfigStore()
                    config = config_store.get_or_create_config("default-user")
                    openai_key = config.agent_backend.openai_api_key or os.getenv("OPENAI_API_KEY")
                    anthropic_key = config.agent_backend.anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")

                    # Get Vertex AI configuration from system settings
                    service_account_setting = settings_store.get_setting("vertex_ai_service_account_json")
                    vertex_project_setting = settings_store.get_setting("vertex_ai_project_id")
                    vertex_location_setting = settings_store.get_setting("vertex_ai_location")

                    vertex_service_account_json = (service_account_setting.value if service_account_setting and service_account_setting.value else None) or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
                    vertex_project_id = (vertex_project_setting.value if vertex_project_setting and vertex_project_setting.value else None) or os.getenv("GOOGLE_CLOUD_PROJECT")
                    vertex_location = (vertex_location_setting.value if vertex_location_setting and vertex_location_setting.value else None) or os.getenv("VERTEX_LOCATION", "us-central1")

                    llm_provider = LLMProviderManager(
                        openai_key=openai_key,
                        anthropic_key=anthropic_key,
                        vertex_api_key=vertex_service_account_json,
                        vertex_project_id=vertex_project_id,
                        vertex_location=vertex_location
                    )

                    # Get provider based on user's selected model - no fallback
                    logger.info(f"Selecting provider for model {model_name}, provider_name={provider_name}, available_providers={llm_provider.get_available_providers()}")

                    if provider_name:
                        provider = llm_provider.get_provider(provider_name)
                        if not provider:
                            error_msg = f"Provider '{provider_name}' not available for model '{model_name}'. Please check your API configuration. Available providers: {llm_provider.get_available_providers()}"
                            logger.error(error_msg)
                            yield f"data: {json.dumps({'type': 'error', 'message': error_msg})}\n\n"
                            return
                    else:
                        error_msg = f"Cannot determine LLM provider: model '{model_name}' not specified or unknown model name. Please configure chat_model in system settings."
                        logger.error(error_msg)
                        yield f"data: {json.dumps({'type': 'error', 'message': error_msg})}\n\n"
                        return

                    # For SSE streaming, we need direct access to the stream object to yield chunks
                    # provider.chat_completion(stream=True) collects all chunks and returns full text,
                    # which doesn't work for SSE. So we need provider-specific streaming.
                    provider_type = type(provider).__name__
                    logger.info(f"Selected provider type: {provider_type} for model {model_name}")

                    # Set model_to_use for all provider types
                    model_to_use = model_name or "gpt-4o-mini"

                    # Build messages for all provider types (before branching)
                    # Parse enhanced_prompt to extract system and user parts
                    if "User question:" in enhanced_prompt:
                        parts = enhanced_prompt.split("User question:", 1)
                        system_part = parts[0].strip()
                        user_part = request.message
                    else:
                        # Fallback: use enhanced_prompt as system, message as user
                        system_part = enhanced_prompt
                        user_part = request.message

                    # Check token count and truncate if necessary
                    from backend.app.services.conversation.model_context_presets import get_context_preset
                    from backend.app.services.conversation.context_builder import ContextBuilder

                    # Get model's context limit
                    preset = get_context_preset(model_to_use)
                    model_context_limits = {
                        "gpt-3.5-turbo": 12000,
                        "gpt-4": 12000,
                        "gpt-4-turbo": 12000,
                        "gpt-4o": 120000,
                        "gpt-4o-mini": 120000,
                        "gpt-5.1": 120000,
                        "gpt-4.1": 120000,
                    }
                    max_input_tokens = model_context_limits.get(model_to_use, 12000)

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
                        if "## Recent Conversation:" in system_part:
                            conv_start = system_part.find("## Recent Conversation:")
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

                    # Build messages for all providers
                    from backend.app.shared.llm_utils import build_prompt
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

                        # Stream response
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
                        from backend.app.models.mindscape import MindEvent, EventType, EventActor
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

                        # Check for playbook trigger in execution mode
                        logger.info(f"[PlaybookTrigger] Checking trigger after OpenAIProvider response. execution_mode={execution_mode}, workspace_id={workspace_id}")
                        playbook_trigger_result = await _check_and_trigger_playbook(
                            full_text=full_text,
                            workspace=workspace,
                            workspace_id=workspace_id,
                            profile_id=profile_id,
                            execution_mode=execution_mode
                        )
                        if playbook_trigger_result:
                            logger.info(f"[PlaybookTrigger] Trigger result: {playbook_trigger_result}")
                            yield f"data: {json.dumps({'type': 'playbook_triggered', **playbook_trigger_result})}\n\n"
                        else:
                            logger.info(f"[PlaybookTrigger] No trigger result returned for OpenAIProvider")

                        # Send completion event with context token count
                        yield f"data: {json.dumps({'type': 'complete', 'event_id': assistant_event.id, 'context_tokens': context_token_count})}\n\n"
                    elif provider_type == 'AnthropicProvider':
                        # Anthropic streaming support (if needed in future)
                        # For now, fall back to non-streaming
                        logger.warning(f"AnthropicProvider streaming not yet implemented for SSE")
                        yield f"data: {json.dumps({'type': 'error', 'message': 'Streaming not supported for Anthropic provider yet'})}\n\n"
                    elif provider_type == 'VertexAIProvider':
                        # Vertex AI streaming support
                        logger.info(f"Using VertexAIProvider for model {model_to_use}")
                        full_text = ""

                        # Use provider's chat_completion_stream if available
                        if hasattr(provider, 'chat_completion_stream'):
                            async for chunk_content in provider.chat_completion_stream(
                                messages=messages,
                                model=model_to_use,
                                temperature=0.7,
                                max_tokens=8000
                            ):
                                full_text += chunk_content
                                yield f"data: {json.dumps({'type': 'chunk', 'content': chunk_content})}\n\n"
                        else:
                            # Fallback: use non-streaming and simulate streaming
                            logger.warning("VertexAIProvider does not support streaming, using non-streaming mode")
                            response_text = await provider.chat_completion(
                                messages=messages,
                                model=model_to_use,
                                temperature=0.7,
                                max_tokens=8000
                            )
                            # Simulate streaming by sending chunks
                            chunk_size = 10
                            for i in range(0, len(response_text), chunk_size):
                                chunk = response_text[i:i+chunk_size]
                                full_text += chunk
                                yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"

                        # Create assistant event
                        from backend.app.models.mindscape import MindEvent, EventType, EventActor
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

                        # Check for playbook trigger in execution mode
                        logger.info(f"[PlaybookTrigger] Checking trigger after VertexAIProvider response. execution_mode={execution_mode}, workspace_id={workspace_id}")
                        playbook_trigger_result = await _check_and_trigger_playbook(
                            full_text=full_text,
                            workspace=workspace,
                            workspace_id=workspace_id,
                            profile_id=profile_id,
                            execution_mode=execution_mode
                        )
                        if playbook_trigger_result:
                            logger.info(f"[PlaybookTrigger] Trigger result: {playbook_trigger_result}")
                            yield f"data: {json.dumps({'type': 'playbook_triggered', **playbook_trigger_result})}\n\n"
                        else:
                            logger.info(f"[PlaybookTrigger] No trigger result returned for VertexAIProvider")

                        # Send completion event with context token count
                        yield f"data: {json.dumps({'type': 'complete', 'event_id': assistant_event.id, 'context_tokens': context_token_count})}\n\n"
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
