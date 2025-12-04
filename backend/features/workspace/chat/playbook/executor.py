"""
Playbook execution logic for execution and hybrid modes
"""

import logging
from typing import Dict, Any, Optional, List

from backend.app.services.intent_analyzer import IntentPipeline
from backend.app.services.playbook_service import PlaybookService, ExecutionMode as PlaybookExecutionMode
from backend.app.shared.intent_playbook_mapping import select_playbook_for_intent
from backend.app.services.mindscape_store import MindscapeStore

logger = logging.getLogger(__name__)


async def execute_playbook_for_execution_mode(
    message: str,
    workspace_id: str,
    profile_id: str,
    profile: Optional[Any],
    store: MindscapeStore
) -> Optional[Dict[str, Any]]:
    """
    Execute playbook directly for execution mode using intent analysis

    Args:
        message: User message
        workspace_id: Workspace ID
        profile_id: Profile ID
        profile: Profile object (optional)
        store: MindscapeStore instance

    Returns:
        Execution result dict if playbook was executed, None otherwise
    """
    try:
        logger.info(f"[ExecutionMode] Starting direct playbook.run flow for execution mode")

        # Initialize services
        playbook_service = PlaybookService(store=store)
        intent_pipeline = IntentPipeline(
            llm_provider=None,  # Will use default
            store=store,
            playbook_service=playbook_service
        )

        # Analyze intent
        intent_result = await intent_pipeline.analyze(
            user_input=message,
            profile_id=profile_id,
            workspace_id=workspace_id,
            profile=profile
        )

        logger.info(
            f"[ExecutionMode] Intent analysis result: "
            f"task_domain={intent_result.task_domain.value if intent_result.task_domain else None}, "
            f"interaction_type={intent_result.interaction_type.value if intent_result.interaction_type else None}"
        )

        # Select playbook
        logger.info(f"[ExecutionMode] Attempting intent → playbook mapping for user input: {message[:100]}")
        playbook_code = await select_playbook_for_intent(
            intent_result,
            workspace_id,
            playbook_service
        )

        if playbook_code:
            logger.info(
                f"[ExecutionMode] Intent mapping SUCCESS - Selected playbook: {playbook_code} "
                f"for task_domain={intent_result.task_domain.value if intent_result.task_domain else None}"
            )

            # Execute playbook
            try:
                execution_result = await playbook_service.execute_playbook(
                    playbook_code=playbook_code,
                    workspace_id=workspace_id,
                    profile_id=profile_id,
                    inputs={
                        'message': message,
                        'intent': {
                            'task_domain': intent_result.task_domain.value if intent_result.task_domain else None,
                            'interaction_type': intent_result.interaction_type.value if intent_result.interaction_type else None
                        }
                    },
                    execution_mode=PlaybookExecutionMode.ASYNC
                )

                result = {
                    "status": "executed",
                    "playbook_code": playbook_code,
                    "execution_id": execution_result.execution_id,
                    "execution_mode": "direct_playbook_run"
                }

                logger.info(f"[ExecutionMode] Playbook {playbook_code} executed directly, execution_id={execution_result.execution_id}")
                return result

            except Exception as exec_error:
                logger.warning(f"[ExecutionMode] Failed to execute playbook {playbook_code}: {exec_error}", exc_info=True)
                return None
        else:
            logger.warning(
                f"[ExecutionMode] Intent mapping FAILED - No playbook selected for "
                f"task_domain={intent_result.task_domain.value if intent_result.task_domain else None}, "
                f"interaction_type={intent_result.interaction_type.value if intent_result.interaction_type else None}"
            )
            logger.info(f"[ExecutionMode] No playbook selected, falling back to LLM generation")
            return None

    except Exception as e:
        logger.warning(f"[ExecutionMode] Failed in direct playbook.run flow: {e}", exc_info=True)
        return None


async def execute_playbook_for_hybrid_mode(
    message: str,
    executable_tasks: List[str],
    workspace_id: str,
    profile_id: str,
    profile: Optional[Any],
    store: MindscapeStore
) -> Optional[Dict[str, Any]]:
    """
    Execute playbook for hybrid mode based on executable tasks

    Args:
        message: Original user message
        executable_tasks: List of executable tasks from parsed response
        workspace_id: Workspace ID
        profile_id: Profile ID
        profile: Profile object (optional)
        store: MindscapeStore instance

    Returns:
        Execution result dict if playbook was executed, None otherwise
    """
    if not executable_tasks:
        return None

    try:
        # Initialize services
        playbook_service = PlaybookService(store=store)
        intent_pipeline = IntentPipeline(
            llm_provider=None,  # Will use default
            store=store,
            playbook_service=playbook_service
        )

        # Analyze the first executable task (or combine all tasks)
        task_text = executable_tasks[0] if executable_tasks else message

        # Analyze intent
        intent_result = await intent_pipeline.analyze(
            user_input=task_text,
            profile_id=profile_id,
            workspace_id=workspace_id,
            profile=profile
        )

        # Select playbook based on intent
        logger.info(
            f"[AgentMode] Attempting intent → playbook mapping for executable tasks: "
            f"{executable_tasks[:3] if executable_tasks else 'N/A'}"
        )
        playbook_code = await select_playbook_for_intent(
            intent_result,
            workspace_id,
            playbook_service
        )

        if playbook_code:
            logger.info(
                f"[AgentMode] Intent mapping SUCCESS - Selected playbook {playbook_code} "
                f"for executable tasks (task_domain={intent_result.task_domain.value if intent_result.task_domain else None})"
            )
        else:
            logger.warning(
                f"[AgentMode] Intent mapping FAILED - No playbook selected for executable tasks "
                f"(task_domain={intent_result.task_domain.value if intent_result.task_domain else None}, "
                f"interaction_type={intent_result.interaction_type.value if intent_result.interaction_type else None})"
            )
            return None

        # Execute playbook
        execution_result = await playbook_service.execute_playbook(
            playbook_code=playbook_code,
            workspace_id=workspace_id,
            profile_id=profile_id,
            inputs={
                'message': message,
                'tasks': executable_tasks,
                'intent': {
                    'task_domain': intent_result.task_domain.value if intent_result.task_domain else None,
                    'interaction_type': intent_result.interaction_type.value if intent_result.interaction_type else None
                }
            },
            execution_mode=PlaybookExecutionMode.ASYNC
        )

        result = {
            "playbook_code": playbook_code,
            "execution_id": execution_result.execution_id,
            "tasks": executable_tasks
        }

        logger.info(f"[AgentMode] Playbook {playbook_code} executed successfully, execution_id={execution_result.execution_id}")
        return result

    except Exception as e:
        logger.warning(f"[AgentMode] Failed to analyze intent or execute playbook: {e}", exc_info=True)
        return None

