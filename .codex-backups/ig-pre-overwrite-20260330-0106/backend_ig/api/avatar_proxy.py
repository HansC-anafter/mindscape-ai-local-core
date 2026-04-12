"""
IG Avatar Proxy with Caching

Proxies Instagram profile pictures through the backend with local caching.
This solves the 403 Forbidden error when IG CDN URLs expire.
"""

import os
import logging
import hashlib
import httpx
import re
import random
from datetime import datetime, timedelta
from pathlib import Path
from fastapi import APIRouter, Path as PathParam
from fastapi.responses import FileResponse, Response

router = APIRouter(tags=["ig-avatar"])
logger = logging.getLogger(__name__)

AVATAR_CACHE_DIR = Path(os.environ.get("DATA_DIR", "data")) / "ig_avatars"
CACHE_MAX_AGE_DAYS = 7

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


def get_cache_path(username: str) -> Path:
    """Get the cache file path for a username."""
    safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", username.lower())
    return AVATAR_CACHE_DIR / f"{safe_name}.jpg"


def is_cache_valid(cache_path: Path) -> bool:
    """Check if cache file exists and is not too old."""
    if not cache_path.exists():
        return False

    mtime = datetime.fromtimestamp(cache_path.stat().st_mtime)
    age = datetime.now() - mtime
    return age < timedelta(days=CACHE_MAX_AGE_DAYS)


def get_browser_headers() -> dict:
    """Get headers that mimic a real browser.
    
    NOTE: Do NOT include Sec-Fetch-* headers here — Instagram returns
    a truncated HTML response (~163KB) when those are present, stripping
    og:image meta tags and embedded JSON profile data. Without them the
    full page (~900KB) is returned with all the data we need.
    
    NOTE: Accept-Encoding must NOT include 'br' (brotli) — httpx in the
    Docker container lacks brotli support and will return raw compressed
    bytes instead of decoded text, breaking all regex matching.
    """
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }


async def fetch_avatar_url(username: str) -> str | None:
    """Fetch the profile picture URL for a specific Instagram user.
    
    Strategy:
    1. PrivateAPIVisitor — uses authenticated Playwright cookies to bypass 
       unauthenticated Rate Limits and retrieves TARGET's avatar via API.
    2. HTML scraping (fallback) — scrapes public og:image if session missing.
    """
    try:
        # Import dynamically to avoid circular dependencies
        from ..tools.following_analyzer.private_api_visitor import (
            PrivateAPIVisitor,
            PrivateAPIRateLimited,
            PrivateAPIAuthError,
            PrivateAPINotFound,
        )
        
        _storage_path = "data/ig-browser-profiles/default/storage_state.json"
        
        try:
            visitor = PrivateAPIVisitor(storage_state_path=_storage_path)
            async with visitor:
                stats = await visitor.fetch_profile(username)
                pic_url = stats.get("profile_image_url")
                if pic_url and ("cdninstagram.com" in pic_url or "fbcdn.net" in pic_url):
                    logger.debug(f"Found avatar via PrivateAPIVisitor for {username}")
                    return pic_url
        except FileNotFoundError:
            logger.warning("storage_state.json not found, falling back to unauthenticated HTML scraping")
        except PrivateAPINotFound:
            logger.info(f"Account {username} not found via Private API")
            return None
        except (PrivateAPIRateLimited, PrivateAPIAuthError, Exception) as e:
            logger.warning(f"PrivateAPIVisitor failed for {username}: {type(e).__name__} - {e}")

        # ---------- Strategy 2: HTML scraping (fallback, no cookies) ----------
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            page_url = f"https://www.instagram.com/{username}/"
            page_headers = get_browser_headers()
            response = await client.get(page_url, headers=page_headers)

            if response.status_code == 200:
                html = response.text
                if "loginAndSignupOpen" not in html and "Login • Instagram" not in html:
                    og_match = re.search(r'<meta property="og:image" content="([^"]+)"', html)
                    if og_match:
                        img_url = og_match.group(1).replace("&amp;", "&")
                        if "cdninstagram.com" in img_url or "fbcdn.net" in img_url:
                            logger.debug(f"Found og:image for {username}")
                            return img_url
            else:
                logger.warning(f"Failed to fetch profile for fallback scraping {username}: {response.status_code}")

    except httpx.TimeoutException:
        logger.warning(f"Timeout fetching avatar for {username}")
    except Exception as e:
        logger.error(f"Error fetching avatar URL for {username}: {e}")

    return None


