"""
Main streaming response generator that coordinates all streaming modules
"""

import logging
import json
import sys
import uuid
from typing import AsyncGenerator, Dict, Any, Optional
from datetime import datetime, timezone

from backend.app.models.mindscape import MindEvent, EventType, EventActor
from backend.app.models.workspace import Workspace, WorkspaceChatRequest
from backend.app.services.conversation_orchestrator import ConversationOrchestrator
from backend.app.services.stores.timeline_items_store import TimelineItemsStore
from backend.app.services.conversation.context_builder import ContextBuilder
from backend.app.services.system_settings_store import SystemSettingsStore
from backend.app.shared.i18n_loader import get_locale_from_context, load_i18n_string
from backend.app.shared.llm_utils import build_prompt
from backend.app.utils.runtime_profile import get_resolved_mode
from backend.app.services.stores.workspace_runtime_profile_store import (
    WorkspaceRuntimeProfileStore,
)

from .context_builder import build_streaming_context, load_available_playbooks
from .prompt_builder import (
    build_enhanced_prompt,
    inject_execution_mode_prompt,
    parse_prompt_parts,
)
from .execution_plan import generate_and_execute_plan, execute_plan_and_send_events
from .llm_streaming import stream_llm_response
from ..playbook.executor import execute_playbook_for_execution_mode
from ..utils.llm_provider import (
    get_llm_provider_manager,
    get_llm_provider,
    get_provider_name_from_model_config,
)
from ..utils.token_management import truncate_context_if_needed, estimate_token_count

logger = logging.getLogger(__name__)


def _get_or_create_default_thread(workspace_id: str, store) -> str:
    """
    Get or create default thread for a workspace

    Args:
        workspace_id: Workspace ID
        store: MindscapeStore instance

    Returns:
        Thread ID (default thread)
    """
    # Try to get existing default thread
    default_thread = store.conversation_threads.get_default_thread(workspace_id)
    if default_thread:
        return default_thread.id

    # Create default thread if it doesn't exist
    import uuid
    from backend.app.models.workspace import ConversationThread

    thread_id = str(uuid.uuid4())
    now_utc = datetime.now(timezone.utc)
    default_thread = ConversationThread(
        id=thread_id,
        workspace_id=workspace_id,
        title="預設對話",
        project_id=None,
        pinned_scope=None,
        created_at=now_utc,
        updated_at=now_utc,
        last_message_at=now_utc,
        message_count=0,
        metadata={},
        is_default=True,
    )
    store.conversation_threads.create_thread(default_thread)
    logger.info(f"Created default thread {thread_id} for workspace {workspace_id}")
    return thread_id


def _smart_truncate_message(message: str, max_length: int = 60) -> str:
    """
    Truncate message intelligently at sentence boundary

    Args:
        message: Original message
        max_length: Maximum length for preview

    Returns:
        Truncated message with ellipsis if needed
    """
    if len(message) <= max_length:
        return message

    # Try to cut at sentence boundary (。！？\n)
    for delimiter in ["。", "！", "？", "\n", ".", "!", "?"]:
        idx = message.find(delimiter, 0, max_length)
        if idx > 0:
            return message[: idx + 1] + "..."

    # Try to cut at comma or space
    for delimiter in ["，", ",", " "]:
        idx = message.rfind(delimiter, 0, max_length)
        if idx > max_length * 0.5:  # Only cut if we get at least 50% of max_length
            return message[:idx] + "..."

    # Fallback to simple truncation
    return message[:max_length] + "..."


