from typing import Any, Dict, Optional

from backend.app.services.tools.base import MindscapeTool
from backend.app.services.tools.schemas import (
    ToolMetadata,
    ToolDangerLevel,
    ToolSourceType,
    ToolInputSchema,
    ToolCategory,
)

from .runner import ig_analyze_following


class IGFollowingAnalyzerTool(MindscapeTool):
    """Tool for extracting and analyzing Instagram following lists."""

    def __init__(self):
        input_schema = ToolInputSchema(
            type="object",
            properties={
                "target_username": {
                    "type": "string",
                    "description": "Target Instagram username to extract following list from",
                },
                "workspace_id": {
                    "type": "string",
                    "description": "Mindscape workspace ID",
                },
                "execution_id": {
                    "type": "string",
                    "description": "Execution ID for correlating progress artifacts (optional; used as trace_id fallback)",
                },
                "max_accounts": {
                    "type": "integer",
                    "description": "Maximum number of accounts to process (None = all)",
                },
                "visit_account_pages": {
                    "type": "boolean",
                    "default": True,
                    "description": "Whether to visit each account page for statistics and data extraction",
                },
                "run_mode": {
                    "type": "string",
                    "default": "full",
                    "description": "Execution mode: 'full' (default), 'list' (scroll only, must reach expected), 'visit' (skip scrolling and only visit pages using existing list)",
                },
                "allow_partial_resume": {
                    "type": "boolean",
                    "default": False,
                    "description": "When run_mode='visit', allow resuming with an incomplete list (accounts < expected). Default false.",
                },
                "user_data_dir": {
                    "type": "string",
                    "description": "Optional persistent browser profile directory for Playwright",
                },
                "trace_id": {
                    "type": "string",
                    "description": "Trace ID for tracking (optional)",
                },
                "seed_posts_count": {
                    "type": "integer",
                    "description": "Number of seed account posts to extract before scrolling (default 30, 0 to skip)",
                },
            },
            required=["target_username", "workspace_id"],
        )

        metadata = ToolMetadata(
            name="ig_analyze_following",
            description="Extract Instagram following list and analyze account pages with browser automation. Uses Playwright to navigate Instagram, extract following list, and visit account pages for statistics.",
            input_schema=input_schema,
            category=ToolCategory.CONTENT,
            danger_level=ToolDangerLevel.MEDIUM,
            source_type=ToolSourceType.BUILTIN,
            provider="ig",
        )
        super().__init__(metadata)

    async def execute(self, **kwargs) -> Dict[str, Any]:
        # Register seed immediately so it appears in the seed list dropdown
        # before the runner starts its long-running work.
        target = kwargs.get("target_username")
        wid = kwargs.get("workspace_id")
        if target and wid:
            try:
                from .persistence import register_seed_immediately

                register_seed_immediately(
                    workspace_id=wid,
                    seed=target,
                    execution_id=kwargs.get("execution_id"),
                    source_handle=None,
                    source_profile_ref=kwargs.get("user_data_dir"),
                )
            except Exception:
                pass  # Non-critical — runner will register later anyway

        # MindscapeTool.safe_execute() already wraps results into ToolExecutionResult.
        # This method should return the raw tool output and raise on failure.
        result = await ig_analyze_following(
            target_username=target,
            workspace_id=wid,
            execution_id=kwargs.get("execution_id"),
            max_accounts=kwargs.get("max_accounts"),
            visit_account_pages=kwargs.get("visit_account_pages", True),
            run_mode=kwargs.get("run_mode"),
            allow_partial_resume=kwargs.get("allow_partial_resume", False),
            user_data_dir=kwargs.get("user_data_dir"),
            trace_id=kwargs.get("trace_id"),
            seed_posts_count=kwargs.get("seed_posts_count"),
        )
        return result


async def ig_analyze_following_tool(
    target_username: str,
    workspace_id: str,
    execution_id: Optional[str] = None,
    max_accounts: Optional[int] = None,
    visit_account_pages: bool = True,
    run_mode: Optional[str] = None,
    allow_partial_resume: bool = False,
    user_data_dir: Optional[str] = None,
    trace_id: Optional[str] = None,
    seed_posts_count: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Entry point for capability tool execution.
    Returns raw output; runtime wraps it into ToolExecutionResult.
    """
    return await ig_analyze_following(
        target_username=target_username,
        workspace_id=workspace_id,
        execution_id=execution_id,
        max_accounts=max_accounts,
        visit_account_pages=visit_account_pages,
        run_mode=run_mode,
        allow_partial_resume=allow_partial_resume,
        user_data_dir=user_data_dir,
        trace_id=trace_id,
        seed_posts_count=seed_posts_count,
    )
