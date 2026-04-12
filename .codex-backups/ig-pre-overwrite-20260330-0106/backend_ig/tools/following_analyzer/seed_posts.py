"""
Seed Posts Extraction Module.

Extracts the seed account's own posts (grid and reels) and persists
them to the ig_posts table.
"""

import asyncio
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from playwright.async_api import Page

from .utils import random_delay

logger = logging.getLogger(__name__)


async def extract_seed_posts(
    page: Page,
    seed_handle: str,
    workspace_id: str,
    target_count: int = 30,
    trace_id: Optional[str] = None,
) -> int:
    """
    Extract the seed account's own posts and persist to ig_posts.

    Called automatically before the scroll phase to ensure the seed's Posts
    tab is populated.  Checks DB first; skips if already have enough.

    Returns the number of posts persisted in this call.
    """
    logger.info(
        f"[SeedPosts] Starting seed post extraction for @{seed_handle} "
        f"(target={target_count})"
    )

    # ── Check DB for existing posts ──────────────────────────────
    existing_count = 0
    try:
        from sqlalchemy import create_engine, text as sa_text

        try:
            from app.database.config import get_postgres_url_core

            engine = create_engine(get_postgres_url_core())
        except ImportError:
            from backend.app.core.database import get_db_engine

            engine = get_db_engine()

        with engine.connect() as conn:
            # Check if ig_posts table exists
            tbl = conn.execute(
                sa_text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_name = 'ig_posts' LIMIT 1"
                )
            ).fetchone()
            if not tbl:
                logger.info(
                    "[SeedPosts] ig_posts table does not exist yet, will create rows"
                )
            else:
                row = conn.execute(
                    sa_text(
                        "SELECT COUNT(*) FROM ig_posts "
                        "WHERE workspace_id = :wid AND account_handle = :handle"
                    ),
                    {"wid": workspace_id, "handle": seed_handle},
                ).fetchone()
                existing_count = row[0] if row else 0

        if existing_count >= target_count:
            logger.info(
                f"[SeedPosts] Already have {existing_count} posts for @{seed_handle} "
                f"(>= target {target_count}), skipping extraction"
            )
            return 0
    except Exception as e:
        logger.debug(f"[SeedPosts] DB check failed, proceeding with extraction: {e}")

    remaining = target_count - existing_count
    logger.info(
        f"[SeedPosts] Need {remaining} more posts "
        f"(existing={existing_count}, target={target_count})"
    )

    # ── Ensure we're on the seed profile page ────────────────────
    current_url = (page.url or "").rstrip("/").lower()
    expected_suffix = f"instagram.com/{seed_handle.lower()}"
    if not current_url.endswith(expected_suffix):
        await page.goto(
            f"https://www.instagram.com/{seed_handle}/",
            wait_until="domcontentloaded",
            timeout=30000,
        )
        try:
            await page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        await asyncio.sleep(random_delay(1, 2))

    # ── Extract grid post links (scroll for more if needed) ──────
    grid_posts = []
    seen_shortcodes = set()

    async def _collect_visible_posts():
        links = await page.locator("a[href*='/p/'], a[href*='/reel/']").all()
        for link in links:
            try:
                href = await link.get_attribute("href")
                if not href:
                    continue
                shortcode = None
                post_type = "image"
                if "/p/" in href:
                    shortcode = href.split("/p/")[1].strip("/").split("/")[0]
                elif "/reel/" in href:
                    shortcode = href.split("/reel/")[1].strip("/").split("/")[0]
                    post_type = "reel"
                if not shortcode or shortcode in seen_shortcodes:
                    continue
                seen_shortcodes.add(shortcode)
                thumbnail_url = None
                try:
                    img = link.locator("img").first
                    if await img.count() > 0:
                        thumbnail_url = await img.get_attribute("src")
                except Exception:
                    pass
                grid_posts.append(
                    {
                        "post_shortcode": shortcode,
                        "post_type": post_type,
                        "post_url": f"https://www.instagram.com{href}",
                        "thumbnail_url": thumbnail_url,
                        "account_handle": seed_handle,
                    }
                )
            except Exception:
                continue

    await _collect_visible_posts()

    # Scroll profile grid to load more posts if we don't have enough
    max_scroll_attempts = 8
    for attempt in range(max_scroll_attempts):
        if len(grid_posts) >= target_count:
            break
        prev_count = len(grid_posts)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(random_delay(1.5, 3))
        await _collect_visible_posts()
        if len(grid_posts) == prev_count:
            break  # No new posts loaded

    logger.info(f"[SeedPosts] Collected {len(grid_posts)} post links from grid")

    # ── Visit each post page for caption + engagement ────────────
    posts_to_visit = grid_posts[:target_count]
    for i, post in enumerate(posts_to_visit):
        try:
            await page.goto(
                post["post_url"],
                wait_until="domcontentloaded",
                timeout=20000,
            )
            await asyncio.sleep(random_delay(1, 2))

            # Extract caption
            caption = None
            caption_selectors = [
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
                    else:
                        elem = page.locator(selector).first
                        if await elem.count() > 0:
                            caption = await elem.text_content()
                    if caption:
                        caption = caption.strip()
                        break
                except Exception:
                    continue
            post["caption"] = caption

            # Extract like count
            try:
                likes_el = page.locator(
                    "section span:has-text('likes'), section button:has-text('likes')"
                )
                if await likes_el.count() > 0:
                    likes_text = await likes_el.first.text_content()
                    m = re.search(r"([\d,]+)", likes_text or "")
                    if m:
                        post["like_count"] = int(m.group(1).replace(",", ""))
            except Exception:
                pass

            if (i + 1) % 5 == 0:
                logger.info(f"[SeedPosts] Visited {i + 1}/{len(posts_to_visit)} posts")

        except Exception as e:
            logger.debug(
                f"[SeedPosts] Error visiting post {post.get('post_shortcode')}: {e}"
            )
            continue

    # ── Persist to ig_posts ──────────────────────────────────────
    persisted = 0
    try:
        from sqlalchemy import create_engine, text as sa_text

        try:
            from app.database.config import get_postgres_url_core

            engine = create_engine(get_postgres_url_core())
        except ImportError:
            from backend.app.core.database import get_db_engine

            engine = get_db_engine()

        now = datetime.now(timezone.utc)
        with engine.connect() as conn:
            # Ensure table exists
            tbl = conn.execute(
                sa_text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_name = 'ig_posts' LIMIT 1"
                )
            ).fetchone()
            if not tbl:
                logger.warning(
                    "[SeedPosts] ig_posts table does not exist, skipping persist"
                )
                return 0

            for post in posts_to_visit:
                try:
                    # Use savepoint so one row failure doesn't poison the transaction
                    conn.execute(sa_text("SAVEPOINT sp_post"))
                    conn.execute(
                        sa_text(
                            """
                            INSERT INTO ig_posts (
                                id, workspace_id, account_handle, post_shortcode,
                                post_type, post_url, thumbnail_url,
                                caption, like_count,
                                captured_at, trace_id
                            ) VALUES (
                                :id, :workspace_id, :account_handle, :post_shortcode,
                                :post_type, :post_url, :thumbnail_url,
                                :caption, :like_count,
                                :captured_at, :trace_id
                            )
                            ON CONFLICT (workspace_id, account_handle, post_shortcode)
                            DO UPDATE SET
                                thumbnail_url = COALESCE(EXCLUDED.thumbnail_url, ig_posts.thumbnail_url),
                                caption = COALESCE(EXCLUDED.caption, ig_posts.caption),
                                like_count = COALESCE(EXCLUDED.like_count, ig_posts.like_count),
                                captured_at = EXCLUDED.captured_at
                        """
                        ),
                        {
                            "id": str(uuid.uuid4()),
                            "workspace_id": workspace_id,
                            "account_handle": post.get("account_handle", seed_handle),
                            "post_shortcode": post["post_shortcode"],
                            "post_type": post.get("post_type", "image"),
                            "post_url": post.get("post_url"),
                            "thumbnail_url": post.get("thumbnail_url"),
                            "caption": post.get("caption"),
                            "like_count": post.get("like_count"),
                            "captured_at": now,
                            "trace_id": trace_id,
                        },
                    )
                    conn.execute(sa_text("RELEASE SAVEPOINT sp_post"))
                    persisted += 1
                except Exception as e:
                    conn.execute(sa_text("ROLLBACK TO SAVEPOINT sp_post"))
                    logger.debug(
                        f"[SeedPosts] Failed to upsert post {post.get('post_shortcode')}: {e}"
                    )
            conn.commit()

    except Exception as e:
        logger.warning(f"[SeedPosts] DB persist error: {e}")

    logger.info(
        f"[SeedPosts] Completed: persisted {persisted} posts for @{seed_handle}"
    )
    return persisted
