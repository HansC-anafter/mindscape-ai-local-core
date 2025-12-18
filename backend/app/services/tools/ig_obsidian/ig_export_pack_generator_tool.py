"""
IG Export Pack Generator Tool

Tool for generating complete export pack including post.md, hashtags.txt,
CTA variants, and checklist.
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
from backend.app.services.ig_obsidian.export_pack_generator import ExportPackGenerator

logger = logging.getLogger(__name__)


class IGExportPackGeneratorTool(MindscapeTool):
    """Tool for generating complete export pack for IG Post"""

    def __init__(self):
        input_schema = ToolInputSchema(
            type="object",
            properties={
                "post_folder": {
                    "type": "string",
                    "description": "Post folder path (relative to vault)"
                },
                "vault_path": {
                    "type": "string",
                    "description": "Path to Obsidian Vault"
                },
                "post_content": {
                    "type": "string",
                    "description": "Post content text"
                },
                "frontmatter": {
                    "type": "object",
                    "description": "Post frontmatter"
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
            required=["post_folder", "vault_path", "post_content", "frontmatter", "hashtags"]
        )

        metadata = ToolMetadata(
            name="ig_export_pack_generator_tool",
            description="Generate complete export pack for IG Post including post.md, hashtags.txt, CTA variants, and checklist.",
            input_schema=input_schema,
            category=ToolCategory.CONTENT,
            danger_level=ToolDangerLevel.LOW,
            source_type=ToolSourceType.BUILTIN,
            provider="ig_obsidian"
        )
        super().__init__(metadata)

    async def execute(self, **kwargs) -> ToolExecutionResult:
        """
        Execute export pack generation

        Args:
            post_folder: Post folder path
            vault_path: Path to Obsidian Vault
            post_content: Post content text
            frontmatter: Post frontmatter
            hashtags: List of hashtags
            cta_variants: List of CTA variants (optional)
            assets_list: List of assets (optional)

        Returns:
            ToolExecutionResult with export pack generation results
        """
        try:
            post_folder = kwargs.get("post_folder")
            vault_path = kwargs.get("vault_path")
            post_content = kwargs.get("post_content")
            frontmatter = kwargs.get("frontmatter")
            hashtags = kwargs.get("hashtags")
            cta_variants = kwargs.get("cta_variants")
            assets_list = kwargs.get("assets_list")

            if not all([post_folder, vault_path, post_content, frontmatter, hashtags]):
                return ToolExecutionResult(
                    success=False,
                    error="post_folder, vault_path, post_content, frontmatter, and hashtags are required"
                )

            generator = ExportPackGenerator(vault_path)
            result = generator.generate_export_pack(
                post_folder=post_folder,
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


# Tool creation is handled in ig_content_checker_tool.py to avoid circular imports

