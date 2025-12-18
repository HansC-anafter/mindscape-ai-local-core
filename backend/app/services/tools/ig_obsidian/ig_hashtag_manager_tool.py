"""
IG Hashtag Manager Tool

Tool for managing hashtag groups and combining hashtags for IG posts.
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
from backend.app.services.ig_obsidian.hashtag_manager import HashtagManager

logger = logging.getLogger(__name__)


class IGHashtagManagerTool(MindscapeTool):
    """Tool for managing hashtag groups and combining hashtags"""

    def __init__(self):
        input_schema = ToolInputSchema(
            type="object",
            properties={
                "action": {
                    "type": "string",
                    "enum": ["load_groups", "combine", "check_blocked"],
                    "description": "Action to perform: load_groups=load hashtag groups, combine=combine hashtags, check_blocked=check blocked hashtags"
                },
                "intent": {
                    "type": "string",
                    "enum": ["教育", "引流", "轉換", "品牌"],
                    "description": "Post intent (required for combine action)"
                },
                "audience": {
                    "type": "string",
                    "description": "Target audience (optional, for combine action)"
                },
                "region": {
                    "type": "string",
                    "description": "Region (optional, for combine action)"
                },
                "hashtag_count": {
                    "type": "integer",
                    "enum": [15, 25, 30],
                    "default": 25,
                    "description": "Required hashtag count (for combine action)"
                },
                "hashtag_groups": {
                    "type": "object",
                    "description": "Hashtag groups to use (optional, for combine action)"
                },
                "hashtags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of hashtags to check (required for check_blocked action)"
                }
            },
            required=["action"]
        )

        metadata = ToolMetadata(
            name="ig_hashtag_manager_tool",
            description="Manage hashtag groups and combine hashtags for IG posts. Supports brand fixed groups, theme groups, campaign groups, and blocked hashtag checking.",
            input_schema=input_schema,
            category=ToolCategory.CONTENT,
            danger_level=ToolDangerLevel.LOW,
            source_type=ToolSourceType.BUILTIN,
            provider="ig_obsidian"
        )
        super().__init__(metadata)

    async def execute(self, **kwargs) -> ToolExecutionResult:
        """
        Execute hashtag manager action

        Args:
            action: Action to perform (load_groups, combine, check_blocked)
            intent: Post intent (for combine action)
            audience: Target audience (for combine action)
            region: Region (for combine action)
            hashtag_count: Required hashtag count (for combine action)
            hashtag_groups: Hashtag groups to use (for combine action)
            hashtags: List of hashtags to check (for check_blocked action)

        Returns:
            ToolExecutionResult with action results
        """
        try:
            action = kwargs.get("action")

            if action not in ["load_groups", "combine", "check_blocked"]:
                return ToolExecutionResult(
                    success=False,
                    error=f"Invalid action: {action}. Must be 'load_groups', 'combine', or 'check_blocked'"
                )

            manager = HashtagManager()

            if action == "load_groups":
                hashtag_groups = manager.load_groups()

                return ToolExecutionResult(
                    success=True,
                    result={
                        "hashtag_groups": hashtag_groups
                    }
                )

            elif action == "combine":
                intent = kwargs.get("intent")
                audience = kwargs.get("audience")
                region = kwargs.get("region")
                hashtag_count = kwargs.get("hashtag_count", 25)
                hashtag_groups = kwargs.get("hashtag_groups")

                if not intent:
                    return ToolExecutionResult(
                        success=False,
                        error="intent is required for combine action"
                    )

                result = manager.combine_hashtags(
                    intent=intent,
                    audience=audience,
                    region=region,
                    hashtag_count=hashtag_count,
                    hashtag_groups=hashtag_groups
                )

                return ToolExecutionResult(
                    success=True,
                    result={
                        "recommended_hashtags": result["recommended_hashtags"],
                        "blocked_hashtags": result["blocked_hashtags"],
                        "hashtag_groups_used": result["hashtag_groups_used"],
                        "total_count": result["total_count"]
                    }
                )

            elif action == "check_blocked":
                hashtags = kwargs.get("hashtags")

                if not hashtags:
                    return ToolExecutionResult(
                        success=False,
                        error="hashtags is required for check_blocked action"
                    )

                result = manager.check_blocked(hashtags)

                return ToolExecutionResult(
                    success=True,
                    result=result
                )

        except Exception as e:
            logger.error(f"Hashtag manager tool error: {e}", exc_info=True)
            return ToolExecutionResult(
                success=False,
                error=str(e)
            )


# Tool creation is handled in ig_asset_manager_tool.py to avoid circular imports

