"""
IG Batch Processor Tool

Tool for managing batch processing of multiple posts including validation,
generation, and export operations.
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
from capabilities.ig.services.batch_processor import BatchProcessor

logger = logging.getLogger(__name__)


class IGBatchProcessorTool(MindscapeTool):
    """Tool for managing batch processing of multiple posts"""

    def __init__(self):
        input_schema = ToolInputSchema(
            type="object",
            properties={
                "action": {
                    "type": "string",
                    "enum": ["batch_validate", "batch_generate_export_packs", "batch_update_status", "batch_process"],
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
                "post_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of post file paths (relative to workspace or Obsidian-style)"
                },
                "strict_mode": {
                    "type": "boolean",
                    "description": "If True, all required fields must be present (for batch_validate)"
                },
                "output_folder": {
                    "type": "string",
                    "description": "Output folder for export packs (for batch_generate_export_packs)"
                },
                "new_status": {
                    "type": "string",
                    "description": "New status to set (for batch_update_status)"
                },
                "operations": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of operations to perform (for batch_process)"
                },
                "operation_config": {
                    "type": "object",
                    "description": "Configuration for operations (for batch_process)"
                }
            },
            required=["action", "post_paths"]
        )

        metadata = ToolMetadata(
            name="ig_batch_processor_tool",
            description="Manage batch processing of multiple posts including validation, generation, and export operations.",
            input_schema=input_schema,
            category=ToolCategory.DATA,
            danger_level=ToolDangerLevel.MEDIUM,
            source_type=ToolSourceType.BUILTIN,
            provider="ig"
        )
        super().__init__(metadata)

    async def execute(self, **kwargs) -> ToolExecutionResult:
        """
        Execute batch processor action

        Args:
            action: Action to perform
            workspace_id: Workspace identifier
            workspace_path: Custom workspace path (for backward compatibility)
            post_paths: List of post file paths
            strict_mode: Strict mode for validation
            output_folder: Output folder for export packs
            new_status: New status to set
            operations: List of operations
            operation_config: Operation configuration

        Returns:
            ToolExecutionResult with batch processing results
        """
        try:
            action = kwargs.get("action")
            workspace_id = kwargs.get("workspace_id")
            workspace_path = kwargs.get("workspace_path")
            post_paths = kwargs.get("post_paths")

            if not post_paths:
                return ToolExecutionResult(
                    success=False,
                    error="post_paths is required"
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

            processor = BatchProcessor(storage)

            if action == "batch_validate":
                strict_mode = kwargs.get("strict_mode", False)

                result = processor.batch_validate(
                    post_paths=post_paths,
                    strict_mode=strict_mode
                )

                return ToolExecutionResult(
                    success=True,
                    result=result
                )

            elif action == "batch_generate_export_packs":
                output_folder = kwargs.get("output_folder")

                result = processor.batch_generate_export_packs(
                    post_paths=post_paths,
                    output_folder=output_folder
                )

                return ToolExecutionResult(
                    success=True,
                    result=result
                )

            elif action == "batch_update_status":
                new_status = kwargs.get("new_status")

                if not new_status:
                    return ToolExecutionResult(
                        success=False,
                        error="new_status is required for batch_update_status action"
                    )

                result = processor.batch_update_status(
                    post_paths=post_paths,
                    new_status=new_status
                )

                return ToolExecutionResult(
                    success=True,
                    result=result
                )

            elif action == "batch_process":
                operations = kwargs.get("operations")
                operation_config = kwargs.get("operation_config")

                if not operations:
                    return ToolExecutionResult(
                        success=False,
                        error="operations is required for batch_process action"
                    )

                result = processor.batch_process(
                    post_paths=post_paths,
                    operations=operations,
                    operation_config=operation_config
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
            logger.error(f"Batch processor tool error: {e}", exc_info=True)
            return ToolExecutionResult(
                success=False,
                error=str(e)
            )

