"""IG Post tools - MindscapeTool wrappers for IG Post functionality."""
import logging
from typing import Dict, Any, Optional, List
from backend.app.services.tools.base import MindscapeTool
from backend.app.services.tools.schemas import (
    ToolMetadata,
    ToolExecutionResult,
    ToolDangerLevel,
    ToolSourceType,
    ToolInputSchema,
    ToolCategory
)
from backend.app.services.tools.ig_post.ig_post_style_analyzer import ig_post_style_analyzer

logger = logging.getLogger(__name__)


class IGPostStyleAnalyzerTool(MindscapeTool):
    """Tool for analyzing Instagram post visual style from reference images."""

    def __init__(self):
        input_schema = ToolInputSchema(
            type="object",
            properties={
                "reference_image_path": {
                    "type": "string",
                    "description": "Path to reference image file (local file path)"
                },
                "reference_image_url": {
                    "type": "string",
                    "description": "URL to reference image (will be downloaded to temp file)"
                },
                "include_mood": {
                    "type": "boolean",
                    "description": "Whether to include mood and narrative analysis",
                    "default": True
                }
            },
            required=[]
        )

        metadata = ToolMetadata(
            name="ig_post_style_analyzer",
            description="Analyze Instagram post style from reference image and generate design recommendations. Supports both local file paths and image URLs.",
            input_schema=input_schema,
            category=ToolCategory.ANALYSIS,
            danger_level=ToolDangerLevel.LOW,
            source_type=ToolSourceType.BUILTIN,
            provider="ig_post"
        )
        super().__init__(metadata)

    async def execute(self, **kwargs) -> ToolExecutionResult:
        """
        Execute IG Post style analysis.

        Args:
            reference_image_path: Path to reference image file (local)
            reference_image_url: URL to reference image (will be downloaded)
            include_mood: Whether to include mood analysis (default: True)

        Returns:
            ToolExecutionResult with analysis results
        """
        try:
            reference_image_path = kwargs.get("reference_image_path")
            reference_image_url = kwargs.get("reference_image_url")
            include_mood = kwargs.get("include_mood", True)

            if not reference_image_path and not reference_image_url:
                return ToolExecutionResult(
                    success=False,
                    error="Either reference_image_path or reference_image_url must be provided"
                )

            result = await ig_post_style_analyzer(
                reference_image_path=reference_image_path,
                reference_image_url=reference_image_url,
                include_mood=include_mood
            )

            return ToolExecutionResult(
                success=True,
                result=result
            )

        except Exception as e:
            logger.error(f"IG Post style analyzer error: {e}", exc_info=True)
            return ToolExecutionResult(
                success=False,
                error=str(e)
            )


from capabilities.ig.tools.ig_batch_pin_tool import ig_batch_pin_tool


class IGBatchPinTool(MindscapeTool):
    """Tool for auto-scrolling an IG account and batch pinning grid posts."""

    def __init__(self):
        input_schema = ToolInputSchema(
            type="object",
            properties={
                "workspace_id": {
                    "type": "string",
                    "description": "Workspace ID"
                },
                "target_handle": {
                    "type": "string",
                    "description": "Target Instagram Handle"
                },
                "target_count": {
                    "type": "integer",
                    "description": "Number of posts to fetch",
                    "default": 100
                }
            },
            required=["workspace_id", "target_handle", "target_count"]
        )

        metadata = ToolMetadata(
            name="ig_batch_pin_tool",
            description="Scroll down an Instagram account and batch pin posts to references.",
            input_schema=input_schema,
            category=ToolCategory.ACTION,
            danger_level=ToolDangerLevel.MEDIUM,
            source_type=ToolSourceType.BUILTIN,
            provider="ig"
        )
        super().__init__(metadata)

    async def execute(self, **kwargs) -> ToolExecutionResult:
        workspace_id = kwargs.get("workspace_id")
        target_handle = kwargs.get("target_handle")
        target_count = kwargs.get("target_count", 100)

        if not workspace_id or not target_handle:
            return ToolExecutionResult(
                success=False,
                error="workspace_id and target_handle are required"
            )

        try:
            result = await ig_batch_pin_tool(
                workspace_id=workspace_id,
                target_handle=target_handle,
                target_count=target_count
            )
            return ToolExecutionResult(
                success=(result.get("status") == "success" or result.get("status") == "warning"),
                result=result,
                error=result.get("error") if result.get("status") == "error" else None
            )
        except Exception as e:
            logger.error(f"IG Batch Pin Tool error: {e}", exc_info=True)
            return ToolExecutionResult(
                success=False,
                error=str(e)
            )


def create_ig_post_tools() -> List[MindscapeTool]:
    """
    Create all IG Post tools.

    Returns:
        List of IG Post MindscapeTool instances
    """
    return [
        IGPostStyleAnalyzerTool(),
        IGBatchPinTool()
    ]

