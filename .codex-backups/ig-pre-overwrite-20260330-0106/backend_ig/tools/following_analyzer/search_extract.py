"""Search-based following list extraction.

When infinite scroll cannot capture enough accounts (IG UI lazy-load
cap ~1400-1500), this module uses the dialog's search box to query
accounts letter-by-letter (a-z, 0-9).  Each letter returns a subset
of the following list that matches by username or display name.

The return contract matches ``extract_following_list`` from
``scroll_extract.py`` so the runner can merge results seamlessly.
"""

import asyncio
import logging
import os
import random
import time
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set

from playwright.async_api import Locator, Page

from .utils import detect_risk_signal, random_delay

logger = logging.getLogger(__name__)

# Default search alphabet (a-z then digits)
_SEARCH_ALPHABET = list("abcdefghijklmnopqrstuvwxyz0123456789")

# Tunable via env vars
_DELAY_BETWEEN_LETTERS_MIN = float(os.environ.get("IG_SEARCH_DELAY_MIN", "8"))
_DELAY_BETWEEN_LETTERS_MAX = float(os.environ.get("IG_SEARCH_DELAY_MAX", "15"))
_REST_EVERY_N_LETTERS = int(os.environ.get("IG_SEARCH_REST_EVERY", "5"))
_REST_DURATION_MIN = float(os.environ.get("IG_SEARCH_REST_MIN", "30"))
_REST_DURATION_MAX = float(os.environ.get("IG_SEARCH_REST_MAX", "60"))
_MAX_RESULTS_PER_LETTER = int(os.environ.get("IG_SEARCH_MAX_PER_LETTER", "500"))
_TOTAL_TIMEOUT_SECONDS = int(os.environ.get("IG_SEARCH_TIMEOUT", "1800"))
_NO_NEW_STREAK_LIMIT = int(os.environ.get("IG_SEARCH_NO_NEW_STREAK", "5"))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def _find_search_input(dialog: Locator) -> Optional[Locator]:
    """Locate the search input inside the following dialog."""
    selectors = [
        'input[placeholder*="Search" i]',
        'input[aria-label*="Search" i]',
        'input[type="text"]',
        'input[type="search"]',
    ]
    for sel in selectors:
        try:
            loc = dialog.locator(sel).first
            if await loc.is_visible(timeout=2000):
                return loc
        except Exception:
            continue
    return None


async def _clear_search_input(search_input: Locator) -> None:
    """Clear the search input field."""
    try:
        await search_input.click()
        await search_input.fill("")
        await asyncio.sleep(random_delay(0.3, 0.6))
    except Exception:
        try:
            await search_input.press("Control+a")
            await search_input.press("Backspace")
        except Exception:
            pass


async def _extract_visible_accounts(dialog: Locator) -> List[Dict[str, Any]]:
    """Extract account entries visible in the dialog."""
    accounts: List[Dict[str, Any]] = []
    try:
        links = dialog.locator('a[href*="/"]')
        count = await links.count()
        for i in range(min(count, 1000)):
            try:
                link = links.nth(i)
                href = await link.get_attribute("href") or ""
                if not href or href in ("/", "#"):
                    continue
                username = href.strip("/").split("/")[-1]
                if not username or username in ("explore", "accounts", "about"):
                    continue

                display_name = ""
                try:
                    spans = link.locator("span")
                    span_count = await spans.count()
                    if span_count > 0:
                        display_name = (await spans.first.inner_text()).strip()
                except Exception:
                    pass

                accounts.append(
                    {
                        "username": username,
                        "display_name": display_name,
                        "fetched_at": _utc_now().isoformat(),
                    }
                )
            except Exception:
                continue
    except Exception as e:
        logger.debug("[SearchExtract] Failed to extract visible accounts: %s", e)
    return accounts


async def _scroll_search_results(
    page: Page,
    dialog: Locator,
    existing_usernames: Set[str],
    max_results: int,
) -> List[Dict[str, Any]]:
    """Scroll through search results to capture all matching accounts."""
    all_accounts: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    no_new_streak = 0

    for iteration in range(200):
        visible = await _extract_visible_accounts(dialog)
        new_count = 0
        for acc in visible:
            uname = acc.get("username", "").lower()
            if uname and uname not in seen and uname not in existing_usernames:
                seen.add(uname)
                all_accounts.append(acc)
                new_count += 1

        if new_count == 0:
            no_new_streak += 1
        else:
            no_new_streak = 0

        if no_new_streak >= _NO_NEW_STREAK_LIMIT:
            break
        if len(all_accounts) >= max_results:
            break

        # Scroll the dialog to load more results
        try:
            scroll_container = dialog.locator("div").first
            await scroll_container.evaluate("(el) => { el.scrollTop += 300; }")
        except Exception:
            pass
        try:
            await page.mouse.wheel(0, 200)
        except Exception:
            pass
        await asyncio.sleep(random_delay(0.5, 1.0))

    return all_accounts


