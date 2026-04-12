"""
ig_fetch_post_detail — Browser-based extraction of single IG post detail.

Navigates to an IG post page and extracts:
  - Caption text
  - Like / comment counts
  - All carousel images (base64 + CDN URL)
  - Media type (IMAGE / VIDEO / CAROUSEL_ALBUM)
  - Post timestamp
  - Source handle

Uses Playwright (consistent with ig_batch_pin_tool.py).
"""

import asyncio
import logging
import re
from typing import Any, Dict, List, Optional

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from capabilities.ig.tools.following_analyzer.browser_session import BrowserSession

logger = logging.getLogger(__name__)

_DEFAULT_PROFILE = "/app/data/ig-browser-profiles/default"


async def _extract_base64_from_img(img_locator) -> Optional[str]:
    """Extract base64 JPEG from an <img> element via canvas toDataURL."""
    try:
        return await img_locator.evaluate('''
            (imgElement) => {
                if (!imgElement.complete || imgElement.naturalWidth === 0) return null;
                const canvas = document.createElement('canvas');
                canvas.width = imgElement.naturalWidth;
                canvas.height = imgElement.naturalHeight;
                const ctx = canvas.getContext('2d');
                if (!ctx) return null;
                ctx.drawImage(imgElement, 0, 0);
                return canvas.toDataURL('image/jpeg', 0.95);
            }
        ''')
    except Exception as e:
        logger.debug(f"[PostDetail] Failed to extract base64: {e}")
        return None


async def _extract_current_slide_image(page: Page) -> Optional[Dict[str, Any]]:
    """Extract the currently visible image in a post or carousel slide."""
    # IG post images are inside article > div ... > img
    # The main content image is typically the largest img inside the post area
    selectors = [
        "article img[style*='object-fit']",
        "article div[role='presentation'] img",
        "article img[srcset]",
        "article div[class] > div > div > img",
    ]

    for selector in selectors:
        imgs = page.locator(selector)
        count = await imgs.count()
        for i in range(count):
            img = imgs.nth(i)
            try:
                src = await img.get_attribute("src")
                # Skip tiny avatar/icon images
                natural_w = await img.evaluate("el => el.naturalWidth")
                if natural_w and natural_w < 200:
                    continue
                if src and ("scontent" in src or "cdninstagram" in src or "fbcdn" in src):
                    base64_data = await _extract_base64_from_img(img)
                    return {
                        "url": src,
                        "base64_jpeg": base64_data,
                    }
            except Exception:
                continue
    return None


async def _extract_caption(page: Page) -> str:
    """Extract post caption text."""
    try:
        # IG stores caption in a span inside h1, or in article > div > span
        caption_selectors = [
            "article h1",
            "article div[class] > span[class]",
        ]
        for sel in caption_selectors:
            loc = page.locator(sel)
            if await loc.count() > 0:
                text = await loc.first.inner_text()
                if text and len(text.strip()) > 5:
                    return text.strip()
    except Exception as e:
        logger.debug(f"[PostDetail] Caption extraction failed: {e}")
    return ""


async def _extract_stats(page: Page) -> Dict[str, Optional[int]]:
    """Extract like count and comment count from post page."""
    stats: Dict[str, Optional[int]] = {"like_count": None, "comment_count": None}

    try:
        # Likes: look for "XX likes" or "XX 個讚" pattern in page text
        like_section = page.locator("section:has(button)")
        if await like_section.count() > 0:
            section_text = await like_section.first.inner_text()
            # Match patterns like "1,234 likes" or "1234 個讚" or "Liked by X and 234 others"
            like_match = re.search(r'([\d,]+)\s*(?:likes?|個讚)', section_text, re.IGNORECASE)
            if like_match:
                stats["like_count"] = int(like_match.group(1).replace(",", ""))
            else:
                others_match = re.search(r'([\d,]+)\s*others?', section_text, re.IGNORECASE)
                if others_match:
                    stats["like_count"] = int(others_match.group(1).replace(",", "")) + 1
    except Exception as e:
        logger.debug(f"[PostDetail] Like count extraction failed: {e}")

    try:
        # Comments: look for "View all XX comments" link
        comment_link = page.locator("a[href*='comments'], span:has-text('comments'), span:has-text('則留言')")
        if await comment_link.count() > 0:
            comment_text = await comment_link.first.inner_text()
            comment_match = re.search(r'([\d,]+)', comment_text)
            if comment_match:
                stats["comment_count"] = int(comment_match.group(1).replace(",", ""))
    except Exception as e:
        logger.debug(f"[PostDetail] Comment count extraction failed: {e}")

    return stats


async def _extract_timestamp(page: Page) -> str:
    """Extract post timestamp from <time> element."""
    try:
        time_el = page.locator("article time[datetime]")
        if await time_el.count() > 0:
            dt = await time_el.first.get_attribute("datetime")
            return dt or ""
    except Exception as e:
        logger.debug(f"[PostDetail] Timestamp extraction failed: {e}")
    return ""


