"""
ig_batch_pin_tool — Automatically scroll account page and batch pin grid posts.

Flow:
  1. Open target Instagram account page.
  2. Scroll down repeatedly to load posts until the target_count is met or no more items load.
  3. Extract shortcodes and thumbnails.
  4. Pass each item to `ig_pin_reference` for background download & deduplication.

Alternate mode:
  - source_mode="captured_posts": read already captured posts from ig_posts /
    ig_accounts_flat.grid_posts_json and feed them into the same pin/analyze flow
    without touching the browser again.
"""

import asyncio
import json
import logging
import re
import traceback
from collections import Counter
from typing import Any, Dict, List, Optional, Set

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from capabilities.ig.services.pin_failed_attempt_store import PostgresIGPinFailedAttemptStore
from capabilities.ig.services.reference_index import ReferenceIndex
from capabilities.ig.services.workspace_storage import WorkspaceStorage
from capabilities.ig.tools.following_analyzer.browser_session import BrowserSession
from capabilities.ig.tools.ig_pin_reference import ig_pin_reference

logger = logging.getLogger(__name__)


def _normalize_shortcode(shortcode: str | None) -> str:
    return re.sub(r"_c\d+$", "", (shortcode or "").strip(), flags=re.IGNORECASE)


def _get_existing_reference_shortcodes(
    workspace_id: str,
    target_handle: str,
) -> Set[str]:
    storage = WorkspaceStorage(workspace_id, "ig")
    index = ReferenceIndex(storage.get_references_path())
    entries = index.query(source_handle=target_handle)
    shortcodes: Set[str] = set()
    for entry in entries:
        normalized = _normalize_shortcode(entry.get("source_shortcode"))
        if normalized:
            shortcodes.add(normalized)
    return shortcodes


def _add_candidate_post(
    posts_data: Dict[str, Dict[str, str]],
    *,
    shortcode: str | None,
    thumbnail_url: str | None,
    post_url: str | None = None,
    post_type: str | None = None,
    exclude_shortcodes: Optional[Set[str]] = None,
) -> None:
    normalized_shortcode = _normalize_shortcode(shortcode)
    excluded = exclude_shortcodes or set()
    if (
        not normalized_shortcode
        or normalized_shortcode in excluded
        or normalized_shortcode in posts_data
        or not thumbnail_url
    ):
        return

    clean_post_type = (post_type or "image").lower()
    post_kind = "reel" if "reel" in clean_post_type else "p"
    resolved_post_url = post_url or f"https://www.instagram.com/{post_kind}/{normalized_shortcode}/"

    posts_data[normalized_shortcode] = {
        "shortcode": normalized_shortcode,
        "thumbnail_url": thumbnail_url,
        "post_url": resolved_post_url,
        "post_type": clean_post_type,
    }


