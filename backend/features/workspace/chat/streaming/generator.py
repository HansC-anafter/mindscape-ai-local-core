"""
Main streaming response generator that coordinates all streaming modules
"""

import logging
import json
import sys
import uuid
from typing import AsyncGenerator, Dict, Any, Optional
from datetime import datetime

from backend.app.models.mindscape import MindEvent, EventType, EventActor
from backend.app.models.workspace import Workspace, WorkspaceChatRequest
from backend.app.services.conversation_orchestrator import ConversationOrchestrator
from backend.app.services.stores.timeline_items_store import TimelineItemsStore
from backend.app.services.conversation.context_builder import ContextBuilder
from backend.app.services.system_settings_store import SystemSettingsStore
from backend.app.shared.i18n_loader import get_locale_from_context
from backend.app.shared.llm_utils import build_prompt

from .context_builder import build_streaming_context, load_available_playbooks
from .prompt_builder import build_enhanced_prompt, inject_execution_mode_prompt, parse_prompt_parts
from .execution_plan import generate_and_execute_plan, execute_plan_and_send_events
from .llm_streaming import stream_llm_response
from ..playbook.executor import execute_playbook_for_execution_mode
from ..utils.llm_provider import get_llm_provider_manager, get_llm_provider, get_provider_name_from_model_config
from ..utils.token_management import truncate_context_if_needed, estimate_token_count

logger = logging.getLogger(__name__)


