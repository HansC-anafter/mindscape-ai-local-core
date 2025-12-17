"""
Plan Preparer

Prepares execution plans by parsing ExecutionPlan, determining pack_id/playbook_code,
and building base inputs with project metadata.
"""

import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass

from ...models.workspace import ExecutionPlan, TaskPlan
from ...core.execution_context import ExecutionContext
from ...services.mindscape_store import MindscapeStore
from ...services.project.project_manager import ProjectManager

logger = logging.getLogger(__name__)


@dataclass
class PreparedPlan:
    """
    Prepared plan data structure

    Contains all information needed to execute a task plan.
    """

    playbook_code: str
    playbook_inputs: Dict[str, Any]
    project_meta: Optional[Dict[str, Any]] = None
    capability: bool = False
    pack_id: str = ""
    task_plan: Optional[TaskPlan] = None


class PlanPreparer:
    """
    Prepares execution plans for coordination

    Responsibilities:
    - Parse ExecutionPlan and extract task plans
    - Determine pack_id/playbook_code
    - Load project metadata (id, title, name) using ProjectManager
    - Build base inputs with project information
    """

    def __init__(self, store: MindscapeStore):
        """
        Initialize PlanPreparer

        Args:
            store: MindscapeStore instance for accessing project data
        """
        self.store = store
        self.project_manager = ProjectManager(store)

    async def prepare_plan(
        self,
        task_plan: TaskPlan,
        ctx: ExecutionContext,
        message_id: str,
        files: list[str],
        message: str,
        project_id: Optional[str] = None,
    ) -> PreparedPlan:
        """
        Prepare a task plan for execution

        Args:
            task_plan: Task plan to prepare
            ctx: Execution context
            message_id: Message/event ID
            files: List of file IDs
            message: User message
            project_id: Optional project ID

        Returns:
            PreparedPlan with playbook_code, inputs, and project metadata
        """
        pack_id = task_plan.pack_id

        # Load project metadata if project_id is provided
        project_meta = None
        if project_id:
            project_meta = await self._load_project_meta(project_id, ctx.workspace_id)

        # Build base inputs
        playbook_inputs = self._build_base_inputs(
            task_plan=task_plan,
            ctx=ctx,
            message_id=message_id,
            files=files,
            message=message,
            project_id=project_id,
            project_meta=project_meta,
        )

        # Determine playbook_code (default to pack_id, can be overridden by resolver)
        playbook_code = pack_id

        return PreparedPlan(
            playbook_code=playbook_code,
            playbook_inputs=playbook_inputs,
            project_meta=project_meta,
            capability=False,
            pack_id=pack_id,
            task_plan=task_plan,
        )

    async def _load_project_meta(
        self, project_id: str, workspace_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Load project metadata (id, title, name) using ProjectManager

        Args:
            project_id: Project ID to load
            workspace_id: Workspace ID

        Returns:
            Dict with project metadata or None if not found
        """
        try:
            project = await self.project_manager.get_project(
                project_id, workspace_id=workspace_id
            )

            if project:
                project_title = getattr(project, "title", None) or getattr(
                    project, "name", None
                )
                return {
                    "id": project_id,
                    "title": project_title,
                    "name": project_title,
                }

            logger.warning(
                f"Project {project_id} not found in ProjectManager, returning basic metadata"
            )
            return {"id": project_id, "title": None, "name": None}

        except Exception as e:
            logger.warning(f"Failed to load project metadata for {project_id}: {e}")
            return {"id": project_id, "title": None, "name": None}

    def _build_base_inputs(
        self,
        task_plan: TaskPlan,
        ctx: ExecutionContext,
        message_id: str,
        files: list[str],
        message: str,
        project_id: Optional[str],
        project_meta: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Build base inputs for playbook execution

        Args:
            task_plan: Task plan
            ctx: Execution context
            message_id: Message/event ID
            files: List of file IDs
            message: User message
            project_id: Optional project ID
            project_meta: Optional project metadata

        Returns:
            Dict with base inputs for playbook
        """
        inputs = {}

        # Copy task_plan params as base
        if task_plan.params:
            inputs.update(task_plan.params)

        # Add execution context
        inputs["workspace_id"] = ctx.workspace_id
        inputs["message_id"] = message_id
        inputs["files"] = files
        inputs["message"] = message

        # Add project information if available
        if project_id:
            inputs["project_id"] = project_id

            if project_meta:
                if project_meta.get("name"):
                    inputs["project_name"] = project_meta["name"]
                if project_meta.get("title"):
                    inputs["project_title"] = project_meta["title"]

        # Extract context from params if available
        if "context" in inputs:
            context = inputs["context"]
            if isinstance(context, dict):
                inputs.update(context)

        return inputs