def _get_captured_posts(
    workspace_id: str,
    target_handle: str,
    target_count: int,
    *,
    exclude_shortcodes: Optional[Set[str]] = None,
) -> List[Dict[str, str]]:
    posts_data: Dict[str, Dict[str, str]] = {}
    normalized_handle = (target_handle or "").lstrip("@").strip()
    excluded = {
        _normalize_shortcode(shortcode)
        for shortcode in (exclude_shortcodes or set())
        if shortcode
    }

    try:
        from sqlalchemy import create_engine, text

        try:
            from app.database.config import get_postgres_url_core

            engine = create_engine(get_postgres_url_core())
        except ImportError:
            from backend.app.core.database import get_db_engine

            engine = get_db_engine()
    except Exception as e:
        logger.warning(f"[BatchPin] Failed to initialize DB engine for captured_posts: {e}")
        return []

    try:
        with engine.connect() as conn:
            ig_posts_rows = conn.execute(
                text(
                    """
                    SELECT post_shortcode, thumbnail_url, post_url, COALESCE(post_type, 'image') AS post_type
                    FROM ig_posts
                    WHERE workspace_id = :workspace_id
                      AND account_handle = :account_handle
                      AND COALESCE(thumbnail_url, '') <> ''
                    ORDER BY captured_at DESC NULLS LAST, post_shortcode DESC
                    LIMIT :row_limit
                    """
                ),
                {
                    "workspace_id": workspace_id,
                    "account_handle": normalized_handle,
                    "row_limit": max(target_count * 3, 50),
                },
            ).fetchall()

            for row in ig_posts_rows:
                _add_candidate_post(
                    posts_data,
                    shortcode=row[0],
                    thumbnail_url=row[1],
                    post_url=row[2],
                    post_type=row[3],
                    exclude_shortcodes=excluded,
                )
                if len(posts_data) >= target_count:
                    break

            if len(posts_data) < target_count:
                account_row = conn.execute(
                    text(
                        """
                        SELECT grid_posts_json
                        FROM ig_accounts_flat
                        WHERE workspace_id = :workspace_id
                          AND handle = :handle
                          AND COALESCE(grid_posts_json, '') <> ''
                        ORDER BY captured_at DESC NULLS LAST
                        LIMIT 1
                        """
                    ),
                    {
                        "workspace_id": workspace_id,
                        "handle": normalized_handle,
                    },
                ).fetchone()

                if account_row and account_row[0]:
                    try:
                        grid_posts = json.loads(account_row[0])
                    except Exception as parse_err:
                        logger.warning(
                            f"[BatchPin] Failed to parse grid_posts_json for @{normalized_handle}: {parse_err}"
                        )
                        grid_posts = []

                    for post in grid_posts:
                        if not isinstance(post, dict):
                            continue
                        _add_candidate_post(
                            posts_data,
                            shortcode=post.get("post_shortcode"),
                            thumbnail_url=post.get("thumbnail_url"),
                            post_url=post.get("post_url"),
                            post_type=post.get("post_type"),
                            exclude_shortcodes=excluded,
                        )
                        if len(posts_data) >= target_count:
                            break

    except Exception as e:
        logger.warning(f"[BatchPin] Failed to load captured posts for @{normalized_handle}: {e}")
        return []

    return list(posts_data.values())[:target_count]


