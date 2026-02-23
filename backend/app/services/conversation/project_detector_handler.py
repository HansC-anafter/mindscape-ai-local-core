"""
Project Detection Handler

Thin wrapper around project_creation_helper for the legacy routing path.
Delegates to the unified detect_and_create_project_if_needed() and adds
PM assignment only for newly created projects (not duplicates).
"""

import logging
from typing import Any, Optional

from backend.app.services.mindscape_store import MindscapeStore

logger = logging.getLogger(__name__)


async def detect_and_handle_project(
    store: MindscapeStore,
    workspace: Any,
    workspace_id: str,
    profile_id: str,
    message: str,
    project_id: Optional[str],
) -> Optional[str]:
    """
    Detect project intent and create if confidence is high enough.

    Delegates to the unified project_creation_helper and adds
    PM assignment only when a brand-new project is created.

    Args:
        store: MindscapeStore instance.
        workspace: Workspace object.
        workspace_id: Workspace ID.
        profile_id: User profile ID.
        message: User message text.
        project_id: Existing project ID (skip detection if set).

    Returns:
        Resolved project_id (may be the original, a new one, or None).
    """
    if project_id:
        return project_id

    if not workspace:
        return None

    logger.info("Starting project detection for message: %s...", message[:100])

    from backend.app.services.project.project_creation_helper import (
        detect_and_create_project_if_needed,
    )

    # Collect existing project IDs BEFORE detection so we can tell
    # whether the helper created a new project or returned a duplicate.
    from backend.app.services.project.project_manager import ProjectManager

    project_manager = ProjectManager(store)
    existing_projects = await project_manager.list_projects(
        workspace_id=workspace_id, state="open"
    )
    existing_ids = {p.id for p in existing_projects}

    resolved_project_id, _suggestion = await detect_and_create_project_if_needed(
        message=message,
        workspace_id=workspace_id,
        profile_id=profile_id,
        store=store,
        workspace=workspace,
        existing_project_id=None,
        create_on_medium_confidence=False,
    )

    if not resolved_project_id:
        return None

    # Only assign PM for genuinely new projects, not duplicates
    is_new_project = resolved_project_id not in existing_ids
    if is_new_project:
        await _assign_project_pm(
            store=store,
            workspace=workspace,
            workspace_id=workspace_id,
            project_id=resolved_project_id,
        )

    return resolved_project_id


async def _assign_project_pm(
    store: MindscapeStore,
    workspace: Any,
    workspace_id: str,
    project_id: str,
) -> None:
    """
    Assign PM roles to a newly created project.

    Args:
        store: MindscapeStore instance.
        workspace: Workspace object.
        workspace_id: Workspace ID.
        project_id: Project ID to assign PM to.
    """
    try:
        from backend.app.services.project.project_manager import ProjectManager
        from backend.app.services.project.project_assignment_agent import (
            ProjectAssignmentAgent,
        )

        project_manager = ProjectManager(store)
        project = await project_manager.get_project(
            project_id, workspace_id=workspace_id
        )
        if not project:
            return

        assignment_agent = ProjectAssignmentAgent()
        assignment = await assignment_agent.suggest_assignment(
            project=project, workspace=workspace
        )

        if assignment.suggested_human_owner:
            project.human_owner_user_id = assignment.suggested_human_owner.get(
                "user_id"
            )
        if assignment.suggested_ai_pm_id:
            project.ai_pm_id = assignment.suggested_ai_pm_id
        await project_manager.update_project(project)

        logger.info("Assigned PM for new project %s", project_id)
    except Exception as e:
        logger.warning("Failed to assign PM for project %s: %s", project_id, e)
