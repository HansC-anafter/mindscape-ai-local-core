import asyncio
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import unquote

from playwright.async_api import Locator, Page

from .utils import random_delay

logger = logging.getLogger(__name__)

# Regex pattern for matching email addresses in bio text
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")

# Multi-language patterns for private account detection.
# IG uses BOTH "account" and "profile" wording depending on version/language.
# Evidence: kust.51 screenshot showed "This profile is private" (not "account").
_PRIVATE_ACCOUNT_PHRASES = [
    # English — both wordings confirmed in production
    "this account is private",
    "this profile is private",
    # zh-TW
    "此帳號不公開",
    "此帳號為私人帳號",
    "這是私人帳號",
    "這個帳號是私人帳號",
    "這個檔案是私人檔案",
    # zh-CN
    "这是私人帐户",
    "此帐号是私密帐号",
    # ja
    "このアカウントは非公開です",
    # ko
    "비공개 계정입니다",
    "비공개 프로필입니다",
    # es
    "esta cuenta es privada",
    "este perfil es privado",
    # fr
    "ce compte est privé",
    "ce profil est privé",
    # de
    "dieses konto ist privat",
    "dieses profil ist privat",
    # pt
    "esta conta é privada",
    "este perfil é privado",
    # it
    "questo account è privato",
    "questo profilo è privato",
    # ar
    "هذا الحساب خاص",
    # th
    "บัญชีนี้เป็นส่วนตัว",
    # vi
    "tài khoản này ở chế độ riêng tư",
    # id
    "akun ini bersifat pribadi",
    "profil ini bersifat pribadi",
]

# Phrases indicating the page/account does not exist (deleted, suspended, etc).
# Evidence: sakixoc screenshot showed "Sorry, this page isn't available".
_PAGE_NOT_AVAILABLE_PHRASES = [
    "sorry, this page isn't available",
    "sorry, this page isn't available",
    "the link you followed may be broken",
    "此頁面目前無法使用",
    "很抱歉，此页面不可用",
    "ページが見つかりませんでした",
    "이 페이지는 사용할 수 없습니다",
]


async def _detect_private_account(page: Page, username: str) -> bool:
    """
    Detect whether the current page is a private Instagram profile.

    Uses two independent signals (either triggers detection):
    1. Multi-language text matching in <main> element
    2. DOM structure: private profiles LACK follower links and post grid
       articles but HAVE header stats (ul li)
    """
    # ── Signal 1: Multi-language text match ──────────────────────────
    try:
        main_text = await page.locator("main").inner_text(timeout=3000)
        main_lower = main_text.lower()
        for phrase in _PRIVATE_ACCOUNT_PHRASES:
            if phrase.lower() in main_lower:
                logger.info(
                    "[PageAnalyzer] Private detected (text match) for %s: '%s'",
                    username,
                    phrase,
                )
                return True
    except Exception:
        pass

    # ── Signal 2: DOM structure (language-agnostic) ──────────────────
    # Private profiles have header stats but NO clickable follower link
    # and NO post grid.  Public profiles always have both.
    try:
        has_header_stats = await page.locator("header section ul li").count() >= 2
        has_follower_link = await page.locator("a[href$='/followers/']").count() > 0
        has_post_grid = await page.locator("main article").count() > 0

        if has_header_stats and not has_follower_link and not has_post_grid:
            logger.info(
                "[PageAnalyzer] Private detected (DOM structure) for %s: "
                "header_stats=%s, follower_link=%s, post_grid=%s",
                username,
                has_header_stats,
                has_follower_link,
                has_post_grid,
            )
            return True
    except Exception:
        pass

    return False


