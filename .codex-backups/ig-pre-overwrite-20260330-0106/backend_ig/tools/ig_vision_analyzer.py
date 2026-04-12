"""
IG Vision Analyzer Tool

Analyzes the visual content of an IG account's grid posts using a Multimodal LLM.
"""

import base64
import json
import logging
from io import BytesIO
from typing import Any, Dict, List, Optional

import httpx
from PIL import Image

logger = logging.getLogger(__name__)


async def _download_and_encode_image(url: str, max_size: int = 1024) -> Optional[str]:
    """Download image, downscale if needed, and encode to Base64 JPEG."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        img = Image.open(BytesIO(resp.content))
        if img.mode != "RGB":
            img = img.convert("RGB")

        if max(img.width, img.height) > max_size:
            img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

        buf = BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception as e:
        logger.warning(f"[IGVisionAnalyzer] Failed to download/encode image {url}: {e}")
        return None


async def ig_vision_analyzer(
    workspace_id: str,
    target_username: str,
    max_posts: int = 3,
    execution_context: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Analyzes the visual content of the target account's recent grid posts.

    Reads `grid_posts_json` from the DB, downloads the thumbnails, and uses
    the core multimodal LLM to generate a reverse prompt description.
    Results are saved back to `vision_analysis_json`.
    """
    logger.info(f"[IGVisionAnalyzer] Starting vision analysis for @{target_username}")

    try:
        from sqlalchemy import create_engine, text

        try:
            from app.database.config import get_postgres_url_core

            engine = create_engine(get_postgres_url_core())
        except ImportError:
            from backend.app.core.database import get_db_engine

            engine = get_db_engine()
    except ImportError as e:
        logger.error(f"[IGVisionAnalyzer] Initial DB Import error: {e}")
        return {"status": "error", "error": f"Failed to import database: {e}"}

    # Fetch grid posts
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                    SELECT grid_posts_json FROM ig_accounts_flat
                    WHERE workspace_id = :workspace_id AND handle = :handle
                    """
                ),
                {"workspace_id": workspace_id, "handle": target_username},
            ).fetchone()
    except Exception as e:
        return {"status": "error", "error": f"DB read failed: {e}"}

    if not result or not result[0]:
        return {"status": "skipped", "reason": "No grid_posts_json found"}

    try:
        grid_posts = json.loads(result[0])
    except Exception:
        return {"status": "error", "error": "Invalid grid_posts_json format"}

    if not isinstance(grid_posts, list) or len(grid_posts) == 0:
        return {"status": "skipped", "reason": "Grid posts list is empty"}

    # ── 圖片預處理（不做 LLM 調用，交給 playbook core_llm step） ──
    preprocessed_images = []

    for post in grid_posts[:max_posts]:
        thumbnail_url = post.get("thumbnail_url")
        if not thumbnail_url:
            continue

        b64_img = await _download_and_encode_image(thumbnail_url)
        if not b64_img:
            continue

        preprocessed_images.append(
            {
                "shortcode": post.get("post_shortcode"),
                "base64_jpeg": b64_img,
                "thumbnail_url": thumbnail_url,
            }
        )

    if not preprocessed_images:
        return {
            "status": "skipped",
            "reason": "No valid images downloaded",
        }

    logger.info(
        f"[IGVisionAnalyzer] Preprocessed {len(preprocessed_images)} images for @{target_username}"
    )

    return {
        "status": "success",
        "preprocessed_count": len(preprocessed_images),
        "images": preprocessed_images,
    }