async def extract_grid_posts(
    page: Page,
    target_count: int,
    *,
    exclude_shortcodes: Optional[Set[str]] = None,
) -> List[Dict[str, str]]:
    """
    Scroll the page to load and extract at least `target_count` grid items.
    Returns early with what it has if blocked by a login wall or no more items load.
    
    Returns a list of dicts: [{"shortcode": "...", "thumbnail_url": "..."}]
    """
    posts_data: Dict[str, Dict[str, str]] = {}
    excluded = {_normalize_shortcode(shortcode) for shortcode in (exclude_shortcodes or set()) if shortcode}
    last_count = 0
    unchanged_scrolls = 0
    max_unchanged = 5  # Give up if no new posts after 5 scrolls

    # IG post links can be /p/XXX/, /reel/XXX/, or /tv/XXX/
    POST_LINK_SELECTOR = "a[href*='/p/'], a[href*='/reel/'], a[href*='/tv/']"
    POST_PREFIXES = {"p", "reel", "tv"}

    logger.info(f"[BatchPin] Starting infinite scroll to collect {target_count} posts...")

    while len(posts_data) < target_count:
        # Check for login wall — specifically the "Log in" button, not any dialog
        # (IG shows div[role='dialog'] for Messages overlay even when logged in)
        login_wall_text = await page.locator("text='Log in'").count()
        login_form = await page.locator("input[name='username']").count()
        if login_wall_text > 0 and login_form > 0:
            logger.warning("[BatchPin] Login wall detected. Gracefully degrading collection.")
            break

        # Extract current visible anchors that look like posts
        links = await page.locator(POST_LINK_SELECTOR).all()
        for link in links:
            try:
                href = await link.get_attribute("href")
                if not href:
                    continue
                # Extrapolate shortcode from "/{username}/p/{shortcode}/" or "/{username}/reel/{shortcode}/"
                parts = [p for p in href.split("/") if p]
                # Find the post type prefix in parts (IG uses /{username}/p/{shortcode}/)
                post_type = None
                shortcode = None
                for idx, part in enumerate(parts):
                    if part in POST_PREFIXES and idx + 1 < len(parts):
                        post_type = part
                        shortcode = parts[idx + 1]
                        break
                if post_type and shortcode:
                    normalized_shortcode = _normalize_shortcode(shortcode)
                    if not normalized_shortcode or normalized_shortcode in excluded:
                        continue
                    # Find image inside the anchor
                    img = link.locator("img")
                    if await img.count() > 0:
                        src = await img.first.get_attribute("src")
                        if src and normalized_shortcode not in posts_data:
                            # Extract Base64 directly from the DOM image to avoid CDN expiration and rate limits
                            base64_img = None
                            try:
                                base64_img = await img.first.evaluate('''
                                    (imgElement) => {
                                        if (!imgElement.complete || imgElement.naturalWidth === 0) return null;
                                        const canvas = document.createElement('canvas');
                                        canvas.width = imgElement.naturalWidth;
                                        canvas.height = imgElement.naturalHeight;
                                        const ctx = canvas.getContext('2d');
                                        if (!ctx) return null;
                                        // Draw the image
                                        ctx.drawImage(imgElement, 0, 0);
                                        // Extract as JPEG data URL
                                        return canvas.toDataURL('image/jpeg', 0.95);
                                    }
                                ''')
                            except Exception as ev_err:
                                logger.debug(f"[BatchPin] Failed to extract base64 for {shortcode}: {ev_err}")

                            posts_data[normalized_shortcode] = {
                                "shortcode": normalized_shortcode,
                                "thumbnail_url": src,
                                "post_url": f"https://www.instagram.com/{post_type}/{normalized_shortcode}/",
                                "base64_image": base64_img,
                            }
            except Exception as e:
                # Elements might be detached during scrolling, ignore
                pass
                
        logger.info(f"[BatchPin] Collected {len(posts_data)}/{target_count} posts so far...")
        if len(posts_data) >= target_count:
            break

        # Check progress
        if len(posts_data) == last_count:
            unchanged_scrolls += 1
            if unchanged_scrolls >= max_unchanged:
                logger.warning(f"[BatchPin] Scrolling stopped loading new items. Collected {len(posts_data)}.")
                break
        else:
            unchanged_scrolls = 0
            last_count = len(posts_data)

        # Scroll down
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        
        # Wait for new content to load
        try:
            await page.wait_for_timeout(2000)
            if len(posts_data) < target_count:
                 await page.wait_for_load_state("networkidle", timeout=3000)
        except PlaywrightTimeoutError:
            pass # Not a big deal, we just keep scrolling

    results = list(posts_data.values())
    # Return exactly target_count if we overshot slightly
    return results[:target_count]


