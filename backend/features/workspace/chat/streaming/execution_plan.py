"""
Execution plan generation and execution for streaming responses
"""

import logging
import json
import sys
from typing import Dict, Any, Optional, Callable, AsyncGenerator

from backend.app.services.execution_plan_generator import (
    generate_execution_plan,
    record_execution_plan_event
)
from backend.app.services.agent_runner import LLMProviderManager
from backend.app.services.conversation_orchestrator import ConversationOrchestrator
from backend.app.shared.i18n_loader import get_locale_from_context, load_i18n_string

logger = logging.getLogger(__name__)


async def generate_and_execute_plan(
    user_request: str,
    workspace_id: str,
    message_id: str,
    profile_id: str,
    project_id: str,
    execution_mode: str,
    expected_artifacts: Optional[list],
    available_playbooks: list,
    model_name: str,
    llm_provider_manager: LLMProviderManager,
    orchestrator: ConversationOrchestrator,
    files: Optional[list] = None
) -> Optional[Any]:
    """
    Generate execution plan and execute if it has tasks

    Args:
        user_request: User request message
        workspace_id: Workspace ID
        message_id: Message ID
        profile_id: Profile ID
        project_id: Project ID
        execution_mode: Execution mode
        expected_artifacts: Expected artifacts list
        available_playbooks: Available playbooks list
        model_name: Model name
        llm_provider_manager: LLM provider manager
        orchestrator: Conversation orchestrator
        files: Optional file list

    Returns:
        Execution plan if generated, None otherwise
    """
    if execution_mode not in ("execution", "hybrid"):
        return None

    try:
        if not model_name:
            error_msg = "Cannot generate execution plan: chat_model not configured in system settings"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Determine provider from model name
        from ..utils.llm_provider import determine_provider_from_model
        provider_name = determine_provider_from_model(model_name)

        if not provider_name:
            error_msg = (
                f"Cannot determine provider for model '{model_name}'. "
                f"Supported models: gemini-*, gpt-*, o1-*, o3-*, claude-*"
            )
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Get provider
        plan_llm_provider = llm_provider_manager.get_provider(provider_name)
        if not plan_llm_provider:
            error_msg = (
                f"Provider '{provider_name}' not available for model '{model_name}'. "
                f"Please check your API configuration."
            )
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Generate execution plan
        logger.info(f"[ExecutionPlan] Calling generate_execution_plan with model={model_name}, provider={provider_name}")
        print(f"[ExecutionPlan] Calling generate_execution_plan with model={model_name}, provider={provider_name}", file=sys.stderr)
        execution_plan = await generate_execution_plan(
            user_request=user_request,
            workspace_id=workspace_id,
            message_id=message_id,
            execution_mode=execution_mode,
            expected_artifacts=expected_artifacts,
            available_playbooks=available_playbooks,
            llm_provider=llm_provider_manager,
            model_name=model_name
        )

        if not execution_plan:
            logger.warning(f"[ExecutionPlan] generate_execution_plan returned None (plan generation failed or skipped)")
            print(f"[ExecutionPlan] generate_execution_plan returned None (plan generation failed or skipped)", file=sys.stderr)
            return None

        # Record plan as EXECUTION_PLAN MindEvent
        await record_execution_plan_event(
            plan=execution_plan,
            profile_id=profile_id,
            project_id=project_id
        )

        logger.info(
            f"[ExecutionPlan] Generated ExecutionPlan with {len(execution_plan.steps)} steps, "
            f"{len(execution_plan.tasks)} tasks, plan_id={execution_plan.id}"
        )
        logger.info(
            f"[ExecutionPlan] Plan payload keys: {list(execution_plan.to_event_payload().keys())}, "
            f"step_count={len(execution_plan.steps)}"
        )
        logger.info(
            f"[ExecutionPlan] Steps in payload: "
            f"{[s.get('step_id', 'unknown') for s in execution_plan.to_event_payload().get('steps', [])]}"
        )
        print(
            f"[ExecutionPlan] Sending execution_plan SSE event with {len(execution_plan.steps)} steps, "
            f"{len(execution_plan.tasks)} tasks",
            file=sys.stderr
        )

        return execution_plan

    except Exception as e:
        logger.warning(f"Failed to generate ExecutionPlan: {e}", exc_info=True)
        return None


