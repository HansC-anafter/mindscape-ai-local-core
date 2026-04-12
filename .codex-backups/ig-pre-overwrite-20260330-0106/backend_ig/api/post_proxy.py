"""Post Proxy API."""

import logging
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from capabilities.ig.services.thumbnail_fetcher import (
    fetch_thumbnail_bytes,
    is_placeholder_thumbnail_content,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["IG Post Proxy"])

# Cache settings
CACHE_DIR = Path() / "data" / "ig_thumbnails"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_EXPIRE_SECONDS = 7 * 24 * 60 * 60  # 7 days


def _cached_thumbnail_is_valid(cache_path: Path) -> bool:
    try:
        content = cache_path.read_bytes()
    except Exception as exc:
        logger.warning("[PostProxy] Failed to read cache %s: %s", cache_path.name, exc)
        return False

    if is_placeholder_thumbnail_content(content):
        logger.warning("[PostProxy] Discarding placeholder cache for %s", cache_path.stem)
        try:
            cache_path.unlink(missing_ok=True)
        except Exception as exc:
            logger.warning("[PostProxy] Failed to remove invalid cache %s: %s", cache_path.name, exc)
        return False

    return True

@router.get("/post-thumbnail/{shortcode}")
async def get_post_thumbnail(shortcode: str):
    """
    Get a fresh post thumbnail.
    Checks cache first. If missing/expired, tries DB thumbnail URL, then IG embed, then BrowserSession.
    """
    if not shortcode or not shortcode.isalnum() and "_" not in shortcode and "-" not in shortcode:
        raise HTTPException(status_code=400, detail="Invalid shortcode")

    cache_path = CACHE_DIR / f"{shortcode}.jpg"

    # 1. Check Cache
    if cache_path.exists():
        age = time.time() - cache_path.stat().st_mtime
        if age < CACHE_EXPIRE_SECONDS and _cached_thumbnail_is_valid(cache_path):
            return FileResponse(cache_path, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})
        if age >= CACHE_EXPIRE_SECONDS:
            logger.info(f"[PostProxy] Cache expired for {shortcode}, refreshing...")
        else:
            logger.info(f"[PostProxy] Cache invalid for {shortcode}, refreshing...")

    # 2. Resolve a fresh thumbnail via shared IG fetch strategy and refresh cache.
    try:
        downloaded = await fetch_thumbnail_bytes(shortcode, timeout=15.0)
        cache_path.write_bytes(downloaded.content)
        logger.info(
            "[PostProxy] Successfully cached fresh thumbnail for %s via %s",
            shortcode,
            downloaded.source,
        )
        return FileResponse(
            cache_path,
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=86400"},
        )
    except Exception as exc:
        logger.debug("[PostProxy] All live fetch methods failed for %s: %s", shortcode, exc)

    # 5. All methods exhausted — serve stale cache or 404
    if cache_path.exists() and _cached_thumbnail_is_valid(cache_path):
        logger.warning(f"[PostProxy] Serving stale cache for {shortcode} (all live methods failed)")
        return FileResponse(cache_path, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})

    logger.warning(f"[PostProxy] Exhausted all extraction methods for {shortcode}")
    raise HTTPException(status_code=404, detail="Could not extract thumbnail URL")