async def ig_batch_pin_tool(
    workspace_id: str,
    target_handle: str,
    target_count: int = 100,
    user_data_dir: str = "/app/data/ig-browser-profiles/default",
    parent_execution_id: Optional[str] = None,
    source_mode: str = "browser",
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Automated Playbook Task corresponding tool.
    Navigates to the IG account, scrolls down to grab `target_count` posts,
    and batches them into Reference API.
    """
    normalized_source_mode = (source_mode or "browser").strip().lower()
    logger.info(
        f"[BatchPin] Starting background batch pin: @{target_handle} x{target_count} "
        f"(source_mode={normalized_source_mode})"
    )

    account_url = f"https://www.instagram.com/{target_handle}/"
    collected_posts: List[Dict[str, str]] = []
    existing_shortcodes = _get_existing_reference_shortcodes(workspace_id, target_handle)
    existing_reference_count_before = len(existing_shortcodes)
    remaining_needed = max(0, target_count - existing_reference_count_before)
    
    resolved_user_data_dir = (user_data_dir or "").strip() or "/app/data/ig-browser-profiles/default"

    if remaining_needed <= 0:
        message = (
            f"Target already satisfied for @{target_handle}. "
            f"Existing references: {existing_reference_count_before}, target: {target_count}."
        )
        logger.info(f"[BatchPin] {message}")
        return {
            "status": "success",
            "message": message,
            "target_count": target_count,
            "existing_reference_count_before": existing_reference_count_before,
            "existing_reference_count_after": existing_reference_count_before,
            "remaining_needed_before": 0,
            "remaining_to_target": 0,
            "target_met": True,
            "collected_count": 0,
            "pinned_count": 0,
            "duplicate_count": 0,
            "failed_count": 0,
        }
    
    if normalized_source_mode == "captured_posts":
        collected_posts = _get_captured_posts(
            workspace_id,
            target_handle,
            remaining_needed,
            exclude_shortcodes=existing_shortcodes,
        )
    else:
        try:
            async with BrowserSession(resolved_user_data_dir) as (browser, context, page):
                logger.info(f"[BatchPin] Navigating to {account_url} with profile {resolved_user_data_dir}")

                await page.goto(account_url, wait_until="domcontentloaded", timeout=45000)

                # Wait for the post grid to actually render (or login wall)
                try:
                    await page.wait_for_selector("a[href*='/p/'], div[role='dialog']", timeout=15000)
                except Exception:
                    pass  # Proceed anyway, extract_grid_posts will handle empty case

                # Give some time for images to load
                await page.wait_for_timeout(3000)

                collected_posts = await extract_grid_posts(
                    page,
                    remaining_needed,
                    exclude_shortcodes=existing_shortcodes,
                )

                if not collected_posts:
                    shot_path = f"/app/data/ig_debug_batch_pin_{target_handle}.png"
                    try:
                        await page.screenshot(path=shot_path)
                        logger.info(f"[BatchPin] Captured debug screenshot to {shot_path}")
                    except Exception as shot_e:
                        logger.warning(f"[BatchPin] Failed to capture debug screenshot: {shot_e}")

        except Exception as e:
            logger.error(f"[BatchPin] Fatal error during collection: {e}")
            logger.error(traceback.format_exc())
            raise RuntimeError(f"Failed to collect posts from page: {str(e)}")

    if not collected_posts:
        if normalized_source_mode == "captured_posts":
            existing_reference_count_after = existing_reference_count_before
            remaining_to_target = max(0, target_count - existing_reference_count_after)
            message = (
                f"No additional captured posts available for @{target_handle}. "
                f"Existing references: {existing_reference_count_before}, target: {target_count}."
            )
            logger.info(f"[BatchPin] {message}")
            return {
                "status": "success",
                "message": message,
                "source_mode": normalized_source_mode,
                "target_count": target_count,
                "existing_reference_count_before": existing_reference_count_before,
                "existing_reference_count_after": existing_reference_count_after,
                "remaining_needed_before": remaining_needed,
                "remaining_to_target": remaining_to_target,
                "target_met": remaining_to_target == 0,
                "collected_count": 0,
                "pinned_count": 0,
                "duplicate_count": 0,
                "failed_count": 0,
            }
        raise RuntimeError(
            f"Found 0 posts for @{target_handle}. Account might be private or blocked by a login wall."
        )
         
    # Proceed to pin all collected posts
    logger.info(f"[BatchPin] Extracted {len(collected_posts)} thumbnails. Triggering ig_pin_reference concurrently...")
    
    pinned_count = 0
    duplicate_count = 0
    failed_count = 0
    failed_items: List[Dict[str, str]] = []
    failure_summary: Counter[str] = Counter()
    
    # We batch them concurrently but with a limit using asyncio.Semaphore so we don't spam httpx
    semaphore = asyncio.Semaphore(5)
    
    async def _safe_pin(post_data: Dict[str, str]):
        nonlocal pinned_count, duplicate_count, failed_count
        async with semaphore:
            try:
                # Prepare kwargs
                pin_kwargs = {
                    "workspace_id": workspace_id,
                    "image_url": post_data["thumbnail_url"],
                    "source_handle": target_handle,
                    "source_shortcode": post_data["shortcode"],
                    "source_url": post_data["post_url"],
                    "tags": ["batch_pin"],
                    "parent_execution_id": parent_execution_id,
                    "trigger": f"batch_pin:{normalized_source_mode}",
                }
                
                # Pass the extracted Base64 image if available
                if "base64_image" in post_data and post_data["base64_image"]:
                    pin_kwargs["base64_image"] = post_data["base64_image"]


                res = await ig_pin_reference(**pin_kwargs)
                if res.get("status") == "duplicate":
                    duplicate_count += 1
                elif res.get("status") == "error":
                    failed_count += 1
                    error_kind = str(res.get("error_kind") or "pin_error")
                    error_message = str(res.get("error") or "Unknown pin error")
                    final_disposition = str(
                        res.get("final_disposition") or "unknown_disposition"
                    )
                    failure_summary[error_kind] += 1
                    if len(failed_items) < 25:
                        failed_items.append(
                            {
                                "shortcode": post_data["shortcode"],
                                "error_kind": error_kind,
                                "error": error_message,
                                "final_disposition": final_disposition,
                            }
                        )
                    logger.warning(
                        "[BatchPin] Pin skipped for %s (%s): %s. No reference created; no analysis enqueued.",
                        post_data["shortcode"],
                        error_kind,
                        error_message,
                    )
                else:
                    pinned_count += 1
                    # Enqueue background analysis for the newly pinned reference
                    if res.get("reference_id"):
                        try:
                            from capabilities.ig.services.auto_analyze import enqueue_reference_analysis
                            enqueue_reference_analysis(
                                workspace_id=workspace_id,
                                reference_id=res["reference_id"],
                                image_url=post_data["thumbnail_url"],
                                source_handle=target_handle,
                                parent_execution_id=parent_execution_id,
                            )
                        except Exception as enq_err:
                            logger.warning(
                                f"[BatchPin] Failed to enqueue analysis for {post_data['shortcode']} (non-fatal): {enq_err}"
                            )
            except Exception as e:
                import traceback
                logger.error(f"[BatchPin] Error pinning shortcode {post_data['shortcode']}: {e}")
                logger.error(traceback.format_exc())
                try:
                    PostgresIGPinFailedAttemptStore().record_failed_attempt(
                        workspace_id=workspace_id,
                        source_handle=target_handle,
                        source_shortcode=post_data.get("shortcode"),
                        source_url=post_data.get("post_url"),
                        image_url=post_data.get("thumbnail_url"),
                        parent_execution_id=parent_execution_id,
                        trigger=f"batch_pin:{normalized_source_mode}",
                        base64_image_present=bool(post_data.get("base64_image")),
                        error_kind="pin_exception",
                        error_message=str(e),
                        failure_payload={
                            "exception_type": type(e).__name__,
                            "shortcode": post_data.get("shortcode"),
                            "source_mode": normalized_source_mode,
                        },
                    )
                except Exception as store_err:
                    logger.warning(
                        "[BatchPin] Failed to persist pin_exception for %s: %s",
                        post_data.get("shortcode"),
                        store_err,
                    )
                failed_count += 1
                failure_summary["pin_exception"] += 1
                if len(failed_items) < 25:
                    failed_items.append(
                        {
                            "shortcode": post_data["shortcode"],
                            "error_kind": "pin_exception",
                            "error": str(e),
                            "final_disposition": "skipped_no_reference",
                        }
                    )

    tasks = [_safe_pin(p) for p in collected_posts]
    await asyncio.gather(*tasks)

    # ── Persist collected posts to ig_posts table for UI grid display ──
    try:
        import uuid
        from datetime import datetime, timezone
        from sqlalchemy import create_engine, text

        try:
            from app.database.config import get_postgres_url_core
            engine = create_engine(get_postgres_url_core())
        except ImportError:
            from backend.app.core.database import get_db_engine
            engine = get_db_engine()

        now = datetime.now(timezone.utc)
        with engine.connect() as conn:
            check = conn.execute(
                text("SELECT 1 FROM information_schema.tables WHERE table_name = 'ig_posts' LIMIT 1")
            ).fetchone()
            if check:
                upserted = 0
                for post_data in collected_posts:
                    sc = post_data.get("shortcode", "")
                    if not sc:
                        continue
                    try:
                        conn.execute(
                            text("""
                                INSERT INTO ig_posts (
                                    id, workspace_id, account_handle, post_shortcode,
                                    post_type, post_url, thumbnail_url, captured_at
                                ) VALUES (
                                    :id, :workspace_id, :account_handle, :post_shortcode,
                                    :post_type, :post_url, :thumbnail_url, :captured_at
                                )
                                ON CONFLICT (workspace_id, account_handle, post_shortcode)
                                DO UPDATE SET
                                    thumbnail_url = COALESCE(EXCLUDED.thumbnail_url, ig_posts.thumbnail_url),
                                    captured_at = EXCLUDED.captured_at
                            """),
                            {
                                "id": str(uuid.uuid4()),
                                "workspace_id": workspace_id,
                                "account_handle": target_handle,
                                "post_shortcode": sc,
                                "post_type": post_data.get("post_type", "image"),
                                "post_url": post_data.get("post_url", f"https://www.instagram.com/p/{sc}/"),
                                "thumbnail_url": post_data.get("thumbnail_url", ""),
                                "captured_at": now,
                            },
                        )
                        upserted += 1
                    except Exception as e:
                        logger.debug(f"[BatchPin] Failed to upsert post {sc}: {e}")
                conn.commit()
                logger.info(f"[BatchPin] Upserted {upserted} posts into ig_posts for @{target_handle}")
    except Exception as db_err:
        logger.warning(f"[BatchPin] ig_posts upsert failed (non-fatal): {db_err}")

    existing_reference_count_after = existing_reference_count_before + pinned_count
    remaining_to_target = max(0, target_count - existing_reference_count_after)
    target_met = remaining_to_target == 0

    result_msg = (
        f"Batch job complete. Target total {target_count}, "
        f"existing before {existing_reference_count_before}, "
        f"needed {remaining_needed}. "
        f"Collected {len(collected_posts)} new candidates from {normalized_source_mode}. "
        f"Results: {pinned_count} new, {duplicate_count} duplicated, {failed_count} failed. "
        f"Total references now {existing_reference_count_after}."
    )
    if failed_count:
        result_msg += " Failed items were skipped without creating references or analysis jobs."
    if not target_met:
        result_msg += f" Still short by {remaining_to_target}."
    logger.info(f"[BatchPin] {result_msg}")
    
    return {
        "status": "success",
        "message": result_msg,
        "source_mode": normalized_source_mode,
        "target_count": target_count,
        "existing_reference_count_before": existing_reference_count_before,
        "existing_reference_count_after": existing_reference_count_after,
        "remaining_needed_before": remaining_needed,
        "remaining_to_target": remaining_to_target,
        "target_met": target_met,
        "collected_count": len(collected_posts),
        "pinned_count": pinned_count,
        "duplicate_count": duplicate_count,
        "failed_count": failed_count,
        "failure_summary": dict(failure_summary),
        "failed_items_sample": failed_items,
    }
