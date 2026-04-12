"""
IG Content Analyzer Tool

Extracts posts from IG accounts and persists with topic classification.
Operates in three modes:
- extract_only: Crawl posts, return captions for LLM classification
- persist: Write posts with topics to DB (requires topics_from_llm)
- full: Both extract and persist (for non-LLM use cases)
"""

import json
import logging
import re
import uuid
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


from typing import Any, Dict, List, Optional

from playwright.async_api import async_playwright, Page

from capabilities.ig.source_filters import confirmed_target_condition_sql

logger = logging.getLogger(__name__)


def _extract_hashtags(text: str) -> List[str]:
    """Extract hashtags from text."""
    if not text:
        return []
    return re.findall(r"#(\w+)", text)


def _extract_mentions(text: str) -> List[str]:
    """Extract @mentions from text."""
    if not text:
        return []
    return re.findall(r"@(\w+)", text)


async def _extract_posts_from_page(
    page: Page,
    account_handle: str,
    posts_per_account: int = 9,
) -> List[Dict[str, Any]]:
    """
    Extract recent posts from an IG profile page.
    Returns list of post metadata.
    """
    posts = []

    try:
        # Navigate to account page
        url = f"https://www.instagram.com/{account_handle}/"
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)

        # Check if page exists
        if "Page Not Found" in await page.title():
            logger.warning(f"[IGContentAnalyzer] Account not found: {account_handle}")
            return []

        # Find post links
        post_links = await page.locator("a[href*='/p/'], a[href*='/reel/']").all()

        for i, link in enumerate(post_links[:posts_per_account]):
            try:
                href = await link.get_attribute("href")
                if not href:
                    continue

                # Extract shortcode from URL
                shortcode = None
                if "/p/" in href:
                    shortcode = href.split("/p/")[1].strip("/").split("/")[0]
                    post_type = "image"
                elif "/reel/" in href:
                    shortcode = href.split("/reel/")[1].strip("/").split("/")[0]
                    post_type = "reel"

                if not shortcode:
                    continue

                # Get thumbnail
                thumbnail_url = None
                try:
                    img = link.locator("img").first
                    if await img.count() > 0:
                        thumbnail_url = await img.get_attribute("src")
                except Exception:
                    pass

                posts.append(
                    {
                        "account_handle": account_handle,
                        "post_shortcode": shortcode,
                        "post_type": post_type,
                        "post_url": f"https://www.instagram.com{href}",
                        "thumbnail_url": thumbnail_url,
                        "caption": None,  # Will be filled by visiting post page
                        "like_count": None,
                        "comment_count": None,
                    }
                )

            except Exception as e:
                logger.warning(f"[IGContentAnalyzer] Error extracting post link: {e}")
                continue

        # Visit each post to get caption
        for post in posts:
            try:
                await page.goto(
                    post["post_url"], wait_until="networkidle", timeout=20000
                )
                await page.wait_for_timeout(1500)

                # Extract caption
                caption_selectors = [
                    "article span:has(> a[href*='explore/tags'])",
                    "article h1 + span",
                    "article div[role='button'] > span",
                    "meta[property='og:description']",
                ]

                for selector in caption_selectors:
                    try:
                        if selector.startswith("meta"):
                            elem = page.locator(selector)
                            if await elem.count() > 0:
                                caption = await elem.get_attribute("content")
                                if caption:
                                    post["caption"] = caption
                                    break
                        else:
                            elem = page.locator(selector).first
                            if await elem.count() > 0:
                                caption = await elem.text_content()
                                if caption:
                                    post["caption"] = caption.strip()
                                    break
                    except Exception:
                        continue

                # Extract engagement counts
                try:
                    likes_elem = page.locator(
                        "section span:has-text('likes'), section button:has-text('likes')"
                    )
                    if await likes_elem.count() > 0:
                        likes_text = await likes_elem.first.text_content()
                        # Parse "1,234 likes" -> 1234
                        match = re.search(r"([\d,]+)", likes_text or "")
                        if match:
                            post["like_count"] = int(match.group(1).replace(",", ""))
                except Exception:
                    pass

            except Exception as e:
                logger.warning(
                    f"[IGContentAnalyzer] Error visiting post {post['post_shortcode']}: {e}"
                )

    except Exception as e:
        logger.error(
            f"[IGContentAnalyzer] Error extracting posts from {account_handle}: {e}"
        )

    return posts