async def _extract_contact_info(
    page: Page,
    username: str,
    bio_text: str = "",
) -> Dict[str, Any]:
    """
    Extract contact information from the profile page.

    Sources:
    - Email: regex match from bio text, mailto: links on page
    - Phone: tel: links on page
    - Website: external links in header/bio area (l.instagram.com redirects)

    Returns dict with optional keys: public_email, public_phone_number, contact_website
    """
    result: Dict[str, Any] = {}

    # 1. Extract email from bio text via regex
    if bio_text:
        email_match = _EMAIL_RE.search(bio_text)
        if email_match:
            result["public_email"] = email_match.group(0).lower()

    # 2. Scan for mailto: and tel: links on the page
    try:
        all_links = await page.locator("a[href]").all()
        for link in all_links:
            try:
                href = await link.get_attribute("href")
                if not href:
                    continue

                # mailto: link
                if href.lower().startswith("mailto:") and "public_email" not in result:
                    email = href[7:].split("?")[0].strip()
                    if email and _EMAIL_RE.match(email):
                        result["public_email"] = email.lower()

                # tel: link
                if (
                    href.lower().startswith("tel:")
                    and "public_phone_number" not in result
                ):
                    phone = href[4:].strip()
                    if phone:
                        result["public_phone_number"] = phone

            except Exception:
                continue
    except Exception:
        pass

    # 3. Extract external website link from header area
    # Instagram wraps external URLs through l.instagram.com redirect
    try:
        header_links = await page.locator(
            "header a[href*='l.instagram.com'], "
            "header a[href^='http']:not([href*='instagram.com'])"
        ).all()
        for link in header_links:
            try:
                href = await link.get_attribute("href")
                if not href:
                    continue
                # Unwrap Instagram redirect URL
                if "l.instagram.com" in href and "u=" in href:
                    from urllib.parse import parse_qs, urlparse

                    parsed = urlparse(href)
                    qs = parse_qs(parsed.query)
                    if "u" in qs:
                        result["contact_website"] = unquote(qs["u"][0])
                        break
                elif "instagram.com" not in href:
                    result["contact_website"] = href
                    break
            except Exception:
                continue
    except Exception:
        pass

    # 4. Fallback: try to extract external URL from bio link area
    # Some profiles show the link outside header in a dedicated link section
    if "contact_website" not in result:
        try:
            bio_links = await page.locator("a[href*='l.instagram.com']").all()
            for link in bio_links[:3]:
                try:
                    href = await link.get_attribute("href")
                    if not href or "instagram.com" not in href:
                        continue
                    if "l.instagram.com" in href and "u=" in href:
                        from urllib.parse import parse_qs, urlparse

                        parsed = urlparse(href)
                        qs = parse_qs(parsed.query)
                        if "u" in qs:
                            result["contact_website"] = unquote(qs["u"][0])
                            break
                except Exception:
                    continue
        except Exception:
            pass

    if result:
        logger.debug(
            f"[PageAnalyzer] Contact info for {username}: "
            f"email={'yes' if 'public_email' in result else 'no'}, "
            f"phone={'yes' if 'public_phone_number' in result else 'no'}, "
            f"website={'yes' if 'contact_website' in result else 'no'}"
        )

    return result


