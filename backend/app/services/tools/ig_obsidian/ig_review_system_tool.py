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
from backend.app.services.ig_obsidian.review_system import ReviewSystem

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
                "vault_path": {
                    "type": "string",
                    "description": "Path to Obsidian Vault"
                },
                "post_path": {
                    "type": "string",
                    "description": "Path to post file (relative to vault)"
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
            provider="ig_obsidian"
        )
        super().__init__(metadata)

    async def execute(self, **kwargs) -> ToolExecutionResult:
        """
        Execute review system action

        Args:
            action: Action to perform
            vault_path: Path to Obsidian Vault
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
            vault_path = kwargs.get("vault_path")
            post_path = kwargs.get("post_path")

            if not all([vault_path, post_path]):
                return ToolExecutionResult(
                    success=False,
                    error="vault_path and post_path are required"
                )

            system = ReviewSystem(vault_path)

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