async def ig_content_analyzer(
    workspace_id: str,
    seed: str,
    mode: str = "full",  # "extract_only" | "persist" | "full"
    target_handles: Optional[List[str]] = None,
    posts_per_account: int = 9,
    user_data_dir: str = "/app/data/ig-browser-profiles/default",
    trace_id: Optional[str] = None,
    topics_from_llm: Optional[List[Dict[str, str]]] = None,
    posts_meta: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Extract posts and persist with topic tags.

    Modes:
    - extract_only: Crawl posts, return captions for LLM classification
    - persist: Write posts + topics to DB (requires topics_from_llm + posts_meta)
    - full: Both extract and persist (for non-LLM use cases)

    NOTE: Tool does NOT call LLM directly.
          Topic classification is done via Playbook Step.
    """
    logger.info(f"[IGContentAnalyzer] Starting content analysis")
    logger.info(f"  workspace_id: {workspace_id}")
    logger.info(f"  seed: {seed}")
    logger.info(f"  mode: {mode}")
    logger.info(f"  target_handles: {target_handles}")
    logger.info(f"  posts_per_account: {posts_per_account}")

    all_posts: List[Dict[str, Any]] = []
    captions_for_llm: List[Dict[str, str]] = []

    # Mode: persist - just write to DB using provided data
    if mode == "persist":
        if not posts_meta:
            return {
                "status": "error",
                "error": "persist mode requires posts_meta",
            }

        # Merge topics with posts
        topic_map: Dict[str, str] = {}
        if topics_from_llm:
            for item in topics_from_llm:
                shortcode = item.get("shortcode")
                topic = item.get("topic")
                if shortcode and topic:
                    topic_map[shortcode] = topic

        for post in posts_meta:
            shortcode = post.get("post_shortcode")
            if shortcode and shortcode in topic_map:
                post["caption_topic"] = topic_map[shortcode]

        all_posts = posts_meta

    # Mode: extract_only or full - crawl posts
    elif mode in ("extract_only", "full"):
        # Get target handles from ig_accounts_flat if not provided
        if not target_handles:
            try:
                from sqlalchemy import create_engine, text

                try:
                    from app.database.config import get_postgres_url_core

                    engine = create_engine(get_postgres_url_core())
                except ImportError:
                    from backend.app.core.database import get_db_engine

                    engine = get_db_engine()
                with engine.connect() as conn:
                    result = conn.execute(
                        text(
                            """
                        SELECT DISTINCT handle FROM ig_accounts_flat
                        WHERE workspace_id = :workspace_id
                          AND seed = :seed
                          AND """
                            + confirmed_target_condition_sql()
                            + """
                        LIMIT 50
                    """
                        ),
                        {"workspace_id": workspace_id, "seed": seed},
                    )
                    target_handles = [row[0] for row in result.fetchall()]
            except Exception as e:
                logger.warning(f"[IGContentAnalyzer] Failed to get target handles: {e}")
                target_handles = []

        if not target_handles:
            return {
                "status": "error",
                "error": "No target handles found or provided",
            }

        logger.info(f"[IGContentAnalyzer] Processing {len(target_handles)} accounts")

        # Extract posts using unified BrowserSession
        try:
            from .following_analyzer.browser_session import BrowserSession

            async with BrowserSession(user_data_dir) as (browser, context, page):
                for handle in target_handles[:10]:  # Limit for safety
                    posts = await _extract_posts_from_page(
                        page, handle, posts_per_account
                    )
                    all_posts.extend(posts)

                    # Collect captions for LLM
                    for post in posts:
                        if post.get("caption"):
                            captions_for_llm.append(
                                {
                                    "shortcode": post["post_shortcode"],
                                    "caption": post["caption"],
                                }
                            )

                    # Random delay between accounts
                    await page.wait_for_timeout(
                        2000 + int(1000 * __import__("random").random())
                    )

        except Exception as e:
            logger.error(f"[IGContentAnalyzer] Browser error: {e}")
            return {
                "status": "error",
                "error": str(e),
            }

    # Extract hashtags and mentions for all posts
    for post in all_posts:
        caption = post.get("caption") or ""
        post["hashtags_json"] = json.dumps(
            _extract_hashtags(caption), ensure_ascii=False
        )
        post["mentions_json"] = json.dumps(
            _extract_mentions(caption), ensure_ascii=False
        )

    # Mode: extract_only - return data for LLM without persisting
    if mode == "extract_only":
        return {
            "status": "success",
            "mode": "extract_only",
            "captions": captions_for_llm,
            "posts_meta": all_posts,
            "total_posts": len(all_posts),
        }

    # Mode: persist or full - write to database
    persisted_count = 0
    try:
        from sqlalchemy import create_engine, text

        try:
            from app.database.config import get_postgres_url_core

            engine = create_engine(get_postgres_url_core())
        except ImportError:
            from backend.app.core.database import get_db_engine

            engine = get_db_engine()
        with engine.connect() as conn:
            for post in all_posts:
                try:
                    stmt = text(
                        """
                        INSERT INTO ig_posts (
                            id, workspace_id, account_handle, post_shortcode,
                            post_type, post_url, thumbnail_url,
                            like_count, comment_count,
                            caption, hashtags_json, mentions_json,
                            caption_topic, caption_sentiment, caption_locale,
                            captured_at, execution_id, trace_id
                        ) VALUES (
                            :id, :workspace_id, :account_handle, :post_shortcode,
                            :post_type, :post_url, :thumbnail_url,
                            :like_count, :comment_count,
                            :caption, :hashtags_json, :mentions_json,
                            :caption_topic, :caption_sentiment, :caption_locale,
                            :captured_at, :execution_id, :trace_id
                        )
                        ON CONFLICT (workspace_id, account_handle, post_shortcode)
                        DO UPDATE SET
                            caption = EXCLUDED.caption,
                            like_count = EXCLUDED.like_count,
                            comment_count = EXCLUDED.comment_count,
                            caption_topic = COALESCE(EXCLUDED.caption_topic, ig_posts.caption_topic),
                            captured_at = EXCLUDED.captured_at
                    """
                    )

                    conn.execute(
                        stmt,
                        {
                            "id": str(uuid.uuid4()),
                            "workspace_id": workspace_id,
                            "account_handle": post.get("account_handle"),
                            "post_shortcode": post.get("post_shortcode"),
                            "post_type": post.get("post_type"),
                            "post_url": post.get("post_url"),
                            "thumbnail_url": post.get("thumbnail_url"),
                            "like_count": post.get("like_count"),
                            "comment_count": post.get("comment_count"),
                            "caption": post.get("caption"),
                            "hashtags_json": post.get("hashtags_json"),
                            "mentions_json": post.get("mentions_json"),
                            "caption_topic": post.get("caption_topic"),
                            "caption_sentiment": post.get("caption_sentiment"),
                            "caption_locale": post.get("caption_locale"),
                            "captured_at": _utc_now(),
                            "execution_id": trace_id,
                            "trace_id": trace_id,
                        },
                    )
                    persisted_count += 1
                except Exception as e:
                    logger.warning(f"[IGContentAnalyzer] Failed to persist post: {e}")

            conn.commit()

    except Exception as e:
        logger.error(f"[IGContentAnalyzer] Database error: {e}")
        return {
            "status": "error",
            "error": str(e),
        }

    result = {
        "status": "success",
        "mode": mode,
        "total_posts": len(all_posts),
        "persisted_count": persisted_count,
        "workspace_id": workspace_id,
        "seed": seed,
    }

    if mode == "full":
        result["captions"] = captions_for_llm
        result["posts_meta"] = all_posts

    logger.info(f"[IGContentAnalyzer] Completed: {result}")
    return result
