"""
Instagram Private API Visitor.

Fast alternative to Playwright page visits.
Uses the i.instagram.com mobile API with the existing session cookie,
returning the same stats dict format as analyze_account_page().

Typical response time: 0.3–0.5s per account vs 30–90s with Playwright.

Fallback strategy:
- 401 / 403  → session expired or account not found (caller decides)
- 429         → rate limited (caller should fall back to browser)
- Any other   → transient error (caller falls back to browser)
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

_API_BASE = "https://i.instagram.com/api/v1/users/web_profile_info/"
_APP_ID = "936619743392459"  # public IG web app ID (stable for years)

# How many API failures in a row before we give up on the API for this run
_API_CIRCUIT_BREAKER_THRESHOLD = 5

# Minimum delay between requests (seconds) to avoid rate limiting
_MIN_REQUEST_DELAY = 0.5


class PrivateAPIRateLimited(Exception):
    """Raised when IG API returns 429 or signals rate limiting."""


class PrivateAPIAuthError(Exception):
    """Raised when the session cookie is invalid (401/403)."""


class PrivateAPINotFound(Exception):
    """Raised when the account doesn't exist or is unavailable (404)."""


# ── Session loading ────────────────────────────────────────────────────────────


def _load_session_cookies(storage_state_path: str) -> Dict[str, str]:
    """
    Load Instagram cookies from a Playwright storage_state.json file.

    Returns a dict of {name: value} for all cookies on .instagram.com.
    """
    path = Path(storage_state_path)
    if not path.exists():
        raise FileNotFoundError(
            f"storage_state.json not found at: {storage_state_path}"
        )
    with path.open("r") as f:
        state = json.load(f)

    cookies: Dict[str, str] = {}
    for cookie in state.get("cookies", []):
        domain = cookie.get("domain", "")
        if "instagram.com" in domain:
            cookies[cookie["name"]] = cookie["value"]

    if "sessionid" not in cookies:
        raise ValueError(
            f"No 'sessionid' cookie found in {storage_state_path}. "
            "The Instagram session may have expired — please re-login."
        )
    return cookies


# ── Response mapping ───────────────────────────────────────────────────────────


def _format_count(n: Optional[int], label: str) -> str:
    """Format a follower/following/post count as text, e.g. '1,234 followers'."""
    if n is None:
        return ""
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M {label}"
    if n >= 1_000:
        return f"{n/1_000:.1f}K {label}"  # abbreviated for very large counts
    return f"{n:,} {label}"


