"""
IG Series Manager Tool

Tool for managing IG Post series including creation, updates, querying,
and cross-referencing.
"""
import logging
from typing import Dict, Any, List, Optional

from backend.app.services.tools.base import MindscapeTool
from backend.app.services.tools.schemas import (
    ToolMetadata,
    ToolExecutionResult,
    ToolDangerLevel,
    ToolSourceType,
    ToolInputSchema,
    ToolCategory
)
import os
from capabilities.ig.services.series_manager import SeriesManager
from capabilities.ig.services.workspace_storage import WorkspaceStorage

logger = logging.getLogger(__name__)


class IGSeriesManagerTool(MindscapeTool):
    """Tool for managing IG Post series"""

    def __init__(self):
        input_schema = ToolInputSchema(
            type="object",
            properties={
                "action": {
                    "type": "string",
                    "enum": ["create", "add_post", "get", "list", "get_posts", "get_previous_next", "update_progress"],
                    "description": "Action to perform"
                },
                "workspace_id": {
                    "type": "string",
                    "description": "Workspace identifier (required if workspace_path not provided)"
                },
                "workspace_path": {
                    "type": "string",
                    "description": "Custom workspace path (optional, for backward compatibility)"
                },
                "series_code": {
                    "type": "string",
                    "description": "Series code (required for most actions)"
                },
                "series_name": {
                    "type": "string",
                    "description": "Series name (required for create action)"
                },
                "description": {
                    "type": "string",
                    "description": "Series description (optional)"
                },
                "total_posts": {
                    "type": "integer",
                    "description": "Total number of posts planned (optional)"
                },
                "post_path": {
                    "type": "string",
                    "description": "Post file path (relative to vault, required for add_post action)"
                },
                "post_slug": {
                    "type": "string",
                    "description": "Post slug (required for add_post action)"
                },
                "post_number": {
                    "type": "integer",
                    "description": "Post number in series (optional, auto-increment if not provided)"
                },
                "current_post_number": {
                    "type": "integer",
                    "description": "Current post number (required for get_previous_next action)"
                }
            },
            required=["action"]
        )

        metadata = ToolMetadata(
            name="ig_series_manager_tool",
            description="Manage IG Post series including creation, updates, querying, and cross-referencing. Supports series progress tracking and post navigation.",
            input_schema=input_schema,
            category=ToolCategory.DATA,
            danger_level=ToolDangerLevel.LOW,
            source_type=ToolSourceType.BUILTIN,
            provider="ig"
        )
        super().__init__(metadata)

    async def execute(self, **kwargs) -> ToolExecutionResult:
        """
        Execute series manager action

        Args:
            action: Action to perform
            workspace_id: Workspace identifier
            workspace_path: Optional custom workspace path
            series_code: Series code (for most actions)
            series_name: Series name (for create action)
            description: Series description (for create action)
            total_posts: Total posts planned (for create action)
            post_path: Post file path (for add_post action)
            post_slug: Post slug (for add_post action)
            post_number: Post number (for add_post action)
            current_post_number: Current post number (for get_previous_next action)

        Returns:
            ToolExecutionResult with action results
        """
        try:
            action = kwargs.get("action")
            workspace_id = kwargs.get("workspace_id")
            workspace_path = kwargs.get("workspace_path")

            # Initialize workspace storage
            capability_code = "ig"

            if workspace_path:
                if not workspace_id:
                    workspace_id = "default"
                # Check if we're in enterprise mode
                is_enterprise_mode = bool(os.getenv("TENANT_ID"))
                storage = WorkspaceStorage.from_workspace_path(
                    workspace_id,
                    capability_code,
                    workspace_path,
                    allow_custom_path=not is_enterprise_mode
                )
            elif workspace_id:
                storage = WorkspaceStorage(workspace_id, capability_code)
            else:
                return ToolExecutionResult(
                    success=False,
                    error="Either workspace_id or workspace_path is required"
                )

            manager = SeriesManager(storage)

            if action == "create":
                series_code = kwargs.get("series_code")
                series_name = kwargs.get("series_name")
                description = kwargs.get("description")
                total_posts = kwargs.get("total_posts")

                if not series_code or not series_name:
                    return ToolExecutionResult(
                        success=False,
                        error="series_code and series_name are required for create action"
                    )

                series = manager.create_series(
                    series_code=series_code,
                    series_name=series_name,
                    description=description,
                    total_posts=total_posts
                )

                return ToolExecutionResult(
                    success=True,
                    result={"series": series}
                )

            elif action == "add_post":
                series_code = kwargs.get("series_code")
                post_path = kwargs.get("post_path")
                post_slug = kwargs.get("post_slug")
                post_number = kwargs.get("post_number")

                if not all([series_code, post_path, post_slug]):
                    return ToolExecutionResult(
                        success=False,
                        error="series_code, post_path, and post_slug are required for add_post action"
                    )

                series = manager.add_post_to_series(
                    series_code=series_code,
                    post_path=post_path,
                    post_slug=post_slug,
                    post_number=post_number
                )

                return ToolExecutionResult(
                    success=True,
                    result={"series": series}
                )

            elif action == "get":
                series_code = kwargs.get("series_code")

                if not series_code:
                    return ToolExecutionResult(
                        success=False,
                        error="series_code is required for get action"
                    )

                series = manager.get_series(series_code)

                if not series:
                    return ToolExecutionResult(
                        success=False,
                        error=f"Series {series_code} not found"
                    )

                return ToolExecutionResult(
                    success=True,
                    result={"series": series}
                )

            elif action == "list":
                series_list = manager.list_series()

                return ToolExecutionResult(
                    success=True,
                    result={"series_list": series_list}
                )

            elif action == "get_posts":
                series_code = kwargs.get("series_code")

                if not series_code:
                    return ToolExecutionResult(
                        success=False,
                        error="series_code is required for get_posts action"
                    )

                posts = manager.get_series_posts(series_code)

                return ToolExecutionResult(
                    success=True,
                    result={"posts": posts}
                )

            elif action == "get_previous_next":
                series_code = kwargs.get("series_code")
                current_post_number = kwargs.get("current_post_number")

                if not all([series_code, current_post_number]):
                    return ToolExecutionResult(
                        success=False,
                        error="series_code and current_post_number are required for get_previous_next action"
                    )

                result = manager.get_previous_next_posts(series_code, current_post_number)

                return ToolExecutionResult(
                    success=True,
                    result=result
                )

            elif action == "update_progress":
                series_code = kwargs.get("series_code")

                if not series_code:
                    return ToolExecutionResult(
                        success=False,
                        error="series_code is required for update_progress action"
                    )

                series = manager.update_series_progress(series_code)

                return ToolExecutionResult(
                    success=True,
                    result={"series": series}
                )

            else:
                return ToolExecutionResult(
                    success=False,
                    error=f"Unknown action: {action}"
                )

        except Exception as e:
            logger.error(f"Series manager tool error: {e}", exc_info=True)
            return ToolExecutionResult(
                success=False,
                error=str(e)
            )
