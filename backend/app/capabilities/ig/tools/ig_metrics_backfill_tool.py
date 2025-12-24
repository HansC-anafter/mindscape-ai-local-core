"""
IG Metrics Backfill Tool

Tool for managing post-publication metrics including manual backfill,
data analysis, and performance element tracking.
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
from capabilities.ig.services.metrics_backfill import MetricsBackfill

logger = logging.getLogger(__name__)


class IGMetricsBackfillTool(MindscapeTool):
    """Tool for managing post-publication metrics backfill"""

    def __init__(self):
        input_schema = ToolInputSchema(
            type="object",
            properties={
                "action": {
                    "type": "string",
                    "enum": ["backfill", "analyze", "track_elements", "write_rules", "aggregate_series"],
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
                "post_path": {
                    "type": "string",
                    "description": "Path to post file (relative to workspace or Obsidian-style)"
                },
                "metrics": {
                    "type": "object",
                    "description": "Metrics dictionary (required for backfill action)"
                },
                "backfill_source": {
                    "type": "string",
                    "description": "Source of backfill (e.g., 'manual', 'api', 'scraper')"
                },
                "threshold_config": {
                    "type": "object",
                    "description": "Custom threshold configuration (optional for analyze action)"
                },
                "elements": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of performance elements (required for track_elements action)"
                },
                "performance_level": {
                    "type": "string",
                    "enum": ["good", "average", "poor"],
                    "description": "Performance level (for track_elements action)"
                },
                "rules": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "List of performance rules (required for write_rules action)"
                },
                "series_code": {
                    "type": "string",
                    "description": "Series code (required for aggregate_series action)"
                },
                "series_posts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of post paths in series (required for aggregate_series action)"
                }
            },
            required=["action"]
        )

        metadata = ToolMetadata(
            name="ig_metrics_backfill_tool",
            description="Manage post-publication metrics including manual backfill, data analysis, performance element tracking, and series aggregation.",
            input_schema=input_schema,
            category=ToolCategory.ANALYSIS,
            danger_level=ToolDangerLevel.LOW,
            source_type=ToolSourceType.BUILTIN,
            provider="ig"
        )
        super().__init__(metadata)

    async def execute(self, **kwargs) -> ToolExecutionResult:
        """
        Execute metrics backfill action

        Args:
            action: Action to perform
            workspace_id: Workspace identifier
            workspace_path: Custom workspace path (for backward compatibility)
            post_path: Path to post file
            metrics: Metrics dictionary (for backfill)
            backfill_source: Source of backfill (for backfill)
            threshold_config: Threshold configuration (for analyze)
            elements: Performance elements (for track_elements)
            performance_level: Performance level (for track_elements)
            rules: Performance rules (for write_rules)
            series_code: Series code (for aggregate_series)
            series_posts: Series post paths (for aggregate_series)

        Returns:
            ToolExecutionResult with action results
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

            backfill = MetricsBackfill(storage)

            if action == "backfill":
                post_path = kwargs.get("post_path")
                metrics = kwargs.get("metrics")
                backfill_source = kwargs.get("backfill_source")

                if not all([post_path, metrics]):
                    return ToolExecutionResult(
                        success=False,
                        error="post_path and metrics are required for backfill action"
                    )

                frontmatter = backfill.backfill_metrics(
                    post_path=post_path,
                    metrics=metrics,
                    backfill_source=backfill_source
                )

                return ToolExecutionResult(
                    success=True,
                    result={"frontmatter": frontmatter}
                )

            elif action == "analyze":
                post_path = kwargs.get("post_path")
                threshold_config = kwargs.get("threshold_config")

                if not post_path:
                    return ToolExecutionResult(
                        success=False,
                        error="post_path is required for analyze action"
                    )

                analysis = backfill.analyze_performance(
                    post_path=post_path,
                    threshold_config=threshold_config
                )

                return ToolExecutionResult(
                    success=True,
                    result={"analysis": analysis}
                )

            elif action == "track_elements":
                post_path = kwargs.get("post_path")
                elements = kwargs.get("elements")
                performance_level = kwargs.get("performance_level", "good")

                if not all([post_path, elements]):
                    return ToolExecutionResult(
                        success=False,
                        error="post_path and elements are required for track_elements action"
                    )

                frontmatter = backfill.track_performance_elements(
                    post_path=post_path,
                    elements=elements,
                    performance_level=performance_level
                )

                return ToolExecutionResult(
                    success=True,
                    result={"frontmatter": frontmatter}
                )

            elif action == "write_rules":
                post_path = kwargs.get("post_path")
                rules = kwargs.get("rules")

                if not all([post_path, rules]):
                    return ToolExecutionResult(
                        success=False,
                        error="post_path and rules are required for write_rules action"
                    )

                frontmatter = backfill.write_performance_rules(
                    post_path=post_path,
                    rules=rules
                )

                return ToolExecutionResult(
                    success=True,
                    result={"frontmatter": frontmatter}
                )

            elif action == "aggregate_series":
                series_code = kwargs.get("series_code")
                series_posts = kwargs.get("series_posts")

                if not all([series_code, series_posts]):
                    return ToolExecutionResult(
                        success=False,
                        error="series_code and series_posts are required for aggregate_series action"
                    )

                aggregation = backfill.aggregate_series_metrics(
                    series_code=series_code,
                    series_posts=series_posts
                )

                return ToolExecutionResult(
                    success=True,
                    result={"aggregation": aggregation}
                )

            else:
                return ToolExecutionResult(
                    success=False,
                    error=f"Unknown action: {action}"
                )

        except Exception as e:
            logger.error(f"Metrics backfill tool error: {e}", exc_info=True)
            return ToolExecutionResult(
                success=False,
                error=str(e)
            )

