"""
IG Asset Manager Tool

Tool for managing IG Post assets with naming validation, size checking,
and format validation.
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
from backend.app.services.ig_obsidian.asset_manager import AssetManager

logger = logging.getLogger(__name__)


class IGAssetManagerTool(MindscapeTool):
    """Tool for managing IG Post assets"""

    def __init__(self):
        input_schema = ToolInputSchema(
            type="object",
            properties={
                "action": {
                    "type": "string",
                    "enum": ["scan", "validate", "generate_list"],
                    "description": "Action to perform: scan=scan assets, validate=validate assets, generate_list=generate required asset list"
                },
                "post_folder": {
                    "type": "string",
                    "description": "Post folder path (relative to vault)"
                },
                "vault_path": {
                    "type": "string",
                    "description": "Path to Obsidian Vault"
                },
                "post_type": {
                    "type": "string",
                    "enum": ["post", "carousel", "reel", "story"],
                    "description": "Post type (required for validate and generate_list actions)"
                },
                "asset_list": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Asset list from scan (required for validate action)"
                }
            },
            required=["action", "post_folder", "vault_path"]
        )

        metadata = ToolMetadata(
            name="ig_asset_manager_tool",
            description="Manage IG Post assets with naming validation, size checking, and format validation. Supports post, carousel, reel, and story asset types.",
            input_schema=input_schema,
            category=ToolCategory.DATA,
            danger_level=ToolDangerLevel.LOW,
            source_type=ToolSourceType.BUILTIN,
            provider="ig_obsidian"
        )
        super().__init__(metadata)

    async def execute(self, **kwargs) -> ToolExecutionResult:
        """
        Execute asset manager action

        Args:
            action: Action to perform (scan, validate, generate_list)
            post_folder: Post folder path
            vault_path: Path to Obsidian Vault
            post_type: Post type (for validate and generate_list actions)
            asset_list: Asset list from scan (for validate action)

        Returns:
            ToolExecutionResult with action results
        """
        try:
            action = kwargs.get("action")
            post_folder = kwargs.get("post_folder")
            vault_path = kwargs.get("vault_path")
            post_type = kwargs.get("post_type")
            asset_list = kwargs.get("asset_list")

            if not post_folder or not vault_path:
                return ToolExecutionResult(
                    success=False,
                    error="post_folder and vault_path are required"
                )

            manager = AssetManager(vault_path)

            if action == "scan":
                result = manager.scan_assets(post_folder)

                return ToolExecutionResult(
                    success=True,
                    result={
                        "asset_list": result.get("asset_list", []),
                        "post_slug": result.get("post_slug"),
                        "assets_folder": result.get("assets_folder")
                    }
                )

            elif action == "validate":
                if not post_type:
                    return ToolExecutionResult(
                        success=False,
                        error="post_type is required for validate action"
                    )

                if not asset_list:
                    # Scan assets first if not provided
                    scan_result = manager.scan_assets(post_folder)
                    asset_list = scan_result.get("asset_list", [])

                result = manager.validate_assets(asset_list, post_type)

                return ToolExecutionResult(
                    success=True,
                    result={
                        "validation_results": result["validation_results"],
                        "missing_assets": result["missing_assets"],
                        "size_warnings": result["size_warnings"],
                        "spec_used": result["spec_used"]
                    }
                )

            elif action == "generate_list":
                if not post_type:
                    return ToolExecutionResult(
                        success=False,
                        error="post_type is required for generate_list action"
                    )

                result = manager.generate_asset_list(post_folder, post_type)

                return ToolExecutionResult(
                    success=True,
                    result=result
                )

        except Exception as e:
            logger.error(f"Asset manager tool error: {e}", exc_info=True)
            return ToolExecutionResult(
                success=False,
                error=str(e)
            )


# Tool creation is handled in ig_export_pack_generator_tool.py to avoid circular imports

