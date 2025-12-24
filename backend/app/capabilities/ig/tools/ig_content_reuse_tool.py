"""
IG Content Reuse Tool

Tool for managing content transformation and reuse across different IG formats.
"""
import logging
import os
from typing import Dict, Any, List, Optional

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
from capabilities.ig.services.content_reuse import ContentReuse

logger = logging.getLogger(__name__)


class IGContentReuseTool(MindscapeTool):
    """Tool for managing content transformation and reuse"""

    def __init__(self):
        input_schema = ToolInputSchema(
            type="object",
            properties={
                "action": {
                    "type": "string",
                    "enum": ["article_to_carousel", "carousel_to_reel", "reel_to_stories"],
                    "description": "Action to perform"
                },
                "workspace_id": {
                    "type": "string",
                    "description": "Workspace identifier"
                },
                "workspace_path": {
                    "type": "string",
                    "description": "Custom workspace path (for backward compatibility/migration, not allowed in enterprise mode)"
                },
                "source_post_path": {
                    "type": "string",
                    "description": "Path to source post (relative to workspace or Obsidian-style, for article_to_carousel)"
                },
                "carousel_posts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of carousel post paths (for carousel_to_reel)"
                },
                "source_reel_path": {
                    "type": "string",
                    "description": "Path to source reel post (relative to workspace or Obsidian-style, for reel_to_stories)"
                },
                "target_folder": {
                    "type": "string",
                    "description": "Target folder for generated posts"
                },
                "carousel_slides": {
                    "type": "integer",
                    "description": "Number of carousel slides (default: 7)"
                },
                "slide_structure": {
                    "type": "object",
                    "description": "Custom slide structure configuration (optional)"
                },
                "reel_duration": {
                    "type": "integer",
                    "description": "Reel duration in seconds (optional)"
                },
                "story_count": {
                    "type": "integer",
                    "description": "Number of stories to create (default: 3)"
                }
            },
            required=["action", "target_folder"]
        )

        metadata = ToolMetadata(
            name="ig_content_reuse_tool",
            description="Manage content transformation and reuse across different IG formats: long article to carousel, carousel to reel, reel to stories.",
            input_schema=input_schema,
            category=ToolCategory.DATA,
            danger_level=ToolDangerLevel.LOW,
            source_type=ToolSourceType.BUILTIN,
            provider="ig"
        )
        super().__init__(metadata)

    async def execute(self, **kwargs) -> ToolExecutionResult:
        """
        Execute content reuse action

        Args:
            action: Action to perform
            workspace_id: Workspace identifier
            workspace_path: Custom workspace path (for backward compatibility)
            source_post_path: Source post path (for article_to_carousel)
            carousel_posts: List of carousel post paths (for carousel_to_reel)
            source_reel_path: Source reel path (for reel_to_stories)
            target_folder: Target folder for generated posts
            carousel_slides: Number of carousel slides
            slide_structure: Custom slide structure
            reel_duration: Reel duration
            story_count: Number of stories

        Returns:
            ToolExecutionResult with action results
        """
        try:
            action = kwargs.get("action")
            workspace_id = kwargs.get("workspace_id")
            workspace_path = kwargs.get("workspace_path")
            target_folder = kwargs.get("target_folder")

            if not target_folder:
                return ToolExecutionResult(
                    success=False,
                    error="target_folder is required"
                )

            if not workspace_id and not workspace_path:
                return ToolExecutionResult(
                    success=False,
                    error="Either workspace_id or workspace_path is required"
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
            else:
                return ToolExecutionResult(
                    success=False,
                    error="Either workspace_id or workspace_path is required"
                )

            reuse = ContentReuse(storage)

            if action == "article_to_carousel":
                source_post_path = kwargs.get("source_post_path")
                carousel_slides = kwargs.get("carousel_slides", 7)
                slide_structure = kwargs.get("slide_structure")

                if not source_post_path:
                    return ToolExecutionResult(
                        success=False,
                        error="source_post_path is required for article_to_carousel action"
                    )

                result = reuse.article_to_carousel(
                    source_post_path=source_post_path,
                    target_folder=target_folder,
                    carousel_slides=carousel_slides,
                    slide_structure=slide_structure
                )

                return ToolExecutionResult(
                    success=True,
                    result=result
                )

            elif action == "carousel_to_reel":
                carousel_posts = kwargs.get("carousel_posts")
                reel_duration = kwargs.get("reel_duration")

                if not carousel_posts:
                    return ToolExecutionResult(
                        success=False,
                        error="carousel_posts is required for carousel_to_reel action"
                    )

                result = reuse.carousel_to_reel(
                    carousel_posts=carousel_posts,
                    target_folder=target_folder,
                    reel_duration=reel_duration
                )

                return ToolExecutionResult(
                    success=True,
                    result=result
                )

            elif action == "reel_to_stories":
                source_reel_path = kwargs.get("source_reel_path")
                story_count = kwargs.get("story_count", 3)

                if not source_reel_path:
                    return ToolExecutionResult(
                        success=False,
                        error="source_reel_path is required for reel_to_stories action"
                    )

                result = reuse.reel_to_stories(
                    source_reel_path=source_reel_path,
                    target_folder=target_folder,
                    story_count=story_count
                )

                return ToolExecutionResult(
                    success=True,
                    result=result
                )

            else:
                return ToolExecutionResult(
                    success=False,
                    error=f"Unknown action: {action}"
                )

        except Exception as e:
            logger.error(f"Content reuse tool error: {e}", exc_info=True)
            return ToolExecutionResult(
                success=False,
                error=str(e)
            )