async def _extract_source_handle(page: Page) -> str:
    """Extract the post author's handle."""
    try:
        # IG post header: link to profile with username
        header_link = page.locator("article header a[href^='/']")
        if await header_link.count() > 0:
            href = await header_link.first.get_attribute("href")
            if href:
                parts = [p for p in href.split("/") if p]
                if parts:
                    return f"@{parts[0]}"
    except Exception as e:
        logger.debug(f"[PostDetail] Handle extraction failed: {e}")
    return ""


async def _detect_media_type(page: Page) -> str:
    """Detect whether the post is IMAGE, VIDEO, or CAROUSEL_ALBUM."""
    # Check for carousel: look for "Next" button (aria-label contains "Next" or "下一步")
    next_btn = page.locator("button[aria-label='Next'], button[aria-label='下一步'], button[aria-label='下一張']")
    if await next_btn.count() > 0:
        return "CAROUSEL_ALBUM"

    # Check for video
    video_el = page.locator("article video")
    if await video_el.count() > 0:
        return "VIDEO"

    return "IMAGE"


async def _collect_carousel_images(page: Page) -> List[Dict[str, Any]]:
    """Iterate through carousel slides and collect all images."""
    images: List[Dict[str, Any]] = []
    seen_urls: set = set()

    # Collect the first image
    first = await _extract_current_slide_image(page)
    if first:
        images.append({"index": 0, **first})
        if first.get("url"):
            seen_urls.add(first["url"])

    next_selectors = [
        "button[aria-label='Next']",
        "button[aria-label='下一步']",
        "button[aria-label='下一張']",
    ]

    max_slides = 20  # IG max carousel is 20
    for slide_idx in range(1, max_slides):
        # Click "Next" button
        clicked = False
        for sel in next_selectors:
            btn = page.locator(sel)
            if await btn.count() > 0:
                try:
                    await btn.click()
                    await page.wait_for_timeout(800)  # Wait for slide transition
                    clicked = True
                    break
                except Exception:
                    continue

        if not clicked:
            break  # No more "Next" button = end of carousel

        # Extract the new slide image
        img_data = await _extract_current_slide_image(page)
        if img_data:
            url = img_data.get("url", "")
            if url and url not in seen_urls:
                images.append({"index": slide_idx, **img_data})
                seen_urls.add(url)
            elif url in seen_urls:
                # We've looped back to a seen image — stop
                break

    return images


async def ig_fetch_post_detail(
    shortcode: str,
    browser_profile: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Fetch complete detail for a single IG post using Playwright.

    Args:
        shortcode: IG post shortcode (e.g. "CxyzABC123")
        browser_profile: Optional path to browser profile directory

    Returns:
        Dict with shortcode, media_type, caption, stats, images[], timestamp, source_handle
    """
    profile = browser_profile or _DEFAULT_PROFILE
    post_url = f"https://www.instagram.com/p/{shortcode}/"

    logger.info(f"[PostDetail] Navigating to {post_url}")

    try:
        async with BrowserSession(profile) as (browser, context, page):
            await page.goto(post_url, wait_until="domcontentloaded", timeout=45000)

            # Wait for article content to render
            try:
                await page.wait_for_selector("article", timeout=15000)
            except PlaywrightTimeoutError:
                # Check for login wall
                login_form = await page.locator("input[name='username']").count()
                if login_form > 0:
                    return {
                        "status": "error",
                        "error": "Login wall detected",
                        "shortcode": shortcode,
                    }
                return {
                    "status": "error",
                    "error": "Post page did not load (article not found)",
                    "shortcode": shortcode,
                }

            # Give images time to load
            await page.wait_for_timeout(2000)

            # Detect media type
            media_type = await _detect_media_type(page)

            # Extract images
            if media_type == "CAROUSEL_ALBUM":
                images = await _collect_carousel_images(page)
            else:
                img = await _extract_current_slide_image(page)
                images = [{"index": 0, **img}] if img else []

            # Extract other metadata
            caption = await _extract_caption(page)
            stats = await _extract_stats(page)
            timestamp = await _extract_timestamp(page)
            source_handle = await _extract_source_handle(page)

            result = {
                "status": "success",
                "shortcode": shortcode,
                "media_type": media_type,
                "caption": caption,
                "like_count": stats.get("like_count"),
                "comment_count": stats.get("comment_count"),
                "images": images,
                "image_count": len(images),
                "timestamp": timestamp,
                "source_handle": source_handle,
                "post_url": post_url,
            }

            logger.info(
                "[PostDetail] Extracted %s: type=%s, images=%d, caption=%d chars",
                shortcode, media_type, len(images), len(caption),
            )

            return result

    except Exception as e:
        logger.error(f"[PostDetail] Fatal error for {shortcode}: {e}")
        return {
            "status": "error",
            "error": str(e),
            "shortcode": shortcode,
        }