async def download_avatar(url: str, cache_path: Path) -> bool:
    """Download avatar image to cache, using IG session cookies for CDN auth."""
    try:
        AVATAR_CACHE_DIR.mkdir(parents=True, exist_ok=True)

        # Load IG session cookies for CDN authentication
        cookies = {}
        _storage_state = Path(
            os.environ.get("DATA_DIR", "data")
        ) / "ig-browser-profiles" / "default" / "storage_state.json"
        if _storage_state.exists():
            try:
                import json as _json
                with _storage_state.open() as f:
                    state = _json.load(f)
                for c in state.get("cookies", []):
                    if "instagram.com" in c.get("domain", ""):
                        cookies[c["name"]] = c["value"]
            except Exception:
                pass

        cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items()) if cookies else ""

        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            headers = {
                "User-Agent": random.choice(USER_AGENTS),
                "Accept": "image/avif,image/webp,image/apng,*/*",
                "Referer": "https://www.instagram.com/",
            }
            if cookie_header:
                headers["Cookie"] = cookie_header

            response = await client.get(url, headers=headers)

            if response.status_code == 200 and len(response.content) > 100:
                cache_path.write_bytes(response.content)
                logger.info(f"Cached avatar: {cache_path} ({len(response.content)} bytes)")
                return True
            else:
                logger.warning(f"Avatar download failed for {cache_path.stem}: status={response.status_code}, size={len(response.content)}")

    except Exception as e:
        logger.error(f"Error downloading avatar for {cache_path.stem if 'cache_path' in dir() else 'unknown'}: {e}")

    return False