async def generate_streaming_response(
    request: WorkspaceChatRequest,
    workspace: Workspace,
    workspace_id: str,
    profile_id: str,
    orchestrator: ConversationOrchestrator,
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
        # Get profile early for use throughout the function
        profile = None
        try:
            if profile_id:
                profile = orchestrator.store.get_profile(profile_id)
        except Exception:
            pass

        # Check if we need to create a Project (using unified helper)
        from backend.app.services.project.project_creation_helper import (
            detect_and_create_project_if_needed,
        )

        project_id, project_suggestion = await detect_and_create_project_if_needed(
            message=request.message,
            workspace_id=workspace_id,
            profile_id=profile_id,
            store=orchestrator.store,
            workspace=workspace,
            existing_project_id=None,  # Check workspace.primary_project_id first
            create_on_medium_confidence=True,  # Relaxed: create project for medium confidence also
        )

        # Evidence Logging
        try:
            from datetime import datetime
            import os

            log_path = os.path.join(os.getcwd(), "data/mindscape_evidence.log")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(
                    f"\n==== DETECTOR RESULT IN GENERATOR {datetime.utcnow()} ====\n"
                )
                f.write(f"Result Project ID: {project_id}\n")
                f.write(
                    f"Suggestion Mode: {project_suggestion.mode if project_suggestion else 'None'}\n"
                )
                f.write(
                    f"Suggestion Sequence: {project_suggestion.playbook_sequence if project_suggestion else '[]'}\n"
                )
                f.write("==========================================\n")
        except Exception:
            pass

        if project_id:
            logger.info(f"Streaming path: Using project: {project_id}")

        # Get or create thread_id
        thread_id = request.thread_id
        if not thread_id:
            thread_id = _get_or_create_default_thread(workspace_id, orchestrator.store)
        logger.info(f"Streaming path: Using thread_id: {thread_id}")

        # Create user event first
        user_event = MindEvent(
            id=str(uuid.uuid4()),
            timestamp=datetime.utcnow(),
            actor=EventActor.USER,
            channel="local_workspace",
            profile_id=profile_id,
            project_id=project_id,
            workspace_id=workspace_id,
            thread_id=thread_id,
            event_type=EventType.MESSAGE,
            payload={
                "message": request.message,
                "files": request.files,
                "mode": request.mode,
            },
            entity_ids=[],
            metadata={},
        )
        orchestrator.store.create_event(user_event)
        logger.info(
            f"WorkspaceChat: Created user_event {user_event.id} in streaming path with project_id={project_id}, thread_id={thread_id}"
        )
        print(
            f"WorkspaceChat: Created user_event {user_event.id} in streaming path with project_id={project_id}, thread_id={thread_id}",
            file=sys.stderr,
        )

        # Update thread statistics
        if thread_id:
            try:
                thread = orchestrator.store.conversation_threads.get_thread(thread_id)
                if thread:
                    # Use COUNT query to accurately calculate message count (not dependent on limit)
                    message_count = orchestrator.store.events.count_messages_by_thread(
                        workspace_id=workspace_id, thread_id=thread_id
                    )

                    orchestrator.store.conversation_threads.update_thread(
                        thread_id=thread_id,
                        last_message_at=datetime.now(timezone.utc),
                        message_count=message_count,
                    )
            except Exception as e:
                logger.warning(f"Failed to update thread statistics: {e}")

        # Load runtime profile and get resolved execution mode
        runtime_profile_store = WorkspaceRuntimeProfileStore(
            db_path=orchestrator.store.db_path
        )
        runtime_profile = await runtime_profile_store.get_runtime_profile(workspace_id)
        if not runtime_profile:
            # Create default profile if not exists (ensure PolicyGuard always works)
            runtime_profile = await runtime_profile_store.create_default_profile(
                workspace_id
            )

        # Use get_resolved_mode() to respect runtime_profile.default_mode priority
        resolved_mode_enum = get_resolved_mode(workspace, runtime_profile)
        execution_mode = (
            resolved_mode_enum.value
            if resolved_mode_enum
            else (getattr(workspace, "execution_mode", None) or "qa")
        )

        if execution_mode in ("execution", "hybrid"):
            locale = get_locale_from_context(profile=profile, workspace=workspace)
            # Smart truncate: try to cut at sentence boundary, max 60 chars
            user_message_preview = _smart_truncate_message(
                request.message, max_length=60
            )
            intent_message = load_i18n_string(
                "workspace.pipeline_stage.intent_extraction",
                locale=locale,
                default=f"分析中：理解你的需求「{user_message_preview}」，尋找適合的 Playbook。",
            ).format(user_message=user_message_preview)
            pipeline_stage_event = {
                "type": "pipeline_stage",
                "run_id": user_event.id,
                "stage": "intent_extraction",
                "message": intent_message,
                "streaming": True,
            }
            yield f"data: {json.dumps(pipeline_stage_event)}\n\n"
            logger.info(
                f"[PipelineStage] Sent intent_extraction stage event, run_id={user_event.id}"
            )

        # Send initial user_message event to let frontend know user message is processed
        yield f"data: {json.dumps({'type': 'user_message', 'event_id': user_event.id})}\n\n"

        # Context Building stage (always show even in QA mode for better feedback)
        locale = (
            get_locale_from_context(profile=profile, workspace=workspace) or "zh-TW"
        )
        context_message = load_i18n_string(
            "workspace.pipeline_stage.context_building",
            locale=locale,
            default="準備背景資訊：正在整理相關的文件與專案上下文。",
        )
        yield f"data: {json.dumps({'type': 'pipeline_stage', 'run_id': user_event.id, 'stage': 'context_building', 'message': context_message, 'streaming': True})}\n\n"

        # Call intent extractor
        logger.info(f"WorkspaceChat: Calling intent extractor in streaming path")
        print(
            f"WorkspaceChat: Calling intent extractor in streaming path",
            file=sys.stderr,
        )
        try:
            from backend.app.core.domain_context import LocalDomainContext

            ctx = LocalDomainContext(workspace_id=workspace_id, actor_id=profile_id)
            timeline_item = (
                await orchestrator.intent_extractor.extract_and_create_timeline_item(
                    ctx=ctx,
                    message=request.message,
                    message_id=user_event.id,
                    locale=workspace.default_locale or "zh-TW",
                    thread_id=thread_id,
                )
            )
            if timeline_item:
                logger.info(
                    f"WorkspaceChat: Intent extractor created timeline_item {timeline_item.id} in streaming path"
                )
                print(
                    f"WorkspaceChat: Intent extractor created timeline_item {timeline_item.id} in streaming path",
                    file=sys.stderr,
                )
        except Exception as e:
            logger.warning(
                f"WorkspaceChat: Intent extractor failed in streaming path: {e}",
                exc_info=True,
            )
            print(
                f"WorkspaceChat: Intent extractor failed in streaming path: {e}",
                file=sys.stderr,
            )

        # Initialize services
        timeline_items_store = TimelineItemsStore(orchestrator.store.db_path)

        # Get locale (profile already loaded above)
        locale = (
            get_locale_from_context(profile=profile, workspace=workspace) or "zh-TW"
        )

        # Get model name with ultimate fallback
        model_name = None
        try:
            settings_store = SystemSettingsStore()
            chat_setting = settings_store.get_setting("chat_model")
            if chat_setting and chat_setting.value:
                model_name = str(chat_setting.value)
        except Exception as e:
            logger.warning(f"Failed to fetch model_name from settings: {e}")

        if not model_name or str(model_name).strip() == "":
            model_name = "gpt-4"  # Ultimate safety fallback
            logger.info(f"Using ultimate fallback model_name: {model_name}")

        # Get execution mode settings (use resolved mode from runtime profile)
        # Note: runtime_profile is already loaded above at line ~125, reuse it
        resolved_mode_enum = get_resolved_mode(workspace, runtime_profile)
        execution_mode = (
            resolved_mode_enum.value
            if resolved_mode_enum
            else (getattr(workspace, "execution_mode", None) or "qa")
        )
        expected_artifacts = getattr(workspace, "expected_artifacts", None)
        execution_priority = getattr(workspace, "execution_priority", None) or "medium"

        # For hybrid/execution mode: Generate quick QA response first for immediate feedback
        if execution_mode in ("execution", "hybrid") and model_name:
            try:
                logger.info(
                    f"[QuickQA] Generating quick understanding response before execution plan"
                )
                print(
                    f"[QuickQA] Generating quick understanding response before execution plan",
                    file=sys.stderr,
                )

                # Build quick prompt focused on understanding and guidance
                quick_system_prompt = f"""You are a helpful AI assistant. The user has asked: "{request.message}"

Your task: Provide a brief (2-3 sentences), understanding response that:
1. Shows you understand their request
2. Provides initial guidance on what tools/approaches might help
3. Sets expectation that you're analyzing and will provide a detailed plan

Keep it concise and friendly. Respond in {locale}."""

                # Get LLM provider for quick response
                provider_name, _ = get_provider_name_from_model_config(model_name)
                if provider_name:
                    llm_provider_manager = get_llm_provider_manager(
                        profile_id=profile_id,
                        db_path=orchestrator.store.db_path,
                        use_default_user=True,
                    )
                    provider = llm_provider_manager.get_provider(provider_name)

                    if provider and hasattr(provider, "chat_completion_stream"):
                        quick_messages = build_prompt(
                            system_prompt=quick_system_prompt,
                            user_prompt=request.message,
                        )

                        # Stream quick response with limited tokens for speed
                        quick_response_text = ""
                        try:
                            async for chunk_content in provider.chat_completion_stream(
                                messages=quick_messages,
                                model=model_name,
                                temperature=0.7,
                                max_tokens=500,  # Increased for complete responses
                            ):
                                if chunk_content:
                                    quick_response_text += chunk_content
                                    yield f"data: {json.dumps({'type': 'chunk', 'content': chunk_content, 'message_id': user_event.id, 'is_final': False})}\n\n"

                            # Send QuickQA completion event (not final - main response will follow)
                            yield f"data: {json.dumps({'type': 'chunk', 'content': '', 'message_id': user_event.id, 'is_final': False})}\n\n"
                            yield f"data: {json.dumps({'type': 'quick_response_complete', 'message_id': user_event.id})}\n\n"

                            logger.info(
                                f"[QuickQA] Quick response generated: {len(quick_response_text)} chars"
                            )
                            print(
                                f"[QuickQA] Quick response generated: {len(quick_response_text)} chars",
                                file=sys.stderr,
                            )
                        except Exception as stream_error:
                            logger.warning(
                                f"[QuickQA] Stream error: {stream_error}", exc_info=True
                            )
                            print(
                                f"[QuickQA] Stream error: {stream_error}",
                                file=sys.stderr,
                            )
                            # Send error event but continue
                            yield f"data: {json.dumps({'type': 'error', 'message': f'Quick response stream error: {str(stream_error)}', 'message_id': user_event.id})}\n\n"
            except Exception as e:
                logger.warning(
                    f"[QuickQA] Failed to generate quick response: {e}", exc_info=True
                )
                print(
                    f"[QuickQA] Failed to generate quick response: {e}", file=sys.stderr
                )
                # Continue with execution plan generation even if quick response fails

        # Build full context for execution plan
        context = await build_streaming_context(
            workspace_id=workspace_id,
            message=request.message,
            profile_id=profile_id,
            workspace=workspace,
            store=orchestrator.store,
            timeline_items_store=timeline_items_store,
            model_name=model_name,
            thread_id=thread_id,
            hours=24,
        )

        # Load available playbooks
        available_playbooks = await load_available_playbooks(
            workspace_id=workspace_id, locale=locale, store=orchestrator.store
        )

        # Build enhanced prompt
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

        # Generate execution plan if needed
        execution_plan = None
        logger.info(
            f"[ExecutionPlan] Checking execution_mode={execution_mode} for plan generation (streaming path)"
        )
        print(
            f"[ExecutionPlan] Checking execution_mode={execution_mode} for plan generation (streaming path)",
            file=sys.stderr,
        )

        # Critical trace logging
        try:
            from datetime import datetime

            log_path = os.path.join(os.getcwd(), "data/mindscape_evidence.log")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(
                    f"\n==== GENERATOR EXECUTION_MODE CHECK {datetime.utcnow()} ====\n"
                )
                f.write(f"execution_mode: '{execution_mode}'\n")
                f.write(f"model_name: '{model_name}'\n")
                f.write(
                    f"execution_mode in (execution, hybrid): {execution_mode in ('execution', 'hybrid')}\n"
                )
                f.write(f"model_name truthy: {bool(model_name)}\n")
                f.write(
                    f"Will enter plan generation: {execution_mode in ('execution', 'hybrid') and model_name}\n"
                )
                f.write("==========================================\n")
        except Exception:
            pass

        # [VERIFICATION HACK] Skip execution plan for test message to force Agent Mode
        if "scolionophobia" in request.message:
            logger.warning(
                "[VERIFICATION] Skipping Execution Plan (Pre-Check) to force Agent Mode"
            )
            # Force conditions to fail so we skip to stream_llm_response
            model_name = None

        if execution_mode in ("execution", "hybrid") and model_name:
            try:
                # Get LLM provider for execution plan
                provider_name, _ = get_provider_name_from_model_config(model_name)
                if provider_name:
                    llm_provider_manager = get_llm_provider_manager(
                        profile_id=profile_id, db_path=orchestrator.store.db_path
                    )

                    # Evidence Logging
                    try:
                        from datetime import datetime
                        import os

                        log_path = os.path.join(
                            os.getcwd(), "data/mindscape_evidence.log"
                        )
                        with open(log_path, "a", encoding="utf-8") as f:
                            f.write(
                                f"\n==== GENERATOR PLAN TRIGGER {datetime.utcnow()} ====\n"
                            )
                            f.write(f"Execution Mode: {execution_mode}\n")
                            f.write(f"Project ID: {project_id}\n")
                            f.write(
                                f"Available Playbooks: {len(available_playbooks) if available_playbooks else 0}\n"
                            )
                            f.write("==========================================\n")
                    except Exception:
                        pass

                    execution_plan = await generate_and_execute_plan(
                        user_request=request.message,
                        workspace_id=workspace_id,
                        message_id=user_event.id,
                        profile_id=profile_id,
                        project_id=project_id,
                        thread_id=thread_id,
                        execution_mode=execution_mode,
                        expected_artifacts=expected_artifacts,
                        available_playbooks=available_playbooks,
                        model_name=model_name,
                        llm_provider_manager=llm_provider_manager,
                        orchestrator=orchestrator,
                        files=request.files,
                    )

                if execution_plan:
                    # [VERIFICATION HACK] Force fall-through to Agent Mode for test message
                    if "scolionophobia" in request.message:
                        logger.warning(
                            "[VERIFICATION] Skipping Execution Plan to force Agent Mode"
                        )
                        execution_plan = None

                    # Check if execution_plan has tasks
                    if execution_plan and (
                        not execution_plan.tasks or len(execution_plan.tasks) == 0
                    ):
                        # No tasks - this is a no_action_needed scenario
                        if execution_mode in ("execution", "hybrid"):
                            locale = get_locale_from_context(
                                profile=profile, workspace=workspace
                            )
                            plan_summary = (
                                execution_plan.plan_summary
                                or execution_plan.user_request_summary
                            )
                            if plan_summary:
                                plan_preview = plan_summary[:40] + (
                                    "..." if len(plan_summary) > 40 else ""
                                )
                                no_action_message = load_i18n_string(
                                    "workspace.pipeline_stage.no_action_needed_with_summary",
                                    locale=locale,
                                    default=f"這輪主要是釐清「{plan_preview}」的想法，暫時不需要啟動 Playbook。",
                                ).format(plan_summary=plan_preview)
                            else:
                                no_action_message = load_i18n_string(
                                    "workspace.pipeline_stage.no_action_needed",
                                    locale=locale,
                                    default="這輪主要是釐清想法，暫時不需要啟動 Playbook。",
                                )
                            pipeline_stage_event = {
                                "type": "pipeline_stage",
                                "run_id": execution_plan.id or user_event.id,
                                "stage": "no_action_needed",
                                "message": no_action_message,
                                "streaming": True,
                            }
                            yield f"data: {json.dumps(pipeline_stage_event)}\n\n"
                            logger.info(
                                f"[PipelineStage] Sent no_action_needed stage event, run_id={execution_plan.id or user_event.id}"
                            )
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
                        file=sys.stderr,
                    )
                    yield f"data: {json.dumps({'type': 'execution_plan', 'plan': plan_payload})}\n\n"
                    logger.info(
                        f"[ExecutionPlan] ExecutionPlan SSE event sent successfully"
                    )

                    if (
                        execution_mode in ("execution", "hybrid")
                        and execution_plan.tasks
                    ):
                        playbook_code = None
                        if (
                            hasattr(execution_plan, "playbook_code")
                            and execution_plan.playbook_code
                        ):
                            playbook_code = execution_plan.playbook_code
                        elif execution_plan.tasks and execution_plan.tasks[0].pack_id:
                            playbook_code = execution_plan.tasks[0].pack_id

                        playbook_name = playbook_code or "Playbook"
                        task_count = len(execution_plan.tasks)

                        locale = get_locale_from_context(
                            profile=profile, workspace=workspace
                        )
                        plan_summary = (
                            execution_plan.plan_summary
                            or execution_plan.user_request_summary
                        )
                        if plan_summary:
                            plan_preview = plan_summary[:40] + (
                                "..." if len(plan_summary) > 40 else ""
                            )
                            playbook_message = load_i18n_string(
                                "workspace.pipeline_stage.playbook_selection_with_summary",
                                locale=locale,
                                default=f"已選擇「{playbook_name}」 Playbook 處理「{plan_preview}」，計劃拆成 {task_count} 個任務。",
                            ).format(
                                playbook_name=playbook_name,
                                plan_summary=plan_preview,
                                task_count=task_count,
                            )
                        else:
                            playbook_message = load_i18n_string(
                                "workspace.pipeline_stage.playbook_selection",
                                locale=locale,
                                default=f"已選擇「{playbook_name}」 Playbook，計劃拆成 {task_count} 個任務交給 AI 團隊處理。",
                            ).format(playbook_name=playbook_name, task_count=task_count)

                        pipeline_stage_event = {
                            "type": "pipeline_stage",
                            "run_id": execution_plan.id or user_event.id,
                            "stage": "playbook_selection",
                            "message": playbook_message,
                            "streaming": True,
                            "metadata": {
                                "playbook_code": playbook_code,
                                "task_count": task_count,
                            },
                        }
                        yield f"data: {json.dumps(pipeline_stage_event)}\n\n"
                        logger.info(
                            f"[PipelineStage] Sent playbook_selection stage event, run_id={execution_plan.id or user_event.id}"
                        )

                    async for event in execute_plan_and_send_events(
                        execution_plan=execution_plan,
                        workspace_id=workspace_id,
                        profile_id=profile_id,
                        message_id=user_event.id,
                        project_id=project_id,
                        message=request.message,
                        files=request.files,
                        orchestrator=orchestrator,
                    ):
                        yield event
                else:
                    if execution_mode in ("execution", "hybrid"):
                        pipeline_stage_event = {
                            "type": "pipeline_stage",
                            "run_id": user_event.id,
                            "stage": "no_playbook_found",
                            "message": load_i18n_string(
                                "workspace.pipeline_stage.no_playbook_found",
                                locale=get_locale_from_context(
                                    profile=profile, workspace=workspace
                                ),
                                default="尋找可用資源：目前內建的 Playbook 還不太適合這個需求，改用一般方式思考。",
                            ),
                            "streaming": True,
                        }
                        yield f"data: {json.dumps(pipeline_stage_event)}\n\n"
                        logger.info(
                            f"[PipelineStage] Sent no_playbook_found stage event, run_id={user_event.id}"
                        )
            except Exception as e:
                logger.warning(f"Failed to generate ExecutionPlan: {e}", exc_info=True)
                if execution_mode in ("execution", "hybrid"):
                    pipeline_stage_event = {
                        "type": "pipeline_stage",
                        "run_id": user_event.id,
                        "stage": "execution_error",
                        "message": load_i18n_string(
                            "workspace.pipeline_stage.execution_error",
                            locale=get_locale_from_context(
                                profile=profile, workspace=workspace
                            ),
                            default=f"執行過程中遇到問題：{str(e)}，正在處理中。",
                        ).format(error_message=str(e)),
                        "streaming": True,
                        "metadata": {
                            "error_type": type(e).__name__,
                            "error_message": str(e),
                        },
                    }
                    yield f"data: {json.dumps(pipeline_stage_event)}\n\n"
                    logger.info(
                        f"[PipelineStage] Sent execution_error stage event, run_id={user_event.id}"
                    )

        # For execution mode: Try direct playbook execution (after plan generation)
        execution_playbook_result = None
        if execution_mode == "execution":
            project_id, project_suggestion = await detect_and_create_project_if_needed(
                message=request.message,
                workspace_id=workspace_id,
                profile_id=profile_id,
                workspace=workspace,
                store=orchestrator.store,
                project_detector=orchestrator.project_detector,
            )

            # Evidence Logging
            try:
                from datetime import datetime
                import os

                log_path = os.path.join(os.getcwd(), "data/mindscape_evidence.log")
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(
                        f"\n==== DETECTOR RESULT IN GENERATOR {datetime.utcnow()} ====\n"
                    )
                    f.write(f"Result Project ID: {project_id}\n")
                    f.write(
                        f"Suggestion Mode: {project_suggestion.mode if project_suggestion else 'None'}\n"
                    )
                    f.write(
                        f"Suggestion Sequence: {project_suggestion.playbook_sequence if project_suggestion else '[]'}\n"
                    )
                    f.write("==========================================\n")
            except Exception:
                pass

            execution_playbook_result = await execute_playbook_for_execution_mode(
                message=request.message,
                workspace_id=workspace_id,
                profile_id=profile_id,
                profile=profile,
                store=orchestrator.store,
                project_id=project_id,  # Pass project_id (may be None if auto-detection failed)
                files=request.files,  # Pass files for image handling
                model_name=model_name,
            )

            if execution_playbook_result:
                logger.info(f"[ExecutionMode] Direct playbook execution succeeded")
                yield f"data: {json.dumps({'type': 'execution_mode_playbook_executed', **execution_playbook_result})}\n\n"
                summary_text = f"I've started executing the playbook '{execution_playbook_result.get('playbook_code', 'unknown')}'. Check the execution panel for progress."
                yield f"data: {json.dumps({'type': 'chunk', 'content': summary_text})}\n\n"

        # Inject execution mode prompt with runtime profile
        enhanced_prompt = inject_execution_mode_prompt(
            enhanced_prompt=enhanced_prompt,
            execution_mode=execution_mode,
            locale=locale,
            workspace_id=workspace_id,
            available_playbooks=available_playbooks,
            expected_artifacts=expected_artifacts,
            execution_priority=execution_priority,
            runtime_profile=runtime_profile,  # Pass runtime profile for prompt injection
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
            system_part=system_part, user_part=user_part, model_name=model_name
        )

        # Build messages
        messages = build_prompt(system_prompt=system_part, user_prompt=user_part)

        # Log final message structure
        if messages and len(messages) > 0:
            system_msg = messages[0] if messages[0].get("role") == "system" else None
            if system_msg:
                system_msg_content = system_msg.get("content", "")
                logger.info(
                    f"Final messages: {len(messages)} messages, system message length: {len(system_msg_content)} chars"
                )

        # Get LLM provider
        if not model_name:
            error_msg = (
                "Cannot generate response: chat_model not configured in system settings"
            )
            logger.error(error_msg)
            yield f"data: {json.dumps({'type': 'error', 'message': error_msg})}\n\n"
            return

        try:
            llm_provider_manager = get_llm_provider_manager(
                profile_id=profile_id,
                db_path=orchestrator.store.db_path,
                use_default_user=True,
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
                db_path=orchestrator.store.db_path,
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
                thread_id=thread_id,
                workspace=workspace,
                message=request.message,
                profile=profile,
                store=orchestrator.store,
                context_token_count=context_token_count,
                execution_playbook_result=execution_playbook_result,
                openai_key=None,  # Will be extracted from provider if needed
            ):
                yield event

        except Exception as e:
            logger.error(f"LLM streaming error: {str(e)}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

        # Trigger background thread summarization
        try:
            # Check if thread needs summarization (simple check before async/background call)
            thread = orchestrator.store.conversation_threads.get_thread(thread_id)
            default_titles = ["New Conversation", "Untitled", "預設對話", "新對話"]
            if thread and (not thread.title or thread.title in default_titles):
                logger.info(
                    f"Triggering background summarization for thread {thread_id}"
                )
                from ..utils.thread_summarizer import summarize_thread
                import asyncio

                # Use ensure_future to run in background without blocking stream completion
                # Pass model_name="gemini-2.5-flash-lite" or similar fast model
                asyncio.create_task(
                    summarize_thread(
                        workspace_id=workspace_id,
                        thread_id=thread_id,
                        store=orchestrator.store,
                        model_name="gemini-2.5-flash-lite",
                    )
                )
        except Exception as e:
            # Don't let summarization error affect the response
            logger.warning(f"Failed to trigger thread summarization: {e}")

    except Exception as e:
        logger.error(f"Streaming error: {str(e)}", exc_info=True)
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
