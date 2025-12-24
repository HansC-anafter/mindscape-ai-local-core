"""
IG Review System Tool

Tool for managing review workflow including changelog tracking,
review notes, and decision logs.
"""
import logging
from typing import Dict, Any, Optional

from backend.app.services.tools.base import MindscapeTool
from backend.app.services.tools.schemas import (
    ToolMetadata,
    ToolExecutionResult,
    ToolDangerLevel,
    ToolSourceType,
    ToolInputSchema,
    ToolCategory
)
import os
from capabilities.ig.services.review_system import ReviewSystem
from capabilities.ig.services.workspace_storage import WorkspaceStorage

logger = logging.getLogger(__name__)


class IGReviewSystemTool(MindscapeTool):
    """Tool for managing review workflow"""

    def __init__(self):
        input_schema = ToolInputSchema(
            type="object",
            properties={
                "action": {
                    "type": "string",
                    "enum": ["add_changelog", "add_review_note", "add_decision_log", "update_review_note_status", "get_summary"],
                    "description": "Action to perform"
                },
                "workspace_id": {
                    "type": "string",
                    "description": "Workspace identifier (required if workspace_path not provided)"
                },
                "workspace_path": {
                    "type": "string",
                    "description": "Custom workspace path (optional, for backward compatibility)"
                },
                "post_path": {
                    "type": "string",
                    "description": "Path to post file (relative to workspace or post folder name)"
                },
                "version": {
                    "type": "string",
                    "description": "Version string (required for add_changelog action)"
                },
                "changes": {
                    "type": "string",
                    "description": "Description of changes (required for add_changelog action)"
                },
                "author": {
                    "type": "string",
                    "description": "Author name (optional)"
                },
                "reviewer": {
                    "type": "string",
                    "description": "Reviewer name (required for add_review_note action)"
                },
                "note": {
                    "type": "string",
                    "description": "Review note content (required for add_review_note action)"
                },
                "priority": {
                    "type": "string",
                    "enum": ["high", "medium", "low"],
                    "description": "Priority level (optional, default: medium)"
                },
                "status": {
                    "type": "string",
                    "enum": ["pending", "addressed", "resolved", "rejected"],
                    "description": "Review status (optional)"
                },
                "decision": {
                    "type": "string",
                    "description": "Decision description (required for add_decision_log action)"
                },
                "rationale": {
                    "type": "string",
                    "description": "Rationale for decision (optional)"
                },
                "decision_maker": {
                    "type": "string",
                    "description": "Decision maker name (optional)"
                },
                "note_index": {
                    "type": "integer",
                    "description": "Index of review note (required for update_review_note_status action)"
                },
                "new_status": {
                    "type": "string",
                    "enum": ["pending", "addressed", "resolved", "rejected"],
                    "description": "New status (required for update_review_note_status action)"
                }
            },
            required=["action", "vault_path", "post_path"]
        )

        metadata = ToolMetadata(
            name="ig_review_system_tool",
            description="Manage review workflow including changelog tracking, review notes, and decision logs for content revision cycles.",
            input_schema=input_schema,
            category=ToolCategory.DATA,
            danger_level=ToolDangerLevel.LOW,
            source_type=ToolSourceType.BUILTIN,
            provider="ig"
        )
        super().__init__(metadata)

    async def execute(self, **kwargs) -> ToolExecutionResult:
        """
        Execute review system action

        Args:
            action: Action to perform
            workspace_id: Workspace identifier
            workspace_path: Optional custom workspace path
            post_path: Path to post file
            version: Version string (for add_changelog)
            changes: Changes description (for add_changelog)
            author: Author name (optional)
            reviewer: Reviewer name (for add_review_note)
            note: Review note (for add_review_note)
            priority: Priority level (optional)
            status: Review status (optional)
            decision: Decision description (for add_decision_log)
            rationale: Rationale (for add_decision_log)
            decision_maker: Decision maker (for add_decision_log)
            note_index: Note index (for update_review_note_status)
            new_status: New status (for update_review_note_status)

        Returns:
            ToolExecutionResult with action results
        """
        try:
            action = kwargs.get("action")
            workspace_id = kwargs.get("workspace_id")
            workspace_path = kwargs.get("workspace_path")
            post_path = kwargs.get("post_path")

            if not post_path:
                return ToolExecutionResult(
                    success=False,
                    error="post_path is required"
                )

            # Initialize workspace storage
            capability_code = "ig"

            if workspace_path:
                if not workspace_id:
                    workspace_id = "default"
                is_enterprise_mode = bool(os.getenv("TENANT_ID"))
                storage = WorkspaceStorage.from_workspace_path(
                    workspace_id,
                    capability_code,
                    workspace_path,
                    allow_custom_path=not is_enterprise_mode
                )
            elif workspace_id:
                storage = WorkspaceStorage(workspace_id, capability_code)
            else:
                return ToolExecutionResult(
                    success=False,
                    error="Either workspace_id or workspace_path is required"
                )

            system = ReviewSystem(storage)

            if action == "add_changelog":
                version = kwargs.get("version")
                changes = kwargs.get("changes")
                author = kwargs.get("author")

                if not all([version, changes]):
                    return ToolExecutionResult(
                        success=False,
                        error="version and changes are required for add_changelog action"
                    )

                frontmatter = system.add_changelog_entry(
                    post_path=post_path,
                    version=version,
                    changes=changes,
                    author=author
                )

                return ToolExecutionResult(
                    success=True,
                    result={"frontmatter": frontmatter}
                )

            elif action == "add_review_note":
                reviewer = kwargs.get("reviewer")
                note = kwargs.get("note")
                priority = kwargs.get("priority")
                status = kwargs.get("status")

                if not all([reviewer, note]):
                    return ToolExecutionResult(
                        success=False,
                        error="reviewer and note are required for add_review_note action"
                    )

                frontmatter = system.add_review_note(
                    post_path=post_path,
                    reviewer=reviewer,
                    note=note,
                    priority=priority,
                    status=status
                )

                return ToolExecutionResult(
                    success=True,
                    result={"frontmatter": frontmatter}
                )

            elif action == "add_decision_log":
                decision = kwargs.get("decision")
                rationale = kwargs.get("rationale")
                decision_maker = kwargs.get("decision_maker")

                if not decision:
                    return ToolExecutionResult(
                        success=False,
                        error="decision is required for add_decision_log action"
                    )

                frontmatter = system.add_decision_log(
                    post_path=post_path,
                    decision=decision,
                    rationale=rationale,
                    decision_maker=decision_maker
                )

                return ToolExecutionResult(
                    success=True,
                    result={"frontmatter": frontmatter}
                )

            elif action == "update_review_note_status":
                note_index = kwargs.get("note_index")
                new_status = kwargs.get("new_status")

                if note_index is None or not new_status:
                    return ToolExecutionResult(
                        success=False,
                        error="note_index and new_status are required for update_review_note_status action"
                    )

                frontmatter = system.update_review_note_status(
                    post_path=post_path,
                    note_index=note_index,
                    new_status=new_status
                )

                return ToolExecutionResult(
                    success=True,
                    result={"frontmatter": frontmatter}
                )

            elif action == "get_summary":
                summary = system.get_review_summary(post_path)

                return ToolExecutionResult(
                    success=True,
                    result={"summary": summary}
                )

            else:
                return ToolExecutionResult(
                    success=False,
                    error=f"Unknown action: {action}"
                )

        except Exception as e:
            logger.error(f"Review system tool error: {e}", exc_info=True)
            return ToolExecutionResult(
                success=False,
                error=str(e)
            )