async def get_default_avatar(username: str) -> Response:
    """Generate a default avatar using DiceBear API."""
    try:
        url = f"https://api.dicebear.com/7.x/initials/svg?seed={username}&backgroundColor=6366f1"

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            if response.status_code == 200:
                return Response(
                    content=response.content,
                    media_type="image/svg+xml",
                    headers={"Cache-Control": "public, max-age=300"},
                )
    except Exception as e:
        logger.warning(f"Failed to get default avatar: {e}")

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" viewBox="0 0 100 100">
        <rect width="100" height="100" fill="#6366f1"/>
        <text x="50" y="60" text-anchor="middle" fill="white" font-size="40" font-family="sans-serif">
            {username[0].upper() if username else "?"}
        </text>
    </svg>"""
    return Response(
        content=svg.encode(),
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=300"},
    )


def _get_db_avatar_url_sync(username: str) -> str | None:
    """Synchronous DB query — must be called via asyncio.to_thread."""
    try:
        from app.database.engine import engine_postgres_core
        from sqlalchemy import text

        with engine_postgres_core.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT profile_picture_url FROM ig_accounts_flat "
                    "WHERE handle = :handle AND profile_picture_url IS NOT NULL "
                    "ORDER BY captured_at DESC LIMIT 1"
                ),
                {"handle": username},
            )
            row = result.fetchone()
            if row and row[0]:
                return row[0]
    except Exception as e:
        logger.warning(f"DB avatar lookup failed for {username}: {e}")
    return None


async def _get_db_avatar_url(username: str) -> str | None:
    """Non-blocking wrapper — runs sync DB call in thread pool."""
    import asyncio

    return await asyncio.to_thread(_get_db_avatar_url_sync, username)


import asyncio
from fastapi import BackgroundTasks

async def _refresh_avatar_background(username: str, cache_path: Path):
    """Background task to fetch and update stale avatar."""
    try:
        logger.debug(f"Starting background refresh for avatar: {username}")
        db_url = await _get_db_avatar_url(username)
        if db_url:
            success = await download_avatar(db_url, cache_path)
            if success:
                logger.debug(f"Background refresh succeeded using DB URL: {username}")
                return
        
        fresh_url = await fetch_avatar_url(username)
        if fresh_url:
            success = await download_avatar(fresh_url, cache_path)
            if success:
                logger.debug(f"Background refresh succeeded using fresh IG scrape: {username}")
    except Exception as e:
        logger.warning(f"Background refresh failed for {username}: {e}")

async def _fetch_and_cache(username: str, cache_path: Path) -> bool:
    """Helper to perform fetching and caching logic."""
    db_url = await _get_db_avatar_url(username)
    if db_url:
        success = await download_avatar(db_url, cache_path)
        if success and cache_path.exists():
            return True

    fresh_url = await fetch_avatar_url(username)
    if fresh_url:
        success = await download_avatar(fresh_url, cache_path)
        if success and cache_path.exists():
            return True
            
    return False

@router.get("/avatar/{username}")
async def get_avatar(
    background_tasks: BackgroundTasks,
    username: str = PathParam(..., description="Instagram username")
):
    """
    Get Instagram profile picture with caching.
    """
    cache_path = get_cache_path(username)

    if cache_path.exists():
        is_svg = b"<svg" in cache_path.read_bytes()[:100].lower()
        if is_cache_valid(cache_path):
            return FileResponse(
                cache_path,
                media_type="image/svg+xml" if is_svg else "image/jpeg",
                headers={"Cache-Control": "public, max-age=86400"},
            )
        else:
            # Stale cache — serve immediately, refresh in background
            logger.info(f"Serving stale cached avatar for {username}, refreshing in background")
            background_tasks.add_task(_refresh_avatar_background, username, cache_path)
            return FileResponse(
                cache_path,
                media_type="image/svg+xml" if is_svg else "image/jpeg",
                headers={"Cache-Control": "public, max-age=3600"},
            )

    # No local cache exists. We return default avatar immediately to prevent thread blocking,
    # and fetch the real avatar in the background so it will be ready for the next request.
    logger.info(f"No local cache for {username}, returning fallback and fetching in background")
    background_tasks.add_task(_refresh_avatar_background, username, cache_path)
    
    response = await get_default_avatar(username)
    return response

@router.post("/avatar/batch-refresh")
async def batch_refresh_avatars(
    usernames: list[str],
    force: bool = False,
    max_count: int = 50,
):
    """
    Batch refresh avatars with rate limiting to avoid Instagram detection.

    - Delays 2-3 seconds between each request (with random jitter)
    - Only refreshes expired avatars (>7 days old) unless force=True
    - Limited to max_count per request (default 50)
    """
    import asyncio

    usernames = usernames[:max_count]  # Enforce limit

    refreshed = []
    skipped = []
    failed = []

    for i, username in enumerate(usernames):
        username = username.strip().lstrip("@")
        if not username:
            continue

        cache_path = get_cache_path(username)

        # Skip if cache is still valid (unless force=True)
        if not force and is_cache_valid(cache_path):
            skipped.append(username)
            continue

        # Rate limiting: 2-3s delay with random jitter (skip first request)
        if i > 0:
            delay = 2.0 + random.random()  # 2.0 - 3.0 seconds
            await asyncio.sleep(delay)

        # Attempt to fetch and cache avatar
        try:
            avatar_url = await fetch_avatar_url(username)
            if avatar_url:
                success = await download_avatar(avatar_url, cache_path)
                if success:
                    refreshed.append(username)
                    logger.info(f"Refreshed avatar for {username}")
                else:
                    failed.append(username)
            else:
                failed.append(username)
        except Exception as e:
            logger.warning(f"Failed to refresh avatar for {username}: {e}")
            failed.append(username)

    return {
        "refreshed": refreshed,
        "skipped": skipped,
        "failed": failed,
        "summary": {
            "refreshed_count": len(refreshed),
            "skipped_count": len(skipped),
            "failed_count": len(failed),
        },
    }
