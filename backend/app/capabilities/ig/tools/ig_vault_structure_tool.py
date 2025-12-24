"""
IG Workspace Structure Tool

Tool for managing workspace structure for IG Post workflow.
Supports initialization, validation, and content scanning.
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
from capabilities.ig.services.vault_structure import WorkspaceStructureManager

logger = logging.getLogger(__name__)


class IGWorkspaceStructureTool(MindscapeTool):
    """Tool for managing workspace structure for IG Post workflow"""

    def __init__(self):
        input_schema = ToolInputSchema(
            type="object",
            properties={
                "workspace_id": {
                    "type": "string",
                    "description": "Workspace identifier"
                },
                "workspace_path": {
                    "type": "string",
                    "description": "Custom workspace path (for backward compatibility/migration, not allowed in enterprise mode)"
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
            required=["action"]
        )

        metadata = ToolMetadata(
            name="ig_vault_structure_tool",
            description="Manage workspace structure for IG Post workflow. Supports initialization, validation, and content scanning.",
            input_schema=input_schema,
            category=ToolCategory.DATA,
            danger_level=ToolDangerLevel.MEDIUM,
            source_type=ToolSourceType.BUILTIN,
            provider="ig"
        )
        super().__init__(metadata)

    async def execute(self, **kwargs) -> ToolExecutionResult:
        """
        Execute workspace structure management action

        Args:
            workspace_id: Workspace identifier
            workspace_path: Custom workspace path (for backward compatibility)
            action: Action to perform (init, validate, scan)
            create_missing: Whether to create missing folders (for validate action)

        Returns:
            ToolExecutionResult with action results
        """
        try:
            workspace_id = kwargs.get("workspace_id")
            workspace_path = kwargs.get("workspace_path")
            action = kwargs.get("action")
            create_missing = kwargs.get("create_missing", False)

            if not workspace_id and not workspace_path:
                return ToolExecutionResult(
                    success=False,
                    error="Either workspace_id or workspace_path is required"
                )

            if action not in ["init", "validate", "scan"]:
                return ToolExecutionResult(
                    success=False,
                    error=f"Invalid action: {action}. Must be one of: init, validate, scan"
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

            manager = WorkspaceStructureManager(storage)

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
                        "workspace_root": result["workspace_root"]
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
                        "workspace_root": result["workspace_root"]
                    }
                )

        except ValueError as e:
            logger.error(f"Workspace structure tool validation error: {e}")
            return ToolExecutionResult(
                success=False,
                error=str(e)
            )
        except Exception as e:
            logger.error(f"Workspace structure tool error: {e}", exc_info=True)
            return ToolExecutionResult(
                success=False,
                error=str(e)
            )

