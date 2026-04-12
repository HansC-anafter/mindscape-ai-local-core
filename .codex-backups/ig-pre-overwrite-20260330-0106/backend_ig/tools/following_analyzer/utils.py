import asyncio
import logging
import os
import random
import re
from typing import Any, Dict, Optional

from playwright.async_api import Page

logger = logging.getLogger(__name__)


def classify_failure(error_message: str, current_url: Optional[str] = None) -> str:
    msg = (error_message or "").lower()
    url = (current_url or "").lower()

    if any(token in msg or token in url for token in ["challenge", "checkpoint"]):
        return "challenge_required"
    if "login required" in msg or "accounts/login" in url:
        return "login_required"
    # IG rate limiting / temporary restrictions
    if (
        "rate limit" in msg
        or "too many requests" in msg
        or "429" in msg
        or "try again later" in msg
        or "please wait a few minutes" in msg
        or "we restrict certain activity" in msg
        or "something went wrong" in msg
        or "instagram risk signal detected" in msg
    ):
        return "rate_limited"
    if "timeout" in msg or "timed out" in msg:
        return "timeout"
    if "not found" in msg or "missing" in msg:
        return "not_found"
    if "permission" in msg or "unauthorized" in msg or "forbidden" in msg:
        return "unauthorized"
    if "page crashed" in msg or "target closed" in msg or "browser disconnected" in msg:
        return "browser_crash"

    return "unknown"


def parse_count_text_to_int(value: Optional[str]) -> Optional[int]:
    """
    Best-effort parse for IG count labels.
    Supports:
    - "3,332" -> 3332
    - "3.3k" -> 3300
    - "1.2m" -> 1200000
    - "14.8萬" -> 148000
    - "3332追蹤中" / "following 3332" -> 3332
    """
    if not value or not isinstance(value, str):
        return None
    s = value.strip().lower()
    if not s:
        return None
    # Remove common labels
    s = re.sub(r"(followers?|following|posts?|位粉絲|粉絲|追蹤中|貼文)", " ", s)
    s = s.replace("\u00a0", " ")
    s = s.replace(",", "").strip()
    # Chinese 10k
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*萬", s)
    if m:
        try:
            return int(float(m.group(1)) * 10000)
        except Exception:
            return None
    # k/m suffix
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*([km])\b", s)
    if m:
        try:
            base = float(m.group(1))
            mult = 1000 if m.group(2) == "k" else 1000000
            return int(base * mult)
        except Exception:
            return None
    # Plain integer
    m = re.search(r"\b([0-9]{1,10})\b", s)
    if m:
        try:
            return int(m.group(1))
        except Exception:
            return None
    return None


async def detect_risk_signal(page: Optional[Page]) -> Optional[Dict[str, str]]:
    if not page:
        return None

    try:
        current_url = (page.url or "").lower()
    except Exception:
        current_url = ""

    if any(token in current_url for token in ["challenge", "checkpoint"]):
        return {
            "error_type": "challenge_required",
            "error_message": "Instagram checkpoint/challenge detected",
        }
    if "accounts/login" in current_url:
        return {
            "error_type": "login_required",
            "error_message": "Instagram login required",
        }

    try:
        text = await asyncio.wait_for(page.inner_text("body"), timeout=4.0)
        text_lower = (text or "").lower()
    except Exception:
        return None

    keywords = [
        ("rate_limited", "try again later"),
        ("rate_limited", "please wait a few minutes"),
        ("rate_limited", "we restrict certain activity"),
        ("rate_limited", "we're sorry, but something went wrong"),
        ("challenge_required", "confirm it's you"),
        ("challenge_required", "confirm your identity"),
        ("challenge_required", "suspicious"),
    ]

    for error_type, kw in keywords:
        if kw in text_lower:
            return {
                "error_type": error_type,
                "error_message": f"Instagram risk signal detected: {kw}",
            }

    return None


def get_chromium_executable_path() -> Optional[str]:
    candidate = os.environ.get("CHROMIUM_PATH")
    if candidate and os.path.exists(candidate):
        return candidate

    candidates = [
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
    ]
    for path in candidates:
        try:
            if os.path.exists(path):
                return path
        except Exception:
            continue

    return None


def random_delay(min_seconds: float = 1.0, max_seconds: float = 3.0) -> float:
    """Generate random delay for human-like behavior."""
    return random.uniform(min_seconds, max_seconds)
