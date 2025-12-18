"""
IG Content Reuse Tool

Tool for managing content transformation and reuse across different IG formats.
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
from backend.app.services.ig_obsidian.content_reuse import ContentReuse

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
                "vault_path": {
                    "type": "string",
                    "description": "Path to Obsidian Vault"
                },
                "source_post_path": {
                    "type": "string",
                    "description": "Path to source post (relative to vault, for article_to_carousel)"
                },
                "carousel_posts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of carousel post paths (for carousel_to_reel)"
                },
                "source_reel_path": {
                    "type": "string",
                    "description": "Path to source reel post (relative to vault, for reel_to_stories)"
                },
                "target_folder": {
                    "type": "string",
                    "description": "Target folder for generated posts (relative to vault)"
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
            required=["action", "vault_path", "target_folder"]
        )

        metadata = ToolMetadata(
            name="ig_content_reuse_tool",
            description="Manage content transformation and reuse across different IG formats: long article to carousel, carousel to reel, reel to stories.",
            input_schema=input_schema,
            category=ToolCategory.DATA,
            danger_level=ToolDangerLevel.LOW,
            source_type=ToolSourceType.BUILTIN,
            provider="ig_obsidian"
        )
        super().__init__(metadata)

    async def execute(self, **kwargs) -> ToolExecutionResult:
        """
        Execute content reuse action

        Args:
            action: Action to perform
            vault_path: Path to Obsidian Vault
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
            vault_path = kwargs.get("vault_path")
            target_folder = kwargs.get("target_folder")

            if not all([vault_path, target_folder]):
                return ToolExecutionResult(
                    success=False,
                    error="vault_path and target_folder are required"
                )

            reuse = ContentReuse(vault_path)

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

