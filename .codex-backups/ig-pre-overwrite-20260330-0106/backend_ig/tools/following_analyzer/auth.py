"""
Authentication helpers for Instagram sessions.

This module handles login verification and username extraction
from authenticated Instagram browser sessions.
"""

import logging
from typing import Optional

from playwright.async_api import Page

logger = logging.getLogger(__name__)


async def assert_logged_in(page: Page) -> None:
    """
    Ensure the current page has an authenticated Instagram session.

    Raises:
        ValueError: If the session is not authenticated or requires verification.
    """
    current_url = page.url or ""
    if any(
        token in current_url for token in ["accounts/login", "challenge", "checkpoint"]
    ):
        raise ValueError(
            "Instagram session is not authenticated or requires verification. "
            "Please re-login with ig_login_helper and refresh the session status."
        )

    login_inputs = page.locator("input[name='username'], input[name='password']")
    if await login_inputs.count():
        raise ValueError(
            "Instagram login required. Please re-login with ig_login_helper "
            "and ensure the profile is valid."
        )


async def try_get_logged_in_username(page: Page) -> Optional[str]:
    """
    Attempt to extract the currently logged-in username from the page.

    Returns:
        The username if found, None otherwise.
    """
    selectors = [
        "a[href^='/']:has(img[alt*='profile picture'])",
        "a[href^='/']:has(svg[aria-label*='Profile'])",
        "a[href^='/']:has(svg[aria-label*='profile'])",
    ]

    for selector in selectors:
        try:
            loc = page.locator(selector).first
            if await loc.count() == 0:
                continue
            href = await loc.get_attribute("href")
            if not href:
                continue
            candidate = href.strip("/").split("/")[0]
            if candidate and candidate not in [
                "accounts",
                "explore",
                "reels",
                "direct",
                "stories",
            ]:
                return candidate
        except Exception:
            continue

    return None


# Legacy aliases for backward compatibility
_assert_logged_in = assert_logged_in
_try_get_logged_in_username = try_get_logged_in_username