async def extract_following_by_search(
    page: Page,
    dialog: Locator,
    existing_accounts: List[Dict[str, Any]],
    expected_following_count: Optional[int] = None,
    scroll_evidence: Optional[Dict[str, Any]] = None,
    completed_letters: Optional[List[str]] = None,
    on_progress: Optional[Callable[..., Awaitable[None]]] = None,
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Extract following list by searching letter-by-letter in the dialog.

    Args:
        page: Playwright page instance
        dialog: The following dialog locator
        existing_accounts: Accounts already found via scroll (for dedup)
        expected_following_count: Expected total following count
        scroll_evidence: Evidence dict from scroll phase (preserved in output)
        completed_letters: Letters already searched (for resume)
        on_progress: Progress callback

    Returns:
        Tuple of (merged_accounts, meta_dict) matching extract_following_list contract
    """
    existing_usernames: Set[str] = {
        (a.get("username") or "").lower() for a in existing_accounts
    }
    merged_accounts = list(existing_accounts)
    search_new_accounts = 0
    search_start = time.monotonic()
    letters_completed: List[str] = list(completed_letters or [])
    stop_reason = "search_completed"

    # Determine which letters to search (skip already-completed for resume)
    remaining_letters = [
        ch for ch in _SEARCH_ALPHABET if ch not in set(letters_completed)
    ]

    search_input = await _find_search_input(dialog)
    if not search_input:
        logger.warning("[SearchExtract] No search input found in dialog")
        return merged_accounts, {
            "stop_reason": "search_input_not_found",
            "list_capture_status": "search_failed",
            "is_retryable": False,
            "list_capture_evidence": {
                **(scroll_evidence or {}),
                "search_error": "search_input_not_found",
            },
        }

    for letter_idx, letter in enumerate(remaining_letters):
        # Total time guard
        elapsed = time.monotonic() - search_start
        if elapsed > _TOTAL_TIMEOUT_SECONDS:
            stop_reason = "search_timeout"
            logger.info(
                "[SearchExtract] Total timeout reached (%.0fs), stopping at letter '%s'",
                elapsed,
                letter,
            )
            break

        # Risk signal detection
        try:
            risk = await detect_risk_signal(page)
            if risk:
                stop_reason = "search_rate_limited"
                logger.warning("[SearchExtract] Risk signal detected: %s", risk)
                break
        except Exception:
            pass

        # Type the search letter
        try:
            await _clear_search_input(search_input)
            await asyncio.sleep(random_delay(0.3, 0.6))
            await search_input.press_sequentially(letter, delay=random.randint(80, 200))
            await asyncio.sleep(random_delay(2.0, 3.5))
        except Exception as e:
            logger.warning("[SearchExtract] Failed to type letter '%s': %s", letter, e)
            letters_completed.append(letter)
            continue

        # Scroll and extract results for this letter
        letter_accounts = await _scroll_search_results(
            page, dialog, existing_usernames, _MAX_RESULTS_PER_LETTER
        )

        new_in_letter = 0
        for acc in letter_accounts:
            uname = (acc.get("username") or "").lower()
            if uname and uname not in existing_usernames:
                existing_usernames.add(uname)
                merged_accounts.append(acc)
                new_in_letter += 1
                search_new_accounts += 1

        letters_completed.append(letter)
        logger.info(
            "[SearchExtract] Letter '%s': found %d accounts (new=%d), "
            "total=%d, elapsed=%.0fs",
            letter,
            len(letter_accounts),
            new_in_letter,
            len(merged_accounts),
            time.monotonic() - search_start,
        )

        # Progress callback
        if on_progress:
            try:
                await on_progress(
                    merged_accounts,
                    {
                        "stage": "search_extract",
                        "search_letter": letter,
                        "search_letters_completed": len(letters_completed),
                        "search_letters_total": len(_SEARCH_ALPHABET),
                        "search_new_accounts": search_new_accounts,
                        "total_accounts": len(merged_accounts),
                    },
                )
            except Exception:
                pass

        # Rest period every N letters
        if (letter_idx + 1) % _REST_EVERY_N_LETTERS == 0 and letter_idx < len(
            remaining_letters
        ) - 1:
            rest_duration = random.uniform(_REST_DURATION_MIN, _REST_DURATION_MAX)
            logger.info(
                "[SearchExtract] Resting for %.0fs after %d letters",
                rest_duration,
                letter_idx + 1,
            )
            await asyncio.sleep(rest_duration)
        else:
            # Normal delay between letters
            delay = random.uniform(
                _DELAY_BETWEEN_LETTERS_MIN, _DELAY_BETWEEN_LETTERS_MAX
            )
            await asyncio.sleep(delay)

    # Clear search input when done
    try:
        await _clear_search_input(search_input)
    except Exception:
        pass

    elapsed_total = time.monotonic() - search_start
    letters_remaining = [
        ch for ch in _SEARCH_ALPHABET if ch not in set(letters_completed)
    ]

    # Determine final capture status
    if not letters_remaining:
        list_capture_status = "search_augmented"
    elif stop_reason == "search_timeout":
        list_capture_status = "search_partial"
    elif stop_reason == "search_rate_limited":
        list_capture_status = "search_rate_limited"
    else:
        list_capture_status = "search_augmented"

    return merged_accounts, {
        "stop_reason": stop_reason,
        "list_capture_status": list_capture_status,
        "is_retryable": bool(letters_remaining),
        "list_capture_evidence": {
            **(scroll_evidence or {}),
            "search_letters_completed": letters_completed,
            "search_letters_remaining": letters_remaining,
            "search_new_accounts": search_new_accounts,
            "search_duration_seconds": round(elapsed_total, 1),
            "search_trigger": (
                f"expected={expected_following_count}, "
                f"scroll_saved={len(existing_accounts)}, "
                f"ratio={len(existing_accounts) / max(expected_following_count or 1, 1):.2f}"
            ),
        },
    }
