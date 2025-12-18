"""
IG Series Manager Tool

Tool for managing IG Post series including creation, updates, querying,
and cross-referencing.
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
from backend.app.services.ig_obsidian.series_manager import SeriesManager

logger = logging.getLogger(__name__)


class IGSeriesManagerTool(MindscapeTool):
    """Tool for managing IG Post series"""

    def __init__(self):
        input_schema = ToolInputSchema(
            type="object",
            properties={
                "action": {
                    "type": "string",
                    "enum": ["create", "add_post", "get", "list", "get_posts", "get_previous_next", "update_progress"],
                    "description": "Action to perform"
                },
                "vault_path": {
                    "type": "string",
                    "description": "Path to Obsidian Vault"
                },
                "series_code": {
                    "type": "string",
                    "description": "Series code (required for most actions)"
                },
                "series_name": {
                    "type": "string",
                    "description": "Series name (required for create action)"
                },
                "description": {
                    "type": "string",
                    "description": "Series description (optional)"
                },
                "total_posts": {
                    "type": "integer",
                    "description": "Total number of posts planned (optional)"
                },
                "post_path": {
                    "type": "string",
                    "description": "Post file path (relative to vault, required for add_post action)"
                },
                "post_slug": {
                    "type": "string",
                    "description": "Post slug (required for add_post action)"
                },
                "post_number": {
                    "type": "integer",
                    "description": "Post number in series (optional, auto-increment if not provided)"
                },
                "current_post_number": {
                    "type": "integer",
                    "description": "Current post number (required for get_previous_next action)"
                }
            },
            required=["action", "vault_path"]
        )

        metadata = ToolMetadata(
            name="ig_series_manager_tool",
            description="Manage IG Post series including creation, updates, querying, and cross-referencing. Supports series progress tracking and post navigation.",
            input_schema=input_schema,
            category=ToolCategory.DATA,
            danger_level=ToolDangerLevel.LOW,
            source_type=ToolSourceType.BUILTIN,
            provider="ig_obsidian"
        )
        super().__init__(metadata)

    async def execute(self, **kwargs) -> ToolExecutionResult:
        """
        Execute series manager action

        Args:
            action: Action to perform
            vault_path: Path to Obsidian Vault
            series_code: Series code (for most actions)
            series_name: Series name (for create action)
            description: Series description (for create action)
            total_posts: Total posts planned (for create action)
            post_path: Post file path (for add_post action)
            post_slug: Post slug (for add_post action)
            post_number: Post number (for add_post action)
            current_post_number: Current post number (for get_previous_next action)

        Returns:
            ToolExecutionResult with action results
        """
        try:
            action = kwargs.get("action")
            vault_path = kwargs.get("vault_path")

            if not vault_path:
                return ToolExecutionResult(
                    success=False,
                    error="vault_path is required"
                )

            manager = SeriesManager(vault_path)

            if action == "create":
                series_code = kwargs.get("series_code")
                series_name = kwargs.get("series_name")
                description = kwargs.get("description")
                total_posts = kwargs.get("total_posts")

                if not series_code or not series_name:
                    return ToolExecutionResult(
                        success=False,
                        error="series_code and series_name are required for create action"
                    )

                series = manager.create_series(
                    series_code=series_code,
                    series_name=series_name,
                    description=description,
                    total_posts=total_posts
                )

                return ToolExecutionResult(
                    success=True,
                    result={"series": series}
                )

            elif action == "add_post":
                series_code = kwargs.get("series_code")
                post_path = kwargs.get("post_path")
                post_slug = kwargs.get("post_slug")
                post_number = kwargs.get("post_number")

                if not all([series_code, post_path, post_slug]):
                    return ToolExecutionResult(
                        success=False,
                        error="series_code, post_path, and post_slug are required for add_post action"
                    )

                series = manager.add_post_to_series(
                    series_code=series_code,
                    post_path=post_path,
                    post_slug=post_slug,
                    post_number=post_number
                )

                return ToolExecutionResult(
                    success=True,
                    result={"series": series}
                )

            elif action == "get":
                series_code = kwargs.get("series_code")

                if not series_code:
                    return ToolExecutionResult(
                        success=False,
                        error="series_code is required for get action"
                    )

                series = manager.get_series(series_code)

                if not series:
                    return ToolExecutionResult(
                        success=False,
                        error=f"Series {series_code} not found"
                    )

                return ToolExecutionResult(
                    success=True,
                    result={"series": series}
                )

            elif action == "list":
                series_list = manager.list_series()

                return ToolExecutionResult(
                    success=True,
                    result={"series_list": series_list}
                )

            elif action == "get_posts":
                series_code = kwargs.get("series_code")

                if not series_code:
                    return ToolExecutionResult(
                        success=False,
                        error="series_code is required for get_posts action"
                    )

                posts = manager.get_series_posts(series_code)

                return ToolExecutionResult(
                    success=True,
                    result={"posts": posts}
                )

            elif action == "get_previous_next":
                series_code = kwargs.get("series_code")
                current_post_number = kwargs.get("current_post_number")

                if not all([series_code, current_post_number]):
                    return ToolExecutionResult(
                        success=False,
                        error="series_code and current_post_number are required for get_previous_next action"
                    )

                result = manager.get_previous_next_posts(series_code, current_post_number)

                return ToolExecutionResult(
                    success=True,
                    result=result
                )

            elif action == "update_progress":
                series_code = kwargs.get("series_code")

                if not series_code:
                    return ToolExecutionResult(
                        success=False,
                        error="series_code is required for update_progress action"
                    )

                series = manager.update_series_progress(series_code)

                return ToolExecutionResult(
                    success=True,
                    result={"series": series}
                )

            else:
                return ToolExecutionResult(
                    success=False,
                    error=f"Unknown action: {action}"
                )

        except Exception as e:
            logger.error(f"Series manager tool error: {e}", exc_info=True)
            return ToolExecutionResult(
                success=False,
                error=str(e)
            )


def create_ig_obsidian_tools() -> List[MindscapeTool]:
    """
    Create all IG + Obsidian integration tools

    Returns:
        List of IG + Obsidian MindscapeTool instances
    """
    from typing import List
    from backend.app.services.tools.base import MindscapeTool
    from backend.app.services.tools.ig_obsidian.ig_vault_structure_tool import IGVaultStructureTool
    from backend.app.services.tools.ig_obsidian.ig_frontmatter_validator_tool import IGFrontmatterValidatorTool
    from backend.app.services.tools.ig_obsidian.ig_template_engine_tool import IGTemplateEngineTool
    from backend.app.services.tools.ig_obsidian.ig_hashtag_manager_tool import IGHashtagManagerTool
    from backend.app.services.tools.ig_obsidian.ig_asset_manager_tool import IGAssetManagerTool
    from backend.app.services.tools.ig_obsidian.ig_export_pack_generator_tool import IGExportPackGeneratorTool
    from backend.app.services.tools.ig_obsidian.ig_content_checker_tool import IGContentCheckerTool
    from backend.app.services.tools.ig_obsidian.ig_review_system_tool import IGReviewSystemTool
    from backend.app.services.tools.ig_obsidian.ig_metrics_backfill_tool import IGMetricsBackfillTool
    from backend.app.services.tools.ig_obsidian.ig_interaction_templates_tool import IGInteractionTemplatesTool
    from backend.app.services.tools.ig_obsidian.ig_content_reuse_tool import IGContentReuseTool
    from backend.app.services.tools.ig_obsidian.ig_complete_workflow_tool import IGCompleteWorkflowTool
    from backend.app.services.tools.ig_obsidian.ig_batch_processor_tool import IGBatchProcessorTool

    return [
        IGVaultStructureTool(),
        IGFrontmatterValidatorTool(),
        IGTemplateEngineTool(),
        IGHashtagManagerTool(),
        IGAssetManagerTool(),
        IGExportPackGeneratorTool(),
        IGContentCheckerTool(),
        IGSeriesManagerTool(),
        IGReviewSystemTool(),
        IGMetricsBackfillTool(),
        IGInteractionTemplatesTool(),
        IGContentReuseTool(),
        IGCompleteWorkflowTool(),
        IGBatchProcessorTool()
    ]


