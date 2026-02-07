"""
Unified Project Creation Helper
Centralized logic for project detection and creation across all modes
"""

import logging
from typing import Optional, Tuple
from backend.app.models.workspace import Workspace
from backend.app.models.project import ProjectSuggestion
from backend.app.services.project.project_manager import ProjectManager
from backend.app.services.project.project_detector import ProjectDetector
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.models.mindscape import EventActor, EventType

logger = logging.getLogger(__name__)

# Unified confidence thresholds
HIGH_CONFIDENCE_THRESHOLD = 0.8  # High confidence: create directly
LOW_CONFIDENCE_THRESHOLD = 0.5  # Low confidence: don't suggest


async def detect_and_create_project_if_needed(
    message: str,
    workspace_id: str,
    profile_id: str,
    store: MindscapeStore,
    workspace: Optional[Workspace] = None,
    existing_project_id: Optional[str] = None,
    create_on_medium_confidence: bool = False,
) -> Tuple[Optional[str], Optional[ProjectSuggestion]]:
    """
    Unified project detection and creation logic

    This function provides consistent project detection and creation across:
    - Workspace Chat mode (generator.py)
    - Execution mode (executor.py)
    - Conversation orchestrator (conversation_orchestrator.py)

    Args:
        message: User message
        workspace_id: Workspace ID
        profile_id: Profile ID
        store: MindscapeStore instance
        workspace: Optional workspace object (if None, will be fetched)
        existing_project_id: Optional existing project ID to use
        create_on_medium_confidence: If True, create project for medium confidence (0.5-0.8)
                                     If False, only create for high confidence (>=0.8)

    Returns:
        Tuple of (project_id, project_suggestion)
        - project_id: Project ID if created or found, None otherwise
        - project_suggestion: ProjectSuggestion if detected, None otherwise
    """
    # Use existing project if provided
    if existing_project_id:
        logger.debug(
            f"[ProjectCreation] Using existing project_id: {existing_project_id}"
        )
        return existing_project_id, None

    # Get workspace if not provided
    if not workspace:
        workspace = await store.get_workspace(workspace_id)
        if not workspace:
            logger.warning(f"[ProjectCreation] Workspace {workspace_id} not found")
            return None, None

    # [REFINED] Don't skip detection just because primary_project_id is set.
    # The user might want to start a NEW project item even if one is active.
    # We will pass the primary_project_id to the detector as context instead of returning early.
    project_id = workspace.primary_project_id
    if project_id:
        logger.debug(
            f"[ProjectCreation] Workspace has primary_project_id {project_id}, but checking for new project intent anyway."
        )

    # No existing project, detect if we should create one
    logger.info(f"[ProjectCreation] Checking if we need to create a project...")

    project_manager = ProjectManager(store)
    project_detector = ProjectDetector()

    # Get recent conversation context
    recent_events = store.events.get_events(
        profile_id=profile_id, workspace_id=workspace_id, limit=10
    )
    conversation_context = [
        {
            "role": "user" if e.actor == EventActor.USER else "assistant",
            "content": e.payload.get("message", "") if e.payload else "",
        }
        for e in recent_events
        if e.event_type == EventType.MESSAGE and e.payload
    ]

    # Load available playbooks to help detector suggest the right sequence
    available_playbooks = []
    try:
        from backend.app.services.playbook_service import PlaybookService

        playbook_service = PlaybookService(store=store)

        # Load all playbooks (system + capability + user) via unified interface
        locale = workspace.default_locale or "zh-TW"
        all_playbook_metadata = await playbook_service.list_playbooks(
            workspace_id=workspace_id, locale=locale, source=None  # Get all sources
        )

        for metadata in all_playbook_metadata:
            # Extract output_types from metadata
            output_types = getattr(metadata, "output_types", []) or []
            if isinstance(output_types, str):
                output_types = [output_types] if output_types else []

            available_playbooks.append(
                {
                    "playbook_code": metadata.playbook_code,
                    "name": metadata.name,
                    "description": metadata.description or "",
                    "tags": metadata.tags or [],
                    "output_type": output_types[0] if output_types else None,
                    "output_types": output_types,
                }
            )

        # Evidence Logging (Outside Loop)
        try:
            from datetime import datetime
            import os

            # Use absolute path for reliable logging
            log_path = os.path.join(os.getcwd(), "data/mindscape_evidence.log")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"\n==== DETECT EVIDENCE (Helper) {datetime.utcnow()} ====\n")
                f.write(f"Workspace: {workspace.id}\n")
                f.write(
                    f"Available Playbooks: {len(available_playbooks) if available_playbooks else 0}\n"
                )
                f.write(f"Prompt (Message): {message}\n")
                f.write("==========================================\n")
        except Exception:
            pass

        logger.debug(
            f"[ProjectCreation] Loaded {len(available_playbooks)} available playbooks for detection"
        )
    except Exception as e:
        logger.warning(
            f"[ProjectCreation] Failed to load available playbooks for detection: {e}"
        )

    # Detect project
    project_suggestion = await project_detector.detect(
        message=message,
        conversation_context=conversation_context,
        workspace=workspace,
        available_playbooks=available_playbooks,
    )

    if not project_suggestion or project_suggestion.mode != "project":
        logger.debug(
            f"[ProjectCreation] No project detected (mode={project_suggestion.mode if project_suggestion else None})"
        )
        return None, project_suggestion

    logger.info(
        f"[ProjectCreation] Project detection result: "
        f"type={project_suggestion.project_type}, "
        f"title={project_suggestion.project_title}, "
        f"confidence={project_suggestion.confidence}"
    )

    # Check for duplicate projects using LLM
    existing_projects = await project_manager.list_projects(
        workspace_id=workspace_id, state="open"
    )

    duplicate_project = None
    if existing_projects and project_suggestion.project_title:
        duplicate_project = await project_detector.check_duplicate(
            suggested_project=project_suggestion,
            existing_projects=existing_projects,
            workspace=workspace,
        )

    if duplicate_project:
        logger.info(
            f"[ProjectCreation] Using existing duplicate project: {duplicate_project.id}"
        )
        return duplicate_project.id, project_suggestion

    # Check confidence and create if appropriate
    confidence = project_suggestion.confidence or 0.5

    should_create = False
    if confidence >= HIGH_CONFIDENCE_THRESHOLD:
        should_create = True
        logger.info(
            f"[ProjectCreation] High confidence ({confidence:.2f}), creating project directly"
        )
    elif create_on_medium_confidence and confidence >= LOW_CONFIDENCE_THRESHOLD:
        should_create = True
        logger.info(
            f"[ProjectCreation] Medium confidence ({confidence:.2f}), creating project (create_on_medium_confidence=True)"
        )

    if should_create:
        # Ensure required fields are present
        if not project_suggestion.project_type or not project_suggestion.project_title:
            logger.warning(
                "[ProjectCreation] Project suggestion missing required fields, skipping creation"
            )
            return None, project_suggestion

        # Create project with validated playbook_sequence
        project = await project_manager.create_project(
            project_type=project_suggestion.project_type,
            title=project_suggestion.project_title,
            workspace_id=workspace_id,
            flow_id=None,  # Will be auto-generated
            initiator_user_id=profile_id,
            playbook_sequence=project_suggestion.playbook_sequence,
        )

        logger.info(
            f"[ProjectCreation] Created new project: {project.id} (confidence: {confidence:.2f})"
        )

        # Update workspace primary_project_id so frontend can display it
        if not workspace.primary_project_id:
            workspace.primary_project_id = project.id
            await store.update_workspace(workspace)
            logger.info(
                f"[ProjectCreation] Updated workspace primary_project_id to {project.id}"
            )

        return project.id, project_suggestion
    else:
        logger.debug(
            f"[ProjectCreation] Confidence ({confidence:.2f}) too low, not creating project"
        )
        return None, project_suggestion
