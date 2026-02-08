"""
Playbook execution logic for execution and hybrid modes
"""

import logging
from typing import Dict, Any, Optional, List

from backend.app.services.intent_analyzer import IntentPipeline
from backend.app.services.playbook_service import (
    PlaybookService,
    ExecutionMode as PlaybookExecutionMode,
)
from backend.app.shared.intent_playbook_mapping import select_playbook_for_intent
from backend.app.services.mindscape_store import MindscapeStore

logger = logging.getLogger(__name__)


async def execute_playbook_for_execution_mode(
    message: str,
    workspace_id: str,
    profile_id: str,
    profile: Optional[Any],
    store: MindscapeStore,
    project_id: Optional[str] = None,
    files: Optional[List[str]] = None,
    model_name: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Execute playbook directly for execution mode using intent analysis

    If no project_id is provided, will detect if a project should be created
    (same logic as workspace chat mode) to support multi-step workflows and progress tracking.

    Args:
        message: User message
        workspace_id: Workspace ID
        profile_id: Profile ID
        profile: Profile object (optional)
        store: MindscapeStore instance
        project_id: Optional project ID (if None, will detect if project should be created)

    Returns:
        Execution result dict if playbook was executed, None otherwise
    """
    try:
        logger.info(
            f"[ExecutionMode] Starting direct playbook.run flow for execution mode"
        )

        # Check if we need to create a Project using unified helper
        from backend.app.services.project.project_creation_helper import (
            detect_and_create_project_if_needed,
        )

        project_id, project_suggestion = await detect_and_create_project_if_needed(
            message=message,
            workspace_id=workspace_id,
            profile_id=profile_id,
            store=store,
            workspace=None,  # Will be fetched inside helper
            existing_project_id=project_id,  # Use provided project_id if available
            create_on_medium_confidence=False,  # Only create on high confidence in execution mode
        )

        if project_id:
            logger.info(f"[ExecutionMode] Using project: {project_id}")

        # Initialize services
        playbook_service = PlaybookService(store=store)
        intent_pipeline = IntentPipeline(
            llm_provider=None,  # Will use default
            store=store,
            playbook_service=playbook_service,
        )

        # If we have a project_id, check if we should use flow's playbook_sequence
        if project_id:
            from backend.app.services.project.project_manager import ProjectManager

            project_manager = ProjectManager(store)
            project = await project_manager.get_project(project_id)

            if project and project.flow_id:
                from backend.app.services.stores.playbook_flows_store import (
                    PlaybookFlowsStore,
                )

                flows_store = PlaybookFlowsStore(store.db_path)
                flow = flows_store.get_flow(project.flow_id)

                if flow:
                    flow_def = (
                        flow.flow_definition
                        if isinstance(flow.flow_definition, dict)
                        else {}
                    )
                    playbook_sequence = flow_def.get("playbook_sequence", [])

                    if playbook_sequence and len(playbook_sequence) > 0:
                        logger.info(
                            f"[ExecutionMode] Found flow with {len(playbook_sequence)} playbooks, executing first playbook: {playbook_sequence[0]}"
                        )
                        # Use first playbook from sequence for execution
                        # Note: Full sequence execution would be handled by execution coordinator
                        playbook_code = playbook_sequence[0]

                        # Execute first playbook from flow
                        try:
                            execution_result = await playbook_service.execute_playbook(
                                playbook_code=playbook_code,
                                workspace_id=workspace_id,
                                profile_id=profile_id,
                                inputs={
                                    "message": message,
                                    "project_id": project_id,
                                    "intent": {},
                                },
                                execution_mode=PlaybookExecutionMode.ASYNC,
                            )

                            result = {
                                "status": "executed",
                                "playbook_code": playbook_code,
                                "execution_id": execution_result.execution_id,
                                "execution_mode": "flow_based_execution",
                                "project_id": project_id,
                                "flow_id": project.flow_id,
                                "playbook_sequence": playbook_sequence,
                                "current_index": 0,
                            }

                            logger.info(
                                f"[ExecutionMode] Playbook {playbook_code} executed from flow, execution_id={execution_result.execution_id}"
                            )
                            return result

                        except Exception as exec_error:
                            logger.warning(
                                f"[ExecutionMode] Failed to execute playbook {playbook_code} from flow: {exec_error}",
                                exc_info=True,
                            )
                            # Fall through to single playbook execution below

        # If we have a project_id and flow, use flow's playbook_sequence (already handled above)
        # Otherwise, fall back to single playbook execution via intent analysis

        # Analyze intent
        intent_result = await intent_pipeline.analyze(
            user_input=message,
            profile_id=profile_id,
            workspace_id=workspace_id,
            profile=profile,
        )

        logger.info(
            f"[ExecutionMode] Intent analysis result: "
            f"task_domain={intent_result.task_domain.value if intent_result.task_domain else None}, "
            f"interaction_type={intent_result.interaction_type.value if intent_result.interaction_type else None}"
        )

        # Select playbook
        logger.info(
            f"[ExecutionMode] Attempting intent → playbook mapping for user input: {message[:100]}"
        )
        playbook_code = await select_playbook_for_intent(
            intent_result, workspace_id, playbook_service
        )

        if playbook_code:
            logger.info(
                f"[ExecutionMode] Intent mapping SUCCESS - Selected playbook: {playbook_code} "
                f"for task_domain={intent_result.task_domain.value if intent_result.task_domain else None}"
            )

            # Prepare inputs
            inputs = {
                "message": message,
                "project_id": project_id,  # Pass project_id (may be None or newly created)
                "intent": {
                    "task_domain": (
                        intent_result.task_domain.value
                        if intent_result.task_domain
                        else None
                    ),
                    "interaction_type": (
                        intent_result.interaction_type.value
                        if intent_result.interaction_type
                        else None
                    ),
                },
            }

            # Auto-configure image handling for ig_post_generation playbook
            if playbook_code == "ig_post_generation":
                inputs = await _prepare_ig_post_inputs(
                    inputs, files, workspace_id, store
                )

            # Execute playbook
            try:
                execution_result = await playbook_service.execute_playbook(
                    playbook_code=playbook_code,
                    workspace_id=workspace_id,
                    profile_id=profile_id,
                    inputs=inputs,
                    execution_mode=PlaybookExecutionMode.ASYNC,
                )

                result = {
                    "status": "executed",
                    "playbook_code": playbook_code,
                    "execution_id": execution_result.execution_id,
                    "execution_mode": "direct_playbook_run",
                }

                # Include project_id if available
                if project_id:
                    result["project_id"] = project_id

                logger.info(
                    f"[ExecutionMode] Playbook {playbook_code} executed directly, execution_id={execution_result.execution_id}"
                )
                return result

            except Exception as exec_error:
                logger.warning(
                    f"[ExecutionMode] Failed to execute playbook {playbook_code}: {exec_error}",
                    exc_info=True,
                )
                return None
        else:
            logger.warning(
                f"[ExecutionMode] Intent mapping FAILED - No playbook selected for "
                f"task_domain={intent_result.task_domain.value if intent_result.task_domain else None}, "
                f"interaction_type={intent_result.interaction_type.value if intent_result.interaction_type else None}"
            )
            logger.info(
                f"[ExecutionMode] No playbook selected, falling back to LLM generation"
            )
            return None

    except Exception as e:
        logger.warning(
            f"[ExecutionMode] Failed in direct playbook.run flow: {e}", exc_info=True
        )
        return None


async def execute_playbook_for_hybrid_mode(
    message: str,
    executable_tasks: List[str],
    workspace_id: str,
    profile_id: str,
    profile: Optional[Any],
    store: MindscapeStore,
    files: Optional[List[str]] = None,
    model_name: Optional[str] = None,
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
            playbook_service=playbook_service,
        )

        # Analyze the first executable task (or combine all tasks)
        task_text = executable_tasks[0] if executable_tasks else message

        # [FIX] Check for explicit playbook code in task text to bypass redundant/flaky intent analysis
        # Pattern matches: "(using ig_analyze_following)", "[playbook: ig_analyze_following]", "using ig_analyze_following playbook"
        import re

        explicit_playbook_match = re.search(
            r"(?:using|playbook:|playbook)\s+[`'\"]?([a-z0-9_]+)[`'\"]?(?:\s+playbook)?",
            task_text,
            re.IGNORECASE,
        )

        playbook_code = None
        intent_result = None

        if explicit_playbook_match:
            candidate_code = explicit_playbook_match.group(1).lower()
            # Verify if this playbook actually exists
            if playbook_service.get_playbook(candidate_code):
                playbook_code = candidate_code
                logger.info(
                    f"[AgentMode] Explicit playbook code found in task: {playbook_code}. Bypassing intent analysis."
                )

                # Create a dummy intent result for compatibility
                from backend.app.services.intent_analyzer import (
                    IntentResult,
                    TaskDomain,
                    InteractionType,
                )

                intent_result = IntentResult(
                    task_domain=TaskDomain.GENERAL,  # Default
                    interaction_type=InteractionType.EXECUTE_PLAYBOOK,
                    confidence=1.0,
                    reasoning="Explicit playbook requested by Agent",
                )
            else:
                logger.warning(
                    f"[AgentMode] Explicit playbook code '{candidate_code}' found but not registered. Falling back to intent analysis."
                )

        if not playbook_code:
            # Analyze intent from ORIGINAL user message (not LLM-generated task text)
            # This is architecturally correct: intent should be derived from user's request
            intent_result = await intent_pipeline.analyze(
                user_input=message,  # Use original user message, not task_text
                profile_id=profile_id,
                workspace_id=workspace_id,
                profile=profile,
                model_name=model_name,
            )

        # Select playbook based on intent
        logger.info(
            f"[AgentMode] Attempting intent → playbook mapping for executable tasks: "
            f"{executable_tasks[:3] if executable_tasks else 'N/A'}"
        )
        playbook_code = await select_playbook_for_intent(
            intent_result, workspace_id, playbook_service
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

        # Prepare inputs
        inputs = {
            "message": message,
            "tasks": executable_tasks,
            "intent": {
                "task_domain": (
                    intent_result.task_domain.value
                    if intent_result.task_domain
                    else None
                ),
                "interaction_type": (
                    intent_result.interaction_type.value
                    if intent_result.interaction_type
                    else None
                ),
            },
        }

        # Auto-configure image handling for ig_post_generation playbook
        if playbook_code == "ig_post_generation":
            inputs = await _prepare_ig_post_inputs(inputs, files, workspace_id, store)

        # Execute playbook
        execution_result = await playbook_service.execute_playbook(
            playbook_code=playbook_code,
            workspace_id=workspace_id,
            profile_id=profile_id,
            inputs=inputs,
            execution_mode=PlaybookExecutionMode.ASYNC,
        )

        result = {
            "playbook_code": playbook_code,
            "execution_id": execution_result.execution_id,
            "tasks": executable_tasks,
        }

        logger.info(
            f"[AgentMode] Playbook {playbook_code} executed successfully, execution_id={execution_result.execution_id}"
        )
        return result

    except Exception as e:
        logger.warning(
            f"[AgentMode] Failed to analyze intent or execute playbook: {e}",
            exc_info=True,
        )
        return None


async def _prepare_ig_post_inputs(
    inputs: Dict[str, Any],
    files: Optional[List[str]],
    workspace_id: str,
    store: MindscapeStore,
) -> Dict[str, Any]:
    """
    Prepare inputs for ig_post_generation playbook with automatic image handling

    Logic:
    1. If user provided image files, use them as reference_image_path
    2. If no images provided, automatically enable Unsplash image search

    Args:
        inputs: Base inputs dict
        files: List of uploaded file IDs/paths
        workspace_id: Workspace ID
        store: MindscapeStore instance

    Returns:
        Updated inputs dict with image configuration
    """
    import os
    from pathlib import Path

    # Check for image files
    image_files = []
    if files:
        uploads_dir = os.getenv("UPLOADS_DIR", "data/uploads")
        workspace_uploads_dir = Path(uploads_dir) / workspace_id

        for file_id_or_path in files:
            try:
                file_path = None

                # If it's already a path, use it directly
                if (
                    os.path.exists(file_id_or_path)
                    or Path(file_id_or_path).is_absolute()
                ):
                    file_path = file_id_or_path
                else:
                    # Assume it's a file_id, try to find the file in uploads directory
                    # Files are stored as {file_id}{ext} in workspace uploads dir
                    if workspace_uploads_dir.exists():
                        for uploaded_file in workspace_uploads_dir.glob(
                            f"{file_id_or_path}*"
                        ):
                            if uploaded_file.is_file():
                                file_path = str(uploaded_file.resolve())
                                break

                if file_path:
                    # Check if file is an image
                    image_extensions = {
                        ".jpg",
                        ".jpeg",
                        ".png",
                        ".gif",
                        ".webp",
                        ".bmp",
                        ".svg",
                    }
                    if Path(file_path).suffix.lower() in image_extensions:
                        # Resolve absolute path
                        abs_path = Path(file_path).resolve()
                        if abs_path.exists():
                            image_files.append(str(abs_path))
                            logger.info(f"[IGPost] Found image file: {file_path}")
            except Exception as e:
                logger.warning(
                    f"[IGPost] Failed to process file {file_id_or_path}: {e}"
                )

    # Configure image handling
    if image_files:
        # User provided images - use first image as reference
        inputs["reference_image_path"] = image_files[0]
        logger.info(f"[IGPost] Using user-provided image: {image_files[0]}")
    else:
        # No images provided - automatically enable Unsplash search
        inputs["enable_image_search"] = True
        logger.info(
            f"[IGPost] No images provided, enabling automatic Unsplash image search"
        )

    return inputs
