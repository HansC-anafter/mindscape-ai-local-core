import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

import httpx

from capabilities.ig.tools.following_analyzer.browser_session import BrowserSession

logger = logging.getLogger(__name__)

_CDN_URL_RE = re.compile(
    r'https[^"\']+\.(?:jpg|jpeg|webp|png)[^"\']*',
    flags=re.IGNORECASE,
)
_KNOWN_INVALID_THUMBNAIL_SHA256 = {
    "5ea73220ab5bda046e21d3f0cba26eafadeb3cc2bbd07a91978774048c84b6ee",
}
_MIN_VALID_THUMBNAIL_BYTES = 1024


@dataclass
class DownloadedThumbnail:
    content: bytes
    response: httpx.Response
    resolved_url: str
    source: str


def is_placeholder_thumbnail_content(content: bytes) -> bool:
    if not content or len(content) <= _MIN_VALID_THUMBNAIL_BYTES:
        return True
    return hashlib.sha256(content).hexdigest() in _KNOWN_INVALID_THUMBNAIL_SHA256


def _clean_embed_url(url: str) -> str:
    return (
        url.replace("\\u0026", "&")
        .replace("\\&", "&")
        .replace("\\/", "/")
        .replace("&amp;", "&")
    )


def _load_instagram_cookies() -> Dict[str, str]:
    cookies: Dict[str, str] = {}
    storage_state = (
        Path(os.environ.get("DATA_DIR", "data"))
        / "ig-browser-profiles"
        / "default"
        / "storage_state.json"
    )
    if not storage_state.exists():
        return cookies

    try:
        with storage_state.open(encoding="utf-8") as handle:
            state = json.load(handle)
        for cookie in state.get("cookies", []):
            if "instagram.com" in cookie.get("domain", ""):
                name = cookie.get("name")
                value = cookie.get("value")
                if name and value:
                    cookies[name] = value
    except Exception as exc:
        logger.debug("[IGThumbnailFetcher] Failed to load storage_state cookies: %s", exc)

    return cookies


def _build_download_headers() -> Dict[str, str]:
    cookies = _load_instagram_cookies()
    cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items()) if cookies else ""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "image/avif,image/webp,image/apng,*/*",
        "Referer": "https://www.instagram.com/",
    }
    if cookie_header:
        headers["Cookie"] = cookie_header
    return headers


async def _download_image(url: str, *, timeout: float = 15.0) -> tuple[bytes, httpx.Response]:
    headers = _build_download_headers()
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        return resp.content, resp


def _extract_cdn_urls_from_embed_html(html: str) -> list[str]:
    candidates = []
    seen: set[str] = set()
    for match in _CDN_URL_RE.findall(html or ""):
        cleaned = _clean_embed_url(match)
        if "150x150" in cleaned or "s150x150" in cleaned or "320x320" in cleaned or "s320x320" in cleaned:
            continue
        if ".fbcdn.net" not in cleaned and ".cdninstagram.com" not in cleaned:
            continue
        if cleaned in seen:
            continue
        seen.add(cleaned)
        candidates.append(cleaned)
    candidates.sort(key=lambda url: ("1080x1080" in url, "640x640" in url), reverse=True)
    return candidates


async def fetch_via_http_embed(shortcode: str) -> str | None:
    url = f"https://www.instagram.com/p/{shortcode}/embed/"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    }
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                return None
            urls = _extract_cdn_urls_from_embed_html(resp.text)
            return urls[0] if urls else None
    except Exception as exc:
        logger.debug("[IGThumbnailFetcher] HTTP embed fetch failed for %s: %s", shortcode, exc)
        return None


async def fetch_via_browser(shortcode: str) -> str | None:
    profile_path = str(Path(os.environ.get("DATA_DIR", "data")) / "ig-browser-profiles" / "default")
    if not os.path.exists(profile_path):
        logger.debug("[IGThumbnailFetcher] Browser profile path not found: %s", profile_path)
        return None

    logger.info("[IGThumbnailFetcher] Embed fetch failed, falling back to browser for %s", shortcode)
    async with BrowserSession(user_data_dir=profile_path) as (browser, context, page):
        try:
            await page.goto(
                f"https://www.instagram.com/p/{shortcode}/",
                wait_until="domcontentloaded",
                timeout=15000,
            )
            await page.wait_for_selector("article img", timeout=10000)
            imgs = await page.locator("article img").all()
            for img in imgs:
                src = await img.get_attribute("src")
                if src and (".fbcdn.net" in src or ".cdninstagram.com" in src):
                    return src
            return None
        except Exception as exc:
            logger.debug("[IGThumbnailFetcher] Browser fallback failed for %s: %s", shortcode, exc)
            return None


async def fetch_via_db_thumbnail(shortcode: str) -> str | None:
    try:
        from sqlalchemy import create_engine, text as sa_text

        try:
            from app.database.config import get_postgres_url_core

            engine = create_engine(get_postgres_url_core())
        except ImportError:
            from backend.app.core.database import get_db_engine

            engine = get_db_engine()

        with engine.connect() as conn:
            row = conn.execute(
                sa_text(
                    "SELECT thumbnail_url FROM ig_posts "
                    "WHERE post_shortcode = :sc AND thumbnail_url IS NOT NULL "
                    "LIMIT 1"
                ),
                {"sc": shortcode},
            ).fetchone()
            if row and row[0]:
                return row[0]
    except Exception as exc:
        logger.debug("[IGThumbnailFetcher] DB thumbnail lookup failed for %s: %s", shortcode, exc)
    return None


async def fetch_thumbnail_bytes(
    shortcode: Optional[str],
    *,
    preferred_url: Optional[str] = None,
    timeout: float = 15.0,
) -> DownloadedThumbnail:
    candidates: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add_candidate(source: str, url: Optional[str]) -> None:
        if not url:
            return
        normalized = url.strip()
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        candidates.append((source, normalized))

    add_candidate("preferred_url", preferred_url)

    if shortcode:
        add_candidate("db_thumbnail", await fetch_via_db_thumbnail(shortcode))
        add_candidate("embed", await fetch_via_http_embed(shortcode))
        add_candidate("browser", await fetch_via_browser(shortcode))

    last_error: Optional[Exception] = None
    for source, url in candidates:
        try:
            content, response = await _download_image(url, timeout=timeout)
            if is_placeholder_thumbnail_content(content):
                last_error = RuntimeError(
                    f"Invalid placeholder thumbnail via {source} for shortcode={shortcode!r}"
                )
                logger.warning(
                    "[IGThumbnailFetcher] Rejected placeholder thumbnail via %s for %s",
                    source,
                    shortcode or url[:80],
                )
                continue
            return DownloadedThumbnail(
                content=content,
                response=response,
                resolved_url=url,
                source=source,
            )
        except Exception as exc:
            last_error = exc
            logger.debug(
                "[IGThumbnailFetcher] Download failed via %s for %s: %s",
                source,
                shortcode or url[:80],
                exc,
            )

    if last_error is not None:
        raise last_error

    raise RuntimeError(
        f"No thumbnail candidates available for shortcode={shortcode!r} preferred_url={preferred_url!r}"
    )