async def generate_streaming_response(
    request: WorkspaceChatRequest,
    workspace: Workspace,
    workspace_id: str,
    profile_id: str,
    orchestrator: ConversationOrchestrator
) -> AsyncGenerator[str, None]:
    """
    Generate streaming response for workspace chat

    Args:
        request: Chat request
        workspace: Workspace object
        workspace_id: Workspace ID
        profile_id: Profile ID
        orchestrator: Conversation orchestrator

    Yields:
        SSE event strings
    """
    try:
        # Create user event first
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

        execution_mode = getattr(workspace, 'execution_mode', None) or "qa"

        if execution_mode in ("execution", "hybrid"):
            pipeline_stage_event = {
                'type': 'pipeline_stage',
                'run_id': user_event.id,
                'stage': 'intent_extraction',
                'message': '我先幫你釐清這次的核心目標，看看適合用哪一套多平台內容 Playbook。',
                'streaming': True
            }
            yield f"data: {json.dumps(pipeline_stage_event)}\n\n"
            logger.info(f"[PipelineStage] Sent intent_extraction stage event, run_id={user_event.id}")

        # Call intent extractor
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

        # Send initial event
        yield f"data: {json.dumps({'type': 'user_message', 'event_id': user_event.id})}\n\n"

        # Initialize services
        timeline_items_store = TimelineItemsStore(orchestrator.store.db_path)

        # Get locale
        profile = None
        try:
            if profile_id:
                profile = orchestrator.store.get_profile(profile_id)
        except Exception:
            pass
        locale = get_locale_from_context(profile=profile, workspace=workspace) or "zh-TW"

        # Get model name
        model_name = None
        try:
            settings_store = SystemSettingsStore()
            chat_setting = settings_store.get_setting("chat_model")
            if chat_setting and chat_setting.value:
                model_name = str(chat_setting.value)
        except Exception:
            pass

        # Build context
        context = await build_streaming_context(
            workspace_id=workspace_id,
            message=request.message,
            profile_id=profile_id,
            workspace=workspace,
            store=orchestrator.store,
            timeline_items_store=timeline_items_store,
            model_name=model_name,
            hours=24
        )

        # Load available playbooks
        available_playbooks = await load_available_playbooks(
            workspace_id=workspace_id,
            locale=locale,
            store=orchestrator.store
        )

        # Build enhanced prompt
        context_builder = ContextBuilder(
            store=orchestrator.store,
            timeline_items_store=timeline_items_store,
            model_name=model_name
        )
        enhanced_prompt = build_enhanced_prompt(
            message=request.message,
            context=context or "",
            context_builder=context_builder
        )

        # Get execution mode settings
        execution_mode = getattr(workspace, 'execution_mode', None) or "qa"
        expected_artifacts = getattr(workspace, 'expected_artifacts', None)
        execution_priority = getattr(workspace, 'execution_priority', None) or "medium"

        # Generate execution plan if needed
        execution_plan = None
        logger.info(f"[ExecutionPlan] Checking execution_mode={execution_mode} for plan generation (streaming path)")
        print(f"[ExecutionPlan] Checking execution_mode={execution_mode} for plan generation (streaming path)", file=sys.stderr)

        if execution_mode in ("execution", "hybrid") and model_name:
            try:
                # Get LLM provider for execution plan
                provider_name, _ = get_provider_name_from_model_config(model_name)
                if provider_name:
                    llm_provider_manager = get_llm_provider_manager(
                        profile_id=profile_id,
                        db_path=orchestrator.store.db_path
                    )

                    execution_plan = await generate_and_execute_plan(
                        user_request=request.message,
                        workspace_id=workspace_id,
                        message_id=user_event.id,
                        profile_id=profile_id,
                        project_id=workspace.primary_project_id,
                        execution_mode=execution_mode,
                        expected_artifacts=expected_artifacts,
                        available_playbooks=available_playbooks,
                        model_name=model_name,
                        llm_provider_manager=llm_provider_manager,
                        orchestrator=orchestrator,
                        files=request.files
                    )

                    if execution_plan:
                        # Check if execution_plan has tasks
                        if not execution_plan.tasks or len(execution_plan.tasks) == 0:
                            # No tasks - this is a no_action_needed scenario
                            if execution_mode in ("execution", "hybrid"):
                                pipeline_stage_event = {
                                    'type': 'pipeline_stage',
                                    'run_id': execution_plan.id or user_event.id,
                                    'stage': 'no_action_needed',
                                    'message': '這輪主要是幫你釐清想法，暫時不需要叫出內容團隊。',
                                    'streaming': True
                                }
                                yield f"data: {json.dumps(pipeline_stage_event)}\n\n"
                                logger.info(f"[PipelineStage] Sent no_action_needed stage event, run_id={execution_plan.id or user_event.id}")
                        else:
                            plan_payload = execution_plan.to_event_payload()
                        logger.info(
                            f"[ExecutionPlan] Generated ExecutionPlan with {len(execution_plan.steps)} steps, "
                            f"{len(execution_plan.tasks)} tasks, plan_id={execution_plan.id}, "
                            f"ai_team_members={len(plan_payload.get('ai_team_members', []))}"
                        )
                        print(
                            f"[ExecutionPlan] Sending execution_plan SSE event with {len(execution_plan.steps)} steps, "
                            f"ai_team_members={len(plan_payload.get('ai_team_members', []))}",
                            file=sys.stderr
                        )
                        yield f"data: {json.dumps({'type': 'execution_plan', 'plan': plan_payload})}\n\n"
                        logger.info(f"[ExecutionPlan] ExecutionPlan SSE event sent successfully")

                        if execution_mode in ("execution", "hybrid") and execution_plan.tasks:
                            playbook_code = None
                            if hasattr(execution_plan, 'playbook_code') and execution_plan.playbook_code:
                                playbook_code = execution_plan.playbook_code
                            elif execution_plan.tasks and execution_plan.tasks[0].pack_id:
                                playbook_code = execution_plan.tasks[0].pack_id

                            playbook_name = playbook_code or "Playbook"
                            task_count = len(execution_plan.tasks)
                            pipeline_stage_event = {
                                'type': 'pipeline_stage',
                                'run_id': execution_plan.id or user_event.id,
                                'stage': 'playbook_selection',
                                'message': f'已選擇「{playbook_name}」 Playbook，準備拆成 {task_count} 個任務交給內容團隊。',
                                'streaming': True,
                                'metadata': {
                                    'playbook_code': playbook_code,
                                    'task_count': task_count
                                }
                            }
                            yield f"data: {json.dumps(pipeline_stage_event)}\n\n"
                            logger.info(f"[PipelineStage] Sent playbook_selection stage event, run_id={execution_plan.id or user_event.id}")

                        async for event in execute_plan_and_send_events(
                            execution_plan=execution_plan,
                            workspace_id=workspace_id,
                            profile_id=profile_id,
                            message_id=user_event.id,
                            project_id=workspace.primary_project_id,
                            message=request.message,
                            files=request.files,
                            orchestrator=orchestrator
                        ):
                            yield event
                    else:
                        if execution_mode in ("execution", "hybrid"):
                            pipeline_stage_event = {
                                'type': 'pipeline_stage',
                                'run_id': user_event.id,
                                'stage': 'no_playbook_found',
                                'message': '目前內建的 Playbook 還不太適合這個需求，我先用一般方式幫你思考。',
                                'streaming': True
                            }
                            yield f"data: {json.dumps(pipeline_stage_event)}\n\n"
                            logger.info(f"[PipelineStage] Sent no_playbook_found stage event, run_id={user_event.id}")
            except Exception as e:
                logger.warning(f"Failed to generate ExecutionPlan: {e}", exc_info=True)
                if execution_mode in ("execution", "hybrid"):
                    pipeline_stage_event = {
                        'type': 'pipeline_stage',
                        'run_id': user_event.id,
                        'stage': 'execution_error',
                        'message': f'執行過程中遇到問題：{str(e)}',
                        'streaming': True,
                        'metadata': {
                            'error_type': type(e).__name__,
                            'error_message': str(e)
                        }
                    }
                    yield f"data: {json.dumps(pipeline_stage_event)}\n\n"
                    logger.info(f"[PipelineStage] Sent execution_error stage event, run_id={user_event.id}")

        # For execution mode: Try direct playbook execution
        execution_playbook_result = None
        if execution_mode == "execution":
            execution_playbook_result = await execute_playbook_for_execution_mode(
                message=request.message,
                workspace_id=workspace_id,
                profile_id=profile_id,
                profile=profile,
                store=orchestrator.store
            )

            # If direct playbook execution succeeded, skip LLM generation
            if execution_playbook_result:
                logger.info(f"[ExecutionMode] Direct playbook execution succeeded, skipping LLM generation")
                yield f"data: {json.dumps({'type': 'execution_mode_playbook_executed', **execution_playbook_result})}\n\n"
                summary_text = f"I've started executing the playbook '{execution_playbook_result.get('playbook_code', 'unknown')}'. Check the execution panel for progress."
                yield f"data: {json.dumps({'type': 'chunk', 'content': summary_text})}\n\n"
                yield f"data: {json.dumps({'type': 'complete', 'event_id': user_event.id, 'context_tokens': 0})}\n\n"
                return

        # Inject execution mode prompt
        enhanced_prompt = inject_execution_mode_prompt(
            enhanced_prompt=enhanced_prompt,
            execution_mode=execution_mode,
            locale=locale,
            workspace_id=workspace_id,
            available_playbooks=available_playbooks,
            expected_artifacts=expected_artifacts,
            execution_priority=execution_priority
        )

        # Calculate context token count
        try:
            context_token_count = estimate_token_count(enhanced_prompt, model_name) or 0
        except Exception as e:
            logger.warning(f"Failed to estimate token count: {e}")
            context_token_count = 0

        # Parse prompt parts
        system_part, user_part = parse_prompt_parts(enhanced_prompt, request.message)

        # Truncate context if needed
        system_part, system_tokens, total_tokens = truncate_context_if_needed(
            system_part=system_part,
            user_part=user_part,
            model_name=model_name
        )

        # Build messages
        messages = build_prompt(
            system_prompt=system_part,
            user_prompt=user_part
        )

        # Log final message structure
        if messages and len(messages) > 0:
            system_msg = messages[0] if messages[0].get('role') == 'system' else None
            if system_msg:
                system_msg_content = system_msg.get('content', '')
                logger.info(f"Final messages: {len(messages)} messages, system message length: {len(system_msg_content)} chars")

        # Get LLM provider
        if not model_name:
            error_msg = "Cannot generate response: chat_model not configured in system settings"
            logger.error(error_msg)
            yield f"data: {json.dumps({'type': 'error', 'message': error_msg})}\n\n"
            return

        try:
            llm_provider_manager = get_llm_provider_manager(
                profile_id=profile_id,
                db_path=orchestrator.store.db_path,
                use_default_user=True
            )

            provider_name, _ = get_provider_name_from_model_config(model_name)
            if not provider_name:
                error_msg = f"Cannot determine LLM provider: model '{model_name}' not specified or unknown model name. Please configure chat_model in system settings."
                logger.error(error_msg)
                yield f"data: {json.dumps({'type': 'error', 'message': error_msg})}\n\n"
                return

            provider, provider_type = get_llm_provider(
                model_name=model_name,
                llm_provider_manager=llm_provider_manager,
                profile_id=profile_id,
                db_path=orchestrator.store.db_path
            )

            # Stream LLM response
            async for event in stream_llm_response(
                provider=provider,
                provider_type=provider_type,
                messages=messages,
                model_name=model_name,
                execution_mode=execution_mode,
                user_event_id=user_event.id,
                profile_id=profile_id,
                project_id=workspace.primary_project_id,
                workspace_id=workspace_id,
                workspace=workspace,
                message=request.message,
                profile=profile,
                store=orchestrator.store,
                context_token_count=context_token_count,
                execution_playbook_result=execution_playbook_result,
                openai_key=None  # Will be extracted from provider if needed
            ):
                yield event

        except ValueError as e:
            error_msg = str(e)
            logger.error(error_msg)
            yield f"data: {json.dumps({'type': 'error', 'message': error_msg})}\n\n"
        except Exception as e:
            logger.error(f"LLM streaming error: {str(e)}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    except Exception as e:
        logger.error(f"Streaming error: {str(e)}", exc_info=True)
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

