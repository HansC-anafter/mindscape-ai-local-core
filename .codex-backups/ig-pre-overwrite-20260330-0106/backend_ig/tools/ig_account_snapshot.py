"""
IG Account Snapshot Tool
"""

import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

from backend.app.services.tools.base import MindscapeTool
from backend.app.services.tools.schemas import (
    ToolCategory,
    ToolDangerLevel,
    ToolInputSchema,
    ToolMetadata,
    ToolSourceType,
)

from .following_analyzer.runner import _assert_logged_in, _try_get_logged_in_username
from .following_analyzer.page_analyzer import analyze_account_page

logger = logging.getLogger(__name__)


def _parse_count_text_to_number(value: Optional[str]) -> Optional[int]:
    if not value:
        return None

    raw = value.strip().replace(",", "")
    if not raw:
        return None

    import re

    m = re.search(r"(\d+(?:\.\d+)?)(?:\s*([KMB]))?", raw, flags=re.IGNORECASE)
    if not m:
        return None

    num = float(m.group(1))
    suffix = (m.group(2) or "").upper()
    if suffix == "K":
        return int(round(num * 1_000))
    if suffix == "M":
        return int(round(num * 1_000_000))
    if suffix == "B":
        return int(round(num * 1_000_000_000))

    if "億" in raw:
        return int(round(num * 100_000_000))
    if "萬" in raw:
        return int(round(num * 10_000))

    return int(round(num))


async def ig_capture_account_snapshot(
    target_account_handle: str,
    workspace_id: str,
    user_data_dir: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> Dict[str, Any]:
    if not target_account_handle:
        raise ValueError("target_account_handle is required")

    profile_url = (
        f"https://www.instagram.com/{target_account_handle.strip().lstrip('@')}/"
    )
    user_data_dir = user_data_dir or "/app/data/ig-browser-profiles/default"

    from .following_analyzer.browser_session import BrowserSession

    async with BrowserSession(user_data_dir) as (browser, context, page):

        await page.goto(profile_url, wait_until="domcontentloaded", timeout=120000)
        await _assert_logged_in(page)

        source_account_handle = await _try_get_logged_in_username(page)

        stats = await analyze_account_page(page, profile_url, target_account_handle)

        follower_text = stats.get("follower_count_text") or ""
        following_text = stats.get("following_count_text") or ""
        post_text = stats.get("post_count_text") or ""

        profile = {
            "name": stats.get("profile_name") or "",
            "bio": stats.get("profile_bio") or "",
            "avatar_url": stats.get("profile_image_url") or "",
            "external_url": profile_url,
            "follower_count": _parse_count_text_to_number(follower_text),
            "following_count": _parse_count_text_to_number(following_text),
            "post_count": _parse_count_text_to_number(post_text),
            "follower_count_text": follower_text,
            "following_count_text": following_text,
            "post_count_text": post_text,
            "is_verified": False,
        }

        try:
            verified = page.locator(
                'header svg[aria-label*="Verified"], header svg[aria-label*="已驗證"]'
            ).first
            profile["is_verified"] = (await verified.count()) > 0
        except Exception:
            profile["is_verified"] = False

        captured_at = datetime.now().isoformat()
        result = {
            "target": {
                "handle": target_account_handle.strip().lstrip("@"),
                "external_url": profile_url,
            },
            "profile": profile,
            "metadata": {
                "platform": "instagram",
                "source": "ig_account_snapshot",
                "workspace_id": workspace_id,
                "source_account_handle": source_account_handle,
                "source_profile_ref": user_data_dir,
                "target_account_handle": target_account_handle.strip().lstrip("@"),
                "captured_at": captured_at,
                "trace_id": trace_id,
            },
            "raw": stats,
        }

        return result


class IGAccountSnapshotTool(MindscapeTool):
    def __init__(self):
        input_schema = ToolInputSchema(
            type="object",
            properties={
                "target_account_handle": {
                    "type": "string",
                    "description": "Target Instagram account handle",
                },
                "workspace_id": {
                    "type": "string",
                    "description": "Mindscape workspace ID",
                },
                "user_data_dir": {
                    "type": "string",
                    "description": "Persistent browser profile directory for Playwright",
                },
                "trace_id": {
                    "type": "string",
                    "description": "Trace ID for tracking (optional)",
                },
            },
            required=["target_account_handle", "workspace_id"],
        )

        metadata = ToolMetadata(
            name="ig_capture_account_snapshot",
            description="Capture an Instagram account profile snapshot (bio, counts, avatar) using browser automation.",
            input_schema=input_schema,
            category=ToolCategory.CONTENT,
            danger_level=ToolDangerLevel.MEDIUM,
            source_type=ToolSourceType.BUILTIN,
            provider="ig",
        )
        super().__init__(metadata)

    async def execute(self, **kwargs) -> Dict[str, Any]:
        return await ig_capture_account_snapshot(
            target_account_handle=kwargs.get("target_account_handle"),
            workspace_id=kwargs.get("workspace_id"),
            user_data_dir=kwargs.get("user_data_dir"),
            trace_id=kwargs.get("trace_id"),
        )


async def ig_capture_account_snapshot_tool(
    target_account_handle: str,
    workspace_id: str,
    user_data_dir: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> Dict[str, Any]:
    return await ig_capture_account_snapshot(
        target_account_handle=target_account_handle,
        workspace_id=workspace_id,
        user_data_dir=user_data_dir,
        trace_id=trace_id,
    )
