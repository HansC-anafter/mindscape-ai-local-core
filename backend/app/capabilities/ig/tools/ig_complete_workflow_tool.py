"""
IG Complete Workflow Tool

Tool for orchestrating multiple playbooks in sequence to execute
end-to-end workflows for IG post creation and management.
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
from capabilities.ig.services.complete_workflow import CompleteWorkflow

logger = logging.getLogger(__name__)


class IGCompleteWorkflowTool(MindscapeTool):
    """Tool for orchestrating complete workflows"""

    def __init__(self):
        input_schema = ToolInputSchema(
            type="object",
            properties={
                "action": {
                    "type": "string",
                    "enum": ["execute_workflow", "create_post_workflow", "review_workflow"],
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
                "workflow_name": {
                    "type": "string",
                    "description": "Name of the workflow (for execute_workflow action)"
                },
                "workflow_steps": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "List of workflow steps (for execute_workflow action)"
                },
                "initial_context": {
                    "type": "object",
                    "description": "Initial context variables (for execute_workflow action)"
                },
                "post_content": {
                    "type": "string",
                    "description": "Post content (for create_post_workflow action)"
                },
                "post_metadata": {
                    "type": "object",
                    "description": "Post metadata/frontmatter (for create_post_workflow action)"
                },
                "target_folder": {
                    "type": "string",
                    "description": "Target folder for post (for create_post_workflow action)"
                },
                "post_path": {
                    "type": "string",
                    "description": "Path to post file (for review_workflow action)"
                },
                "review_notes": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "List of review notes (for review_workflow action)"
                }
            },
            required=["action"]
        )

        metadata = ToolMetadata(
            name="ig_complete_workflow_tool",
            description="Orchestrate multiple playbooks in sequence to execute end-to-end workflows for IG post creation and management.",
            input_schema=input_schema,
            category=ToolCategory.WORKFLOW,
            danger_level=ToolDangerLevel.MEDIUM,
            source_type=ToolSourceType.BUILTIN,
            provider="ig"
        )
        super().__init__(metadata)

    async def execute(self, **kwargs) -> ToolExecutionResult:
        """
        Execute complete workflow action

        Args:
            action: Action to perform
            workspace_id: Workspace identifier
            workspace_path: Custom workspace path (for backward compatibility)
            workflow_name: Workflow name (for execute_workflow)
            workflow_steps: Workflow steps (for execute_workflow)
            initial_context: Initial context (for execute_workflow)
            post_content: Post content (for create_post_workflow)
            post_metadata: Post metadata (for create_post_workflow)
            target_folder: Target folder (for create_post_workflow)
            post_path: Post path (for review_workflow)
            review_notes: Review notes (for review_workflow)

        Returns:
            ToolExecutionResult with workflow execution results
        """
        try:
            action = kwargs.get("action")
            workspace_id = kwargs.get("workspace_id")
            workspace_path = kwargs.get("workspace_path")

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

            workflow = CompleteWorkflow(storage)

            if action == "execute_workflow":
                workflow_name = kwargs.get("workflow_name")
                workflow_steps = kwargs.get("workflow_steps")
                initial_context = kwargs.get("initial_context")

                if not all([workflow_name, workflow_steps]):
                    return ToolExecutionResult(
                        success=False,
                        error="workflow_name and workflow_steps are required for execute_workflow action"
                    )

                result = workflow.execute_workflow(
                    workflow_name=workflow_name,
                    workflow_steps=workflow_steps,
                    initial_context=initial_context
                )

                return ToolExecutionResult(
                    success=result["status"] == "success",
                    result=result
                )

            elif action == "create_post_workflow":
                post_content = kwargs.get("post_content")
                post_metadata = kwargs.get("post_metadata")
                target_folder = kwargs.get("target_folder")

                if not all([post_content, post_metadata]):
                    return ToolExecutionResult(
                        success=False,
                        error="post_content and post_metadata are required for create_post_workflow action"
                    )

                result = workflow.create_post_workflow(
                    post_content=post_content,
                    post_metadata=post_metadata,
                    target_folder=target_folder
                )

                return ToolExecutionResult(
                    success=result["status"] == "success",
                    result=result
                )

            elif action == "review_workflow":
                post_path = kwargs.get("post_path")
                review_notes = kwargs.get("review_notes", [])

                if not post_path:
                    return ToolExecutionResult(
                        success=False,
                        error="post_path is required for review_workflow action"
                    )

                result = workflow.review_workflow(
                    post_path=post_path,
                    review_notes=review_notes
                )

                return ToolExecutionResult(
                    success=result["status"] == "success",
                    result=result
                )

            else:
                return ToolExecutionResult(
                    success=False,
                    error=f"Unknown action: {action}"
                )

        except Exception as e:
            logger.error(f"Complete workflow tool error: {e}", exc_info=True)
            return ToolExecutionResult(
                success=False,
                error=str(e)
            )

