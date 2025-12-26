"""
Plan Preparer

Prepares execution plans by parsing ExecutionPlan, determining pack_id/playbook_code,
and building base inputs with project metadata.
"""

import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass

from ...models.workspace import ExecutionPlan, TaskPlan
from ...core.domain_context import LocalDomainContext
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
        ctx: LocalDomainContext,
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
        ctx: LocalDomainContext,
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

        # Auto-configure image handling for ig_post_generation playbook
        pack_id = task_plan.pack_id
        logger.info(f"[PlanPreparer] Preparing plan for pack_id={pack_id}, checking if ig_post_generation")
        if pack_id == 'ig_post_generation' or pack_id == 'ig':
            logger.info(f"[PlanPreparer] Detected ig_post_generation playbook, preparing image inputs")
            inputs = self._prepare_ig_post_inputs(inputs, files, ctx.workspace_id)
            logger.info(f"[PlanPreparer] After image preparation, inputs keys: {list(inputs.keys())}")
        else:
            logger.debug(f"[PlanPreparer] Pack {pack_id} is not ig_post_generation, skipping image preparation")

        return inputs

    def _prepare_ig_post_inputs(
        self,
        inputs: Dict[str, Any],
        files: list[str],
        workspace_id: str
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
                    if os.path.exists(file_id_or_path) or Path(file_id_or_path).is_absolute():
                        file_path = file_id_or_path
                    else:
                        # Assume it's a file_id, try to find the file in uploads directory
                        # Files are stored as {file_id}{ext} in workspace uploads dir
                        if workspace_uploads_dir.exists():
                            for uploaded_file in workspace_uploads_dir.glob(f"{file_id_or_path}*"):
                                if uploaded_file.is_file():
                                    file_path = str(uploaded_file.resolve())
                                    break

                    if file_path:
                        # Check if file is an image
                        image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg'}
                        if Path(file_path).suffix.lower() in image_extensions:
                            # Resolve absolute path
                            abs_path = Path(file_path).resolve()
                            if abs_path.exists():
                                image_files.append(str(abs_path))
                                logger.info(f"[IGPost] Found image file: {file_path}")
                except Exception as e:
                    logger.warning(f"[IGPost] Failed to process file {file_id_or_path}: {e}")

        # Configure image handling
        if image_files:
            # User provided images - use first image as reference
            inputs['reference_image_path'] = image_files[0]
            logger.info(f"[IGPost] Using user-provided image: {image_files[0]}")
        else:
            # No images provided - automatically enable Unsplash search
            # The playbook will handle the actual search execution
            inputs['enable_image_search'] = True
            logger.info(f"[IGPost] No images provided, enabling automatic Unsplash image search")

        return inputs
