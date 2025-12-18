"""
IG Vault Structure Tool

Tool for managing Obsidian Vault structure for IG Post workflow.
Supports initialization, validation, and content scanning.
"""
import logging
from typing import Dict, Any, Optional
from pathlib import Path

from backend.app.services.tools.base import MindscapeTool
from backend.app.services.tools.schemas import (
    ToolMetadata,
    ToolExecutionResult,
    ToolDangerLevel,
    ToolSourceType,
    ToolInputSchema,
    ToolCategory
)
from backend.app.services.ig_obsidian.vault_structure import VaultStructureManager

logger = logging.getLogger(__name__)


class IGVaultStructureTool(MindscapeTool):
    """Tool for managing Obsidian Vault structure for IG Post workflow"""

    def __init__(self):
        input_schema = ToolInputSchema(
            type="object",
            properties={
                "vault_path": {
                    "type": "string",
                    "description": "Path to Obsidian Vault"
                },
                "action": {
                    "type": "string",
                    "enum": ["init", "validate", "scan"],
                    "description": "Action to perform: init=initialize structure, validate=validate structure, scan=scan content"
                },
                "create_missing": {
                    "type": "boolean",
                    "default": False,
                    "description": "Whether to create missing folders when validating"
                }
            },
            required=["vault_path", "action"]
        )

        metadata = ToolMetadata(
            name="ig_vault_structure_tool",
            description="Manage Obsidian Vault structure for IG Post workflow. Supports initialization, validation, and content scanning.",
            input_schema=input_schema,
            category=ToolCategory.DATA,
            danger_level=ToolDangerLevel.MEDIUM,
            source_type=ToolSourceType.BUILTIN,
            provider="ig_obsidian"
        )
        super().__init__(metadata)

    async def execute(self, **kwargs) -> ToolExecutionResult:
        """
        Execute Vault structure management action

        Args:
            vault_path: Path to Obsidian Vault
            action: Action to perform (init, validate, scan)
            create_missing: Whether to create missing folders (for validate action)

        Returns:
            ToolExecutionResult with action results
        """
        try:
            vault_path = kwargs.get("vault_path")
            action = kwargs.get("action")
            create_missing = kwargs.get("create_missing", False)

            if not vault_path:
                return ToolExecutionResult(
                    success=False,
                    error="vault_path is required"
                )

            if action not in ["init", "validate", "scan"]:
                return ToolExecutionResult(
                    success=False,
                    error=f"Invalid action: {action}. Must be one of: init, validate, scan"
                )

            manager = VaultStructureManager(vault_path)

            if action == "init":
                result = manager.init_structure(create_missing=True)
                return ToolExecutionResult(
                    success=True,
                    result={
                        "structure_status": result["structure_status"],
                        "created_folders": result["created_folders"],
                        "missing_folders": result["missing_folders"],
                        "is_valid": result["is_valid"]
                    }
                )

            elif action == "validate":
                result = manager.validate_structure(create_missing=create_missing)
                return ToolExecutionResult(
                    success=True,
                    result={
                        "is_valid": result["is_valid"],
                        "missing_folders": result["missing_folders"],
                        "structure_status": result["structure_status"],
                        "vault_path": result["vault_path"]
                    }
                )

            elif action == "scan":
                result = manager.scan_content()
                return ToolExecutionResult(
                    success=True,
                    result={
                        "content_index": result["content_index"],
                        "post_count": result["post_count"],
                        "series_count": result["series_count"],
                        "idea_count": result["idea_count"],
                        "vault_path": result["vault_path"]
                    }
                )

        except ValueError as e:
            logger.error(f"Vault structure tool validation error: {e}")
            return ToolExecutionResult(
                success=False,
                error=str(e)
            )
        except Exception as e:
            logger.error(f"Vault structure tool error: {e}", exc_info=True)
            return ToolExecutionResult(
                success=False,
                error=str(e)
            )


def create_ig_vault_structure_tool() -> IGVaultStructureTool:
    """
    Create IG Vault Structure Tool instance

    Returns:
        IGVaultStructureTool instance
    """
    return IGVaultStructureTool()


def create_ig_obsidian_tools() -> List[MindscapeTool]:
    """
    Create all IG + Obsidian integration tools

    Returns:
        List of IG + Obsidian MindscapeTool instances
    """
    from typing import List
    from backend.app.services.tools.base import MindscapeTool
    from backend.app.services.tools.ig_obsidian.ig_frontmatter_validator_tool import IGFrontmatterValidatorTool
    from backend.app.services.tools.ig_obsidian.ig_template_engine_tool import IGTemplateEngineTool

    return [
        IGVaultStructureTool(),
        IGFrontmatterValidatorTool(),
        IGTemplateEngineTool()
    ]