async def analyze_account_page(
    page: Page,
    account_url: str,
    username: str,
) -> Dict[str, Any]:
    """
    Visit account page and extract statistics and data.
    """
    try:
        # Use wait_until="commit" — IG's SPA never fires domcontentloaded reliably,
        # which caused page.goto() to hang for 90+ seconds even though the page was
        # visually fully loaded (confirmed via timeout screenshots).
        await page.goto(account_url, wait_until="commit", timeout=30000)
        # Wait for the header section to appear instead of unreliable networkidle
        try:
            await page.wait_for_selector(
                "header section", state="visible", timeout=20000
            )
        except Exception:
            # Fallback: page might still have enough content in og:description
            pass
        await asyncio.sleep(random_delay(2, 4))

        stats: Dict[str, Any] = {}

        # ── Page-not-available fast-fail ──────────────────────────────
        # Deleted/suspended accounts show "Sorry, this page isn't available".
        # Fast-fail to avoid 90s timeout on selectors that will never match.
        try:
            body_text = await page.locator("body").inner_text(timeout=3000)
            body_lower = body_text.lower()
            for phrase in _PAGE_NOT_AVAILABLE_PHRASES:
                if phrase.lower() in body_lower:
                    logger.info(
                        "[PageAnalyzer] Page not available for %s: '%s'",
                        username,
                        phrase,
                    )
                    stats["page_analysis_error"] = f"Page not available: {phrase}"
                    stats["is_unavailable"] = True
                    return stats
        except Exception:
            pass

        # ── Early private-account detection ──────────────────────────
        # Private accounts lack most DOM elements that public profiles have
        # (follower links, bio data-testid, post grid, etc.).  Trying each
        # fallback selector wastes ~3 s × N selectors and can push the total
        # past the 90-s per-account timeout.  Detect private early and
        # return only the header stats that are actually present.
        #
        # Uses multi-language text + DOM structure detection to handle
        # IG accounts with non-English UI language settings.
        is_private_early = await _detect_private_account(page, username)

        if is_private_early:
            logger.info(
                f"[PageAnalyzer] Private account detected early: {username} — fast path"
            )
            # Private profiles show stats as plain text in header section ul li
            _clean = lambda v: (v or "").strip()

            async def _quick_text(loc, timeout=3000):
                try:
                    return _clean(await loc.first.inner_text(timeout=timeout))
                except Exception:
                    return ""

            async def _quick_attr(loc, attr):
                try:
                    return _clean(await loc.first.get_attribute(attr))
                except Exception:
                    return ""

            header_items = page.locator("header section ul li")
            item_count = 0
            try:
                item_count = await header_items.count()
            except Exception:
                pass

            if item_count >= 1:
                stats["post_count_text"] = await _quick_text(
                    header_items.nth(0).locator("span")
                )
            if item_count >= 2:
                stats["follower_count_text"] = await _quick_text(
                    header_items.nth(1).locator("span")
                )
            if item_count >= 3:
                stats["following_count_text"] = await _quick_text(
                    header_items.nth(2).locator("span")
                )

            # og:description fallback for counts
            og_desc = await _quick_attr(
                page.locator("meta[property='og:description']"), "content"
            )
            if og_desc:
                stats["og_description"] = og_desc
                try:
                    import re

                    m = re.search(
                        r"([0-9][0-9.,]*[KMB]?)\s+Followers?,\s+([0-9][0-9.,]*[KMB]?)\s+Following,\s+([0-9][0-9.,]*[KMB]?)\s+Posts",
                        og_desc,
                        flags=re.IGNORECASE,
                    )
                    if m:
                        stats["follower_count_text"] = (
                            stats.get("follower_count_text")
                            or f"{m.group(1)} followers"
                        )
                        stats["following_count_text"] = (
                            stats.get("following_count_text")
                            or f"{m.group(2)} following"
                        )
                        stats["post_count_text"] = (
                            stats.get("post_count_text") or f"{m.group(3)} posts"
                        )
                except Exception:
                    pass

            # Profile image
            profile_img = await _quick_attr(page.locator("header img"), "src")
            if profile_img:
                stats["profile_image_url"] = profile_img

            # Profile name (first dir=auto text in header that isn't the username)
            try:
                header = page.locator("header")
                containers = header.locator("div[dir='auto'], span[dir='auto'], h1, h2")
                cnt = await containers.count()
                for i in range(min(cnt, 5)):
                    t = _clean(await containers.nth(i).inner_text(timeout=2000))
                    if (
                        t
                        and t.lower() != username.lower()
                        and t.lower()
                        not in [
                            "follow",
                            "following",
                            "message",
                            "posts",
                            "followers",
                        ]
                        and not any(
                            x in t.lower()
                            for x in [" followers", " following", " posts"]
                        )
                    ):
                        stats["profile_name"] = t
                        break
            except Exception:
                pass

            stats["is_private"] = True
            stats["page_analyzed_at"] = datetime.now().isoformat()
            return stats

        def _clean_text(value: Optional[str]) -> str:
            return (value or "").strip()

        async def _get_text(locator: Locator, timeout: int = 3000) -> str:
            try:
                return _clean_text(await locator.first.inner_text(timeout=timeout))
            except Exception:
                return ""

        async def _get_attr(locator: Locator, attr: str) -> str:
            try:
                return _clean_text(await locator.first.get_attribute(attr))
            except Exception:
                return ""

        followers_text = await _get_text(page.locator("a[href$='/followers/'] span"))
        if not followers_text:
            followers_text = await _get_attr(
                page.locator("a[href$='/followers/'] span"), "title"
            )
        if not followers_text:
            followers_text = await _get_text(
                page.locator("header section ul li").nth(1).locator("span")
            )
        stats["follower_count_text"] = followers_text

        following_text = await _get_text(page.locator("a[href$='/following/'] span"))
        if not following_text:
            following_text = await _get_attr(
                page.locator("a[href$='/following/'] span"), "title"
            )
        if not following_text:
            following_text = await _get_text(
                page.locator("header section ul li").nth(2).locator("span")
            )
        stats["following_count_text"] = following_text

        post_text = await _get_text(
            page.locator("header section ul li").first.locator("span")
        )
        if not post_text:
            post_text = await _get_attr(
                page.locator("header section ul li").first.locator("span"), "title"
            )
        stats["post_count_text"] = post_text

        og_desc = await _get_attr(
            page.locator("meta[property='og:description']"), "content"
        )
        if og_desc:
            stats["og_description"] = og_desc
            try:
                import re

                m = re.search(
                    r"([0-9][0-9.,]*[KMB]?)\s+Followers?,\s+([0-9][0-9.,]*[KMB]?)\s+Following,\s+([0-9][0-9.,]*[KMB]?)\s+Posts",
                    og_desc,
                    flags=re.IGNORECASE,
                )
                if m:
                    stats["follower_count_text"] = (
                        stats.get("follower_count_text") or f"{m.group(1)} followers"
                    )
                    stats["following_count_text"] = f"{m.group(2)} following"
                    stats["post_count_text"] = f"{m.group(3)} posts"
            except Exception:
                pass

        bio_text = await _get_text(page.locator("[data-testid='user-bio']"))

        profile_name = ""
        try:
            header = page.locator("header")
            containers = header.locator("div[dir='auto'], span[dir='auto'], h1, h2")
            container_count = await containers.count()

            candidates = []
            seen_texts = set()
            for i in range(min(container_count, 20)):
                t = _clean_text(await containers.nth(i).inner_text())
                if not t or t in seen_texts:
                    continue

                low = t.lower()
                if low in ["follow", "following", "message", "posts", "followers"]:
                    continue
                if any(x in low for x in [" followers", " following", " posts"]):
                    continue

                if low in ["edit profile", "view archive", "ad tools"]:
                    continue

                candidates.append(t)
                seen_texts.add(t)

            if candidates:
                profile_name = candidates[0]
                remaining = candidates[1:]

                if len(candidates) >= 2 and candidates[0].lower() == username.lower():
                    if candidates[1].lower() == username.lower():
                        profile_name = candidates[1]
                        remaining = candidates[2:]

                if remaining and not bio_text:
                    bio_text = "\n".join(remaining)
        except Exception as e:
            logger.debug(f"Error during candidate extraction: {e}")

        if profile_name:
            stats["profile_name"] = profile_name
        if bio_text and len(bio_text) > 1:
            stats["profile_bio"] = bio_text

        profile_img = await _get_attr(page.locator("header img"), "src")
        if profile_img:
            stats["profile_image_url"] = profile_img

        # Detect if account is private (multi-signal: text + DOM structure)
        is_private = await _detect_private_account(page, username)
        stats["is_private"] = is_private

        # ── Extract contact info (email, phone, website) ──
        if not is_private:
            try:
                contact_info = await _extract_contact_info(
                    page, username, bio_text=bio_text
                )
                if contact_info:
                    stats.update(contact_info)
            except Exception as e:
                logger.debug(
                    f"[PageAnalyzer] Contact info extraction failed for {username}: {e}"
                )

        # ── Pre-fetch post grid (lightweight: no individual post visits) ──
        if not is_private:
            try:
                import re as _re

                post_links = await page.locator(
                    "a[href*='/p/'], a[href*='/reel/']"
                ).all()
                grid_posts = []
                for link in post_links[:12]:
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
                        if not shortcode:
                            continue
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
                            }
                        )
                    except Exception:
                        continue
                if grid_posts:
                    stats["grid_posts"] = grid_posts
                    logger.debug(
                        f"[PageAnalyzer] Extracted {len(grid_posts)} grid posts for {username}"
                    )
            except Exception as e:
                logger.debug(
                    f"[PageAnalyzer] Post grid extraction failed for {username}: {e}"
                )

        stats["page_analyzed_at"] = datetime.now().isoformat()

        return stats

    except Exception as e:
        logger.warning(f"Error analyzing account page {account_url}: {e}")
        return {
            "page_analysis_error": str(e),
            "page_analyzed_at": datetime.now().isoformat(),
        }
