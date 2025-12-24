"""
IG Content Checker Tool

Tool for checking IG Post content for compliance issues including medical/investment
claims, copyright, personal data, and brand tone.
"""
import logging
import os
from typing import Dict, Any, Optional

try:
    from backend.app.services.tools.base import MindscapeTool
    from backend.app.services.tools.schemas import (
        ToolMetadata,
        ToolExecutionResult,
        ToolDangerLevel,
        ToolSourceType,
        ToolInputSchema,
        ToolCategory
    )
except ImportError:
    # Fallback for cloud environment
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "mindscape-ai-local-core" / "backend"))
    from app.services.tools.base import MindscapeTool
    from app.services.tools.schemas import (
        ToolMetadata,
        ToolExecutionResult,
        ToolDangerLevel,
        ToolSourceType,
        ToolInputSchema,
        ToolCategory
    )

from capabilities.ig.services.workspace_storage import WorkspaceStorage
from capabilities.ig.services.content_checker import ContentChecker

logger = logging.getLogger(__name__)


class IGContentCheckerTool(MindscapeTool):
    """Tool for checking IG Post content for compliance issues"""

    def __init__(self):
        input_schema = ToolInputSchema(
            type="object",
            properties={
                "content": {
                    "type": "string",
                    "description": "Post content text to check (optional if post_path provided)"
                },
                "frontmatter": {
                    "type": "object",
                    "description": "Post frontmatter (optional)"
                },
                "workspace_id": {
                    "type": "string",
                    "description": "Workspace identifier (required if post_path provided)"
                },
                "workspace_path": {
                    "type": "string",
                    "description": "Custom workspace path (for backward compatibility/migration, not allowed in enterprise mode)"
                },
                "post_path": {
                    "type": "string",
                    "description": "Path to post Markdown file (relative to workspace or Obsidian-style, optional)"
                }
            },
            required=[]
        )

        metadata = ToolMetadata(
            name="ig_content_checker_tool",
            description="Check IG Post content for compliance issues including medical/investment claims, copyright, personal data, and brand tone. Supports reading from file or direct content input.",
            input_schema=input_schema,
            category=ToolCategory.DATA,
            danger_level=ToolDangerLevel.LOW,
            source_type=ToolSourceType.BUILTIN,
            provider="ig"
        )
        super().__init__(metadata)

    async def execute(self, **kwargs) -> ToolExecutionResult:
        """
        Execute content checking

        Args:
            content: Post content text (optional if post_path provided)
            frontmatter: Post frontmatter (optional)
            workspace_id: Workspace identifier (required if post_path provided)
            workspace_path: Custom workspace path (for backward compatibility)
            post_path: Path to post Markdown file (optional)

        Returns:
            ToolExecutionResult with content check results
        """
        try:
            content = kwargs.get("content")
            frontmatter = kwargs.get("frontmatter")
            workspace_id = kwargs.get("workspace_id")
            workspace_path = kwargs.get("workspace_path")
            post_path = kwargs.get("post_path")

            # Initialize storage if post_path provided
            storage = None
            if post_path:
                if not workspace_id and not workspace_path:
                    return ToolExecutionResult(
                        success=False,
                        error="Either workspace_id or workspace_path is required when post_path is provided"
                    )

                capability_code = "ig"
                tenant_id = os.getenv("TENANT_ID")

                if workspace_path:
                    allow_custom_path = not (tenant_id is not None)
                    storage = WorkspaceStorage.from_workspace_path(
                        workspace_id or "default",
                        capability_code,
                        workspace_path,
                        tenant_id=tenant_id,
                        allow_custom_path=allow_custom_path
                    )
                elif workspace_id:
                    storage = WorkspaceStorage(workspace_id, capability_code, tenant_id=tenant_id)

            checker = ContentChecker(storage)
            result = checker.check_content(
                content=content,
                frontmatter=frontmatter,
                post_path=post_path
            )

            return ToolExecutionResult(
                success=True,
                result=result
            )

        except Exception as e:
            logger.error(f"Content checker tool error: {e}", exc_info=True)
            return ToolExecutionResult(
                success=False,
                error=str(e)
            )

