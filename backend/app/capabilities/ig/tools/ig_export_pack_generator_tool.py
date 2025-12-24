"""
IG Export Pack Generator Tool

Tool for generating complete export pack including post.md, hashtags.txt,
CTA variants, and checklist.
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
from capabilities.ig.services.export_pack_generator import ExportPackGenerator

logger = logging.getLogger(__name__)


class IGExportPackGeneratorTool(MindscapeTool):
    """Tool for generating complete export pack for IG Post"""

    def __init__(self):
        input_schema = ToolInputSchema(
            type="object",
            properties={
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
                    "description": "Post file path (relative to workspace or Obsidian-style, optional if post_content provided)"
                },
                "post_content": {
                    "type": "string",
                    "description": "Post content text (optional if post_path provided)"
                },
                "frontmatter": {
                    "type": "object",
                    "description": "Post frontmatter (optional if post_path provided)"
                },
                "hashtags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of hashtags"
                },
                "cta_variants": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of CTA variants (optional)"
                },
                "assets_list": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "List of assets (optional)"
                }
            },
            required=[]
        )

        metadata = ToolMetadata(
            name="ig_export_pack_generator_tool",
            description="Generate complete export pack for IG Post including post.md, hashtags.txt, CTA variants, and checklist.",
            input_schema=input_schema,
            category=ToolCategory.CONTENT,
            danger_level=ToolDangerLevel.LOW,
            source_type=ToolSourceType.BUILTIN,
            provider="ig"
        )
        super().__init__(metadata)

    async def execute(self, **kwargs) -> ToolExecutionResult:
        """
        Execute export pack generation

        Args:
            workspace_id: Workspace identifier
            workspace_path: Custom workspace path (for backward compatibility)
            post_path: Post file path (optional if post_content provided)
            post_content: Post content text (optional if post_path provided)
            frontmatter: Post frontmatter (optional if post_path provided)
            hashtags: List of hashtags
            cta_variants: List of CTA variants (optional)
            assets_list: List of assets (optional)

        Returns:
            ToolExecutionResult with export pack generation results
        """
        try:
            workspace_id = kwargs.get("workspace_id")
            workspace_path = kwargs.get("workspace_path")
            post_path = kwargs.get("post_path")
            post_content = kwargs.get("post_content")
            frontmatter = kwargs.get("frontmatter")
            hashtags = kwargs.get("hashtags", [])
            cta_variants = kwargs.get("cta_variants")
            assets_list = kwargs.get("assets_list")

            # Initialize storage if post_path provided or workspace_id provided
            storage = None
            if post_path or workspace_id:
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

            if not post_content and not post_path:
                return ToolExecutionResult(
                    success=False,
                    error="Either post_path or (post_content + frontmatter) must be provided"
                )

            if not hashtags:
                return ToolExecutionResult(
                    success=False,
                    error="hashtags is required"
                )

            if not storage:
                return ToolExecutionResult(
                    success=False,
                    error="WorkspaceStorage is required for export pack generation"
                )

            generator = ExportPackGenerator(storage)
            result = generator.generate_export_pack(
                post_path=post_path,
                post_content=post_content,
                frontmatter=frontmatter,
                hashtags=hashtags,
                cta_variants=cta_variants,
                assets_list=assets_list
            )

            return ToolExecutionResult(
                success=True,
                result=result
            )

        except Exception as e:
            logger.error(f"Export pack generator tool error: {e}", exc_info=True)
            return ToolExecutionResult(
                success=False,
                error=str(e)
            )