async def execute_plan_and_send_events(
    execution_plan: Any,
    workspace_id: str,
    profile_id: str,
    message_id: str,
    project_id: str,
    message: str,
    files: Optional[list],
    orchestrator: ConversationOrchestrator
) -> AsyncGenerator[str, None]:
    """
    Execute plan and yield SSE events for task updates

    Args:
        execution_plan: Execution plan object
        workspace_id: Workspace ID
        profile_id: Profile ID
        message_id: Message ID
        project_id: Project ID
        message: User message
        files: Optional file list
        orchestrator: Conversation orchestrator

    Yields:
        SSE event strings
    """
    if not execution_plan.tasks:
        return

    try:
        run_id = execution_plan.id if hasattr(execution_plan, 'id') and execution_plan.id else message_id

        workspace = orchestrator.store.get_workspace(workspace_id)
        profile = orchestrator.store.get_profile(profile_id) if profile_id else None
        locale = get_locale_from_context(profile=profile, workspace=workspace)

        execution_start_message = load_i18n_string(
            'workspace.pipeline_stage.execution_start',
            locale=locale,
            default='開始執行任務，AI 團隊正在協作處理中...'
        )

        pipeline_stage_event = {
            'type': 'pipeline_stage',
            'run_id': run_id,
            'stage': 'execution_start',
            'message': execution_start_message,
            'streaming': True
        }
        yield f"data: {json.dumps(pipeline_stage_event)}\n\n"
        logger.info(f"[PipelineStage] Sent execution_start stage event, run_id={run_id}")

        if execution_plan.tasks:
            agent_members = [task.pack_id for task in execution_plan.tasks if hasattr(task, 'pack_id') and task.pack_id]

            if len(agent_members) > 0:
                try:
                    from backend.app.services.ai_team_service import get_member_info
                    first_agent_info = get_member_info(agent_members[0])
                    first_agent_name = first_agent_info.get('name_zh') or first_agent_info.get('name') or agent_members[0] if first_agent_info else agent_members[0]
                except Exception:
                    first_agent_name = agent_members[0]

                if len(agent_members) > 1:
                    try:
                        from backend.app.services.ai_team_service import get_member_info
                        other_agent_names = []
                        for agent_id in agent_members[1:]:
                            agent_info = get_member_info(agent_id)
                            if agent_info:
                                other_agent_names.append(agent_info.get('name_zh') or agent_info.get('name') or agent_id)
                            else:
                                other_agent_names.append(agent_id)
                        other_agents = "、".join(other_agent_names)
                    except Exception:
                        other_agents = "、".join(agent_members[1:])
                    message = load_i18n_string(
                        'workspace.pipeline_stage.task_assignment_multiple',
                        locale=locale,
                        default=f'計劃下一步：交給 {first_agent_name} 先處理，之後再交給 {other_agents} 分別處理。'
                    ).format(first_agent=first_agent_name, other_agents=other_agents)
                else:
                    message = load_i18n_string(
                        'workspace.pipeline_stage.task_assignment_single',
                        locale=locale,
                        default=f'計劃下一步：交給 {first_agent_name} 處理。'
                    ).format(first_agent=first_agent_name)
            else:
                message = load_i18n_string(
                    'workspace.pipeline_stage.task_assignment_fallback',
                    locale=locale,
                    default=f'計劃下一步：執行 {len(execution_plan.tasks)} 個任務。'
                ).format(task_count=len(execution_plan.tasks))

            task_assignment_event = {
                'type': 'pipeline_stage',
                'run_id': run_id,
                'stage': 'task_assignment',
                'message': message,
                'streaming': True,
                'metadata': {
                    'agent_members': agent_members,
                    'task_count': len(execution_plan.tasks)
                }
            }
            yield f"data: {json.dumps(task_assignment_event)}\n\n"
            logger.info(f"[PipelineStage] Sent task_assignment stage event, run_id={run_id}, agents={agent_members}")

        task_updates = []

        def task_event_callback(event_type: str, task_data: Dict[str, Any]):
            """Callback to collect task updates for SSE notification"""
            task_updates.append({
                'event_type': event_type,
                'task_data': task_data
            })

        execution_results = await orchestrator.execution_coordinator.execute_plan(
            execution_plan=execution_plan,
            workspace_id=workspace_id,
            profile_id=profile_id,
            message_id=message_id,
            files=files,
            message=message,
            project_id=project_id,
            task_event_callback=task_event_callback
        )

        logger.info(
            f"[ExecutionPlan] Execution completed - executed: "
            f"{len(execution_results.get('executed_tasks', []))}, "
            f"suggestions: {len(execution_results.get('suggestion_cards', []))}"
        )
        print(
            f"[ExecutionPlan] Execution completed - executed: "
            f"{len(execution_results.get('executed_tasks', []))}, "
            f"suggestions: {len(execution_results.get('suggestion_cards', []))}",
            file=sys.stderr
        )

        for update in task_updates:
            logger.info(
                f"[ExecutionPlan] Sending task_update event via SSE: "
                f"{update['event_type']}, task_id={update['task_data'].get('id')}"
            )
            print(
                f"[ExecutionPlan] Sending task_update event via SSE: "
                f"{update['event_type']}, task_id={update['task_data'].get('id')}",
                file=sys.stderr
            )
            yield f"data: {json.dumps({'type': 'task_update', 'event_type': update['event_type'], 'task': update['task_data']})}\n\n"

        if execution_results.get('executed_tasks') or execution_results.get('suggestion_cards'):
            logger.info(
                f"[ExecutionPlan] Sending execution_results summary via SSE: "
                f"{len(execution_results.get('executed_tasks', []))} executed, "
                f"{len(execution_results.get('suggestion_cards', []))} suggestions"
            )
            print(
                f"[ExecutionPlan] Sending execution_results summary via SSE: "
                f"{len(execution_results.get('executed_tasks', []))} executed, "
                f"{len(execution_results.get('suggestion_cards', []))} suggestions",
                file=sys.stderr
            )
            yield f"data: {json.dumps({'type': 'execution_results', 'executed_tasks': execution_results.get('executed_tasks', []), 'suggestion_cards': execution_results.get('suggestion_cards', [])})}\n\n"

    except Exception as exec_error:
        logger.warning(f"[ExecutionPlan] Execution failed: {exec_error}", exc_info=True)
        print(f"[ExecutionPlan] Execution failed: {exec_error}", file=sys.stderr)

        run_id = execution_plan.id if hasattr(execution_plan, 'id') and execution_plan.id else message_id
        pipeline_stage_event = {
            'type': 'pipeline_stage',
            'run_id': run_id,
            'stage': 'execution_error',
            'message': load_i18n_string(
                'workspace.pipeline_stage.execution_error',
                locale=locale,
                default=f'執行過程中遇到問題：{str(exec_error)}，正在處理中。'
            ).format(error_message=str(exec_error)),
            'streaming': True,
            'metadata': {
                'error_type': type(exec_error).__name__,
                'error_message': str(exec_error)
            }
        }
        yield f"data: {json.dumps(pipeline_stage_event)}\n\n"
        logger.info(f"[PipelineStage] Sent execution_error stage event, run_id={run_id}")