def _map_api_response(user: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map the i.instagram.com API user object to the same dict format
    returned by analyze_account_page().
    """
    stats: Dict[str, Any] = {}

    # Counts
    follower_count: Optional[int] = (user.get("edge_followed_by") or {}).get("count")
    following_count: Optional[int] = (user.get("edge_follow") or {}).get("count")
    post_count: Optional[int] = (user.get("edge_owner_to_timeline_media") or {}).get(
        "count"
    )

    stats["follower_count_text"] = _format_count(follower_count, "followers")
    stats["following_count_text"] = _format_count(following_count, "following")
    stats["post_count_text"] = _format_count(post_count, "posts")

    # Store raw ints for DB normalisation (page_analyzer only stored text)
    if follower_count is not None:
        stats["_follower_count_raw"] = follower_count
    if following_count is not None:
        stats["_following_count_raw"] = following_count
    if post_count is not None:
        stats["_post_count_raw"] = post_count

    # Identity
    full_name = (user.get("full_name") or "").strip()
    if full_name:
        stats["profile_name"] = full_name

    bio = (user.get("biography") or "").strip()
    if bio:
        stats["profile_bio"] = bio

    # Profile image — prefer HD version
    profile_img = (
        user.get("profile_pic_url_hd") or user.get("profile_pic_url") or ""
    ).strip()
    if profile_img:
        stats["profile_image_url"] = profile_img

    # Privacy / verification flags
    stats["is_private"] = bool(user.get("is_private"))
    stats["is_verified"] = bool(user.get("is_verified"))

    # Contact info (only populated for Business/Creator accounts)
    biz_email = (user.get("business_email") or "").strip()
    if biz_email:
        stats["public_email"] = biz_email
    elif bio:
        # Fallback: regex scan bio for email (mirrors page_analyzer behaviour)
        _EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
        m = _EMAIL_RE.search(bio)
        if m:
            stats["public_email"] = m.group(0).lower()

    biz_phone = (user.get("business_phone_number") or "").strip()
    if biz_phone:
        stats["public_phone_number"] = biz_phone

    # External website
    external_url = (
        user.get("external_url")
        or (user.get("bio_links") or [{}])[0].get("url", "")
        or ""
    ).strip()
    if external_url:
        stats["external_url"] = external_url

    # Grid posts (up to 12) — same schema as _persist_grid_posts expects
    if not stats["is_private"]:
        edges = (user.get("edge_owner_to_timeline_media") or {}).get("edges") or []
        grid_posts: List[Dict[str, Any]] = []
        for edge in edges[:12]:
            node = edge.get("node") or {}
            shortcode = node.get("shortcode")
            if not shortcode:
                continue
            is_video = node.get("is_video", False)
            post_type = "reel" if is_video else "image"
            thumbnail = node.get("display_url") or node.get("thumbnail_src") or ""
            grid_posts.append(
                {
                    "post_shortcode": shortcode,
                    "post_type": post_type,
                    "post_url": f"https://www.instagram.com/p/{shortcode}/",
                    "thumbnail_url": thumbnail or None,
                }
            )
        if grid_posts:
            stats["grid_posts"] = grid_posts
        # Signal to caller: API returned post count but no edges
        stats["_api_grid_posts_available"] = bool(grid_posts)

    stats["page_analyzed_at"] = datetime.now().isoformat()
    stats["_source"] = "private_api"  # tag so we can filter in logs/analytics
    return stats


# ── API client ─────────────────────────────────────────────────────────────────


class PrivateAPIVisitor:
    """
    Fetches Instagram profile data via i.instagram.com private API.

    Usage::

        visitor = PrivateAPIVisitor(storage_state_path="/.../storage_state.json")
        try:
            stats = await visitor.fetch_profile(username)
        except PrivateAPIRateLimited:
            # fall back to Playwright
        except PrivateAPIAuthError:
            # session expired

    Thread-safety: the underlying httpx.AsyncClient is not shared across
    concurrent coroutines.  Create one PrivateAPIVisitor per task.
    """

    def __init__(
        self,
        storage_state_path: str,
        min_request_delay: float = _MIN_REQUEST_DELAY,
    ) -> None:
        self._storage_state_path = storage_state_path
        self._min_delay = min_request_delay
        self._cookies: Dict[str, str] = {}
        self._client: Optional[httpx.AsyncClient] = None
        self._last_request_at: float = 0.0
        self._consecutive_api_failures = 0
        self._total_api_success = 0
        self._total_api_fallback = 0

    async def __aenter__(self) -> "PrivateAPIVisitor":
        self._cookies = _load_session_cookies(self._storage_state_path)
        cookie_str = "; ".join(f"{k}={v}" for k, v in self._cookies.items())
        self._client = httpx.AsyncClient(
            headers={
                "X-IG-App-ID": _APP_ID,
                "Cookie": cookie_str,
                "User-Agent": (
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/21A5303d "
                    "Instagram 313.0.0.11.109"
                ),
                "Referer": "https://www.instagram.com/",
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "*/*",
                "Accept-Language": "en-US,en;q=0.9",
            },
            timeout=10.0,
            follow_redirects=True,
        )
        logger.info(
            "[PrivateAPIVisitor] Session loaded — sessionid found, " "min_delay=%.1fs",
            self._min_delay,
        )
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
        logger.info(
            "[PrivateAPIVisitor] Session closed — "
            "api_success=%d, api_fallback=%d, consecutive_failures=%d",
            self._total_api_success,
            self._total_api_fallback,
            self._consecutive_api_failures,
        )

    @property
    def is_circuit_open(self) -> bool:
        """True when too many consecutive API failures — stop trying API."""
        return self._consecutive_api_failures >= _API_CIRCUIT_BREAKER_THRESHOLD

    def record_fallback(self) -> None:
        """Call this when a fetch falls back to Playwright."""
        self._total_api_fallback += 1
        self._consecutive_api_failures += 1

    def record_success(self) -> None:
        """Call this after a successful API fetch."""
        self._total_api_success += 1
        self._consecutive_api_failures = 0

    async def _throttle(self) -> None:
        """Enforce minimum delay between requests."""
        now = time.monotonic()
        elapsed = now - self._last_request_at
        if elapsed < self._min_delay:
            import asyncio

            await asyncio.sleep(self._min_delay - elapsed)
        self._last_request_at = time.monotonic()

    async def fetch_profile(self, username: str) -> Dict[str, Any]:
        """
        Fetch profile stats for *username* from i.instagram.com.

        Returns the same dict format as analyze_account_page().

        Raises:
            PrivateAPIRateLimited: on HTTP 429 or login-wall redirect.
            PrivateAPIAuthError:   on HTTP 401/403 (session invalid).
            PrivateAPINotFound:    on HTTP 404 (account not found).
            httpx.HTTPError:       on network failures / other HTTP errors.
        """
        if not self._client:
            raise RuntimeError(
                "PrivateAPIVisitor must be used as async context manager"
            )

        await self._throttle()

        url = f"{_API_BASE}?username={username}"
        resp = await self._client.get(url)

        # ── Error handling ──────────────────────────────────────────────────
        if resp.status_code == 429:
            logger.warning("[PrivateAPIVisitor] Rate limited (429) for @%s", username)
            raise PrivateAPIRateLimited(f"Rate limited fetching @{username}")

        if resp.status_code in (401, 403):
            # Check if this is a login-wall response (happens when sessionid expires)
            logger.warning(
                "[PrivateAPIVisitor] Auth error (%d) for @%s — session may be expired",
                resp.status_code,
                username,
            )
            raise PrivateAPIAuthError(
                f"HTTP {resp.status_code} fetching @{username} — session may be invalid"
            )

        if resp.status_code == 404:
            raise PrivateAPINotFound(f"Account @{username} not found (404)")

        resp.raise_for_status()

        # ── Parse response ──────────────────────────────────────────────────
        try:
            data = resp.json()
        except Exception as exc:
            raise ValueError(
                f"Non-JSON response from IG API for @{username}: {exc}"
            ) from exc

        # IG sometimes returns {"status": "fail"} with a login-wall page
        if data.get("status") == "fail" or "data" not in data:
            # Likely a login-wall or geo-block — treat as rate limited
            logger.warning(
                "[PrivateAPIVisitor] API returned status=fail for @%s — "
                "treating as rate limited",
                username,
            )
            raise PrivateAPIRateLimited(
                f"API status=fail for @{username} (login wall or geo-block)"
            )

        user = (data.get("data") or {}).get("user")
        if not user:
            raise PrivateAPINotFound(f"No user data in API response for @{username}")

        stats = _map_api_response(user)
        logger.debug(
            "[PrivateAPIVisitor] ✓ @%s — followers=%s, private=%s, source=api",
            username,
            stats.get("follower_count_text", "?"),
            stats.get("is_private"),
        )
        return stats

    @property
    def stats_summary(self) -> str:
        return (
            f"api_success={self._total_api_success}, "
            f"api_fallback={self._total_api_fallback}, "
            f"circuit_open={self.is_circuit_open}"
        )
