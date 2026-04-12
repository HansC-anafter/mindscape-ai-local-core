"""
Browser Helper Functions.

Low-level helpers for interacting with Instagram pages:
debug logging/screenshots, parsing following counts, and finding UI elements.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from playwright.async_api import Page

from .utils import parse_count_text_to_int

logger = logging.getLogger(__name__)


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


def debug_log(message: str) -> None:
    """Write debug log to file."""
    try:
        with open("/app/data/ig_debug_artifact_init.log", "a") as f:
            f.write(f"[{datetime.now().isoformat()}] {message}\n")
    except Exception:
        pass


async def save_debug_screenshot(
    page: Page, artifact_manager, trace_id: Optional[str]
) -> None:
    """Save debug screenshot and add to artifact."""
    try:
        ts = _utc_now().strftime("%Y%m%dT%H%M%SZ")
        per_exec_path = f"/app/data/ig_debug_profile_{trace_id or 'noid'}_{ts}.png"
        await page.screenshot(path=per_exec_path)
        logger.info(f"[IGFollowingAnalyzer] Debug screenshot saved to {per_exec_path}")
        artifact_manager.add_debug_screenshot(per_exec_path)

        try:
            await page.screenshot(path="/app/data/ig_debug_profile.png")
        except Exception:
            pass
    except Exception as e:
        logger.warning(f"[IGFollowingAnalyzer] Could not save screenshot: {e}")


async def parse_following_count(page: Page) -> Optional[int]:
    """Parse following count from profile header."""
    try:
        candidates = []
        try:
            candidates.append(
                await page.locator("a[href$='/following/']").first.inner_text(
                    timeout=2000
                )
            )
        except Exception:
            pass
        try:
            candidates.append(
                await page.locator("a[href$='/following/'] span").first.inner_text(
                    timeout=2000
                )
            )
        except Exception:
            pass
        try:
            candidates.append(
                await page.locator("header section ul li")
                .nth(2)
                .locator("span")
                .first.inner_text(timeout=2000)
            )
        except Exception:
            pass

        for c in candidates:
            val = parse_count_text_to_int(c)
            if val and val > 0:
                return val
    except Exception:
        pass
    return None


async def find_following_button(page: Page, target_username: str):
    """Find and return the Following button element."""
    following_selectors = [
        "a[href$='/following/']",
        "text=/追蹤中|Following|following/i",
        "[role='link']:has-text('following')",
        "//a[contains(@href, '/following')]",
    ]

    for selector in following_selectors:
        try:
            if selector.startswith("//"):
                btn = page.locator(f"xpath={selector}").first
            else:
                btn = page.locator(selector).first
            if await btn.is_visible(timeout=3000):
                try:
                    href = await btn.get_attribute("href")
                    if not href:
                        anchor = btn.locator("xpath=ancestor::a[1]").first
                        if await anchor.count():
                            btn = anchor
                except Exception:
                    pass
                logger.info(
                    f"[IGFollowingAnalyzer] Found Following button with selector: {selector}"
                )
                return btn
        except Exception:
            continue

    # Log page content for debugging
    page_text = await page.inner_text("body")
    logger.error(f"[IGFollowingAnalyzer] Page text preview: {page_text[:500]}...")
    raise ValueError(f"Following button not found for {target_username}")


async def find_following_dialog(page: Page, target_username: str):
    """Find and return the Following dialog element."""
    dialog = page.locator('div[role="dialog"]').first
    try:
        if not await dialog.is_visible(timeout=8000):
            if "/following" in (page.url or ""):
                dialog = page.locator("main").first
            else:
                following_url = (
                    f"https://www.instagram.com/{target_username}/following/"
                )
                logger.info(
                    f"[IGFollowingAnalyzer] Navigating directly to: {following_url}"
                )
                await page.goto(
                    following_url, wait_until="domcontentloaded", timeout=120000
                )
                try:
                    await page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass
                dialog = page.locator('div[role="dialog"]').first
                if not await dialog.is_visible(timeout=5000):
                    dialog = page.locator("main").first
    except Exception:
        pass

    if await dialog.count() == 0:
        raise ValueError("Following list container not found")

    return dialog
