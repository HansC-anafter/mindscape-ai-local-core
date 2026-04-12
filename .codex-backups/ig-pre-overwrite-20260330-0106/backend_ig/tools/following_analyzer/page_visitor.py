"""
Page visitor for Instagram following analyzer.

This module handles visiting individual account pages and extracting
detailed profile statistics.

Visit strategy (primary → fallback):
  1. i.instagram.com private API  (~0.3s/account, no browser required)
  2. Playwright DOM                (~30-90s/account, original path)

The private API path is disabled automatically if:
  - IG returns 429 (rate limited)  →  circuit breaker opens
  - IG returns 401/403 (auth)      →  session invalid, log + skip for run
  - 5 consecutive failures          →  circuit breaker opens
"""

import asyncio
import logging
import os
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Dict, List, Optional, Tuple

from playwright.async_api import Page

from .page_analyzer import analyze_account_page
from .browser_session import ANTI_DETECTION_SCRIPT
from .resume_manager import is_account_page_done, normalize_accounts
from .utils import classify_failure, detect_risk_signal, random_delay
from .private_api_visitor import (
    PrivateAPIVisitor,
    PrivateAPIRateLimited,
    PrivateAPIAuthError,
    PrivateAPINotFound,
)

if TYPE_CHECKING:
    from .artifact_manager import ArtifactManager

logger = logging.getLogger(__name__)

# Error signatures that indicate a browser crash (page is dead, cannot be reused)
BROWSER_CRASH_SIGNATURES = ("page crashed", "target closed", "browser disconnected")

# Default browser profile path (same default used by runner.py)
_DEFAULT_USER_DATA_DIR = "/app/data/ig-browser-profiles/default"


def _pre_merge_db_visited(
    accounts: List[Dict[str, Any]],
    artifact_manager: "ArtifactManager",
) -> None:
    """
    Query ig_accounts_flat for accounts that already have follower_count
    (i.e. have been visited in a previous execution) and inject
    page_analyzed_at + stats into the in-memory account dicts so that
    needs_visit() returns False for them.
    """
    workspace_id = getattr(artifact_manager, "workspace_id", None)
    seed = getattr(artifact_manager, "target_username", None)
    if not workspace_id or not seed:
        return

    # Build lookup of handles that still need visiting
    need_handles = []
    idx_by_handle: Dict[str, List[int]] = {}
    for i, acc in enumerate(accounts):
        if not isinstance(acc, dict):
            continue
        handle = (acc.get("username") or acc.get("handle") or "").strip()
        if not handle:
            continue
        # Only look up accounts that don't already have page_analyzed_at
        if acc.get("page_analyzed_at"):
            continue
        need_handles.append(handle)
        idx_by_handle.setdefault(handle, []).append(i)

    if not need_handles:
        return

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
                    SELECT a.handle, a.follower_count, a.following_count, a.post_count,
                           a.bio, a.name, a.is_verified, a.is_private, a.profile_picture_url,
                           a.category, a.external_url, a.captured_at
                    FROM ig_accounts_flat a
                    LEFT JOIN LATERAL (
                        SELECT 1 FROM ig_posts p
                        WHERE p.workspace_id = a.workspace_id
                          AND p.account_handle = a.handle
                        LIMIT 1
                    ) posts ON true
                    WHERE a.workspace_id = :wid
                      AND a.seed = :seed
                      AND a.follower_count IS NOT NULL
                      AND (
                          (a.bio IS NOT NULL AND a.bio != '')
                          OR a.is_private = true
                      )
                      AND a.handle = ANY(:handles)
                      AND (posts IS NOT NULL OR a.is_private = true)
                    """
                ),
                {"wid": workspace_id, "seed": seed, "handles": need_handles},
            )
            rows = result.fetchall()

        merged = 0
        for row in rows:
            handle = row[0]
            indices = idx_by_handle.get(handle, [])
            for idx in indices:
                acc = accounts[idx]
                # Only merge if the account doesn't already have page data
                if acc.get("page_analyzed_at"):
                    continue
                # Inject DB data so needs_visit() returns False
                acc["page_analyzed_at"] = str(row[11]) if row[11] else "db_prefill"
                if row[1] is not None and not acc.get("follower_count_text"):
                    acc["follower_count_text"] = f"{row[1]} followers"
                if row[2] is not None and not acc.get("following_count_text"):
                    acc["following_count_text"] = f"{row[2]} following"
                if row[3] is not None and not acc.get("post_count_text"):
                    acc["post_count_text"] = f"{row[3]} posts"
                if row[4] and not acc.get("bio") and not acc.get("profile_bio"):
                    acc["profile_bio"] = row[4]
                if row[5] and not acc.get("name") and not acc.get("full_name"):
                    acc["name"] = row[5]
                if row[6] is not None:
                    acc["is_verified"] = row[6]
                if row[7] is not None:
                    acc["is_private"] = row[7]
                if row[8] and not acc.get("profile_picture_url"):
                    acc["profile_picture_url"] = row[8]
                merged += 1

        if merged > 0:
            logger.info(
                f"[PageVisitor] DB pre-merge: skipping {merged} accounts with existing page data"
            )
    except Exception as e:
        logger.debug(f"[PageVisitor] DB pre-merge query failed: {e}")


async def _scrape_grid_posts_only(page: Page, username: str) -> List[Dict[str, Any]]:
    """Quick browser scrape of just the post grid for a public account.

    Used when the API returns post_count > 0 but no edges.
    Much faster than full analyze_account_page (~3-5s vs 30-90s).
    """
    url = f"https://www.instagram.com/{username}/"
    await page.goto(url, wait_until="commit", timeout=15000)
    try:
        await page.wait_for_selector(
            "a[href*='/p/'], a[href*='/reel/']",
            state="visible",
            timeout=8000,
        )
    except Exception:
        return []  # No posts visible (e.g., empty grid, private)

    await asyncio.sleep(random_delay(0.5, 1.5))

    post_links = await page.locator("a[href*='/p/'], a[href*='/reel/']").all()
    grid_posts: List[Dict[str, Any]] = []
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
            if shortcode:
                thumbnail_url = None
                try:
                    img = link.locator("img").first
                    if await img.count() > 0:
                        thumbnail_url = await img.get_attribute("src")
                except Exception:
                    pass
                grid_posts.append({
                    "post_shortcode": shortcode,
                    "post_type": post_type,
                    "post_url": f"https://www.instagram.com{href}",
                    "thumbnail_url": thumbnail_url,
                })
        except Exception:
            continue

    if grid_posts:
        logger.info(
            "[PageVisitor] Grid post fallback: scraped %d posts for @%s",
            len(grid_posts),
            username,
        )
    return grid_posts


def needs_visit(
    account: Dict[str, Any],
    resume_revisit_errors: bool = True,
) -> bool:
    """
    Determine if an account page needs to be visited.

    Args:
        account: Account dict to check
        resume_revisit_errors: If True, revisit pages that previously errored

    Returns:
        True if the account page should be visited
    """
    if not isinstance(account, dict):
        return True
    if account.get("page_analysis_error"):
        return bool(resume_revisit_errors)
    return not is_account_page_done(account)


class PageVisitor:
    """
    Visits individual account pages to extract detailed profile statistics.
    """

    def __init__(
        self,
        per_account_timeout_sec: Optional[float] = None,
        resume_revisit_errors: Optional[bool] = None,
        max_consecutive_errors: Optional[int] = None,
    ):
        self.per_account_timeout_sec = per_account_timeout_sec or float(
            os.environ.get("IG_ACCOUNT_PAGE_TIMEOUT_SEC") or 90
        )

        if resume_revisit_errors is None:
            try:
                resume_revisit_errors = (
                    os.environ.get("IG_RESUME_REVISIT_ERRORS") or "1"
                ).strip() != "0"
            except Exception:
                resume_revisit_errors = True
        self.resume_revisit_errors = resume_revisit_errors

        if max_consecutive_errors is None:
            try:
                max_consecutive_errors = int(
                    os.environ.get("IG_MAX_CONSECUTIVE_ERRORS") or 5
                )
            except Exception:
                max_consecutive_errors = 5
        self.max_consecutive_errors = max_consecutive_errors

        # Crash recovery: max attempts to recreate page on browser crash
        try:
            self.max_crash_recoveries = int(
                os.environ.get("IG_MAX_CRASH_RECOVERIES") or 3
            )
        except Exception:
            self.max_crash_recoveries = 3

        # Periodic cache clearing: every N successful visits
        try:
            self.cache_clear_interval = int(
                os.environ.get("IG_CACHE_CLEAR_INTERVAL") or 500
            )
        except Exception:
            self.cache_clear_interval = 500

    # Extra seconds after the normal timeout before the hard kill fires.
    HARD_KILL_GRACE_SEC = 15

    async def _recreate_page(self, page: Page) -> Page:
        """Close crashed/stuck page and create a fresh one from the same context."""
        ctx = page.context
        try:
            await page.close()
        except Exception:
            pass
        new_page = await ctx.new_page()
        await new_page.add_init_script(ANTI_DETECTION_SCRIPT)
        return new_page

    def _schedule_hard_kill(self, page: Page, delay_sec: float):
        """Schedule a hard kill of the page from a background thread.

        When asyncio.wait_for can't cancel a hung Playwright operation
        (e.g. dead CDP connection), this forces the underlying transport
        closed so all pending Futures reject immediately.

        Returns a threading.Event — call .set() to cancel the kill.
        """
        import threading

        cancelled = threading.Event()

        def _killer():
            if cancelled.wait(delay_sec):
                return  # Cancelled in time
            logger.warning(
                "[PageVisitor] HARD KILL triggered — forcibly closing page "
                "after %.0fs (asyncio.wait_for failed to cancel)",
                delay_sec,
            )
            try:
                # Closing from a thread: access sync transport to sever the
                # CDP websocket.  This causes all pending Playwright Futures
                # to reject with "Target closed", unblocking the event loop.
                page._impl_obj._connection._transport.close()
            except Exception:
                pass

        t = threading.Thread(target=_killer, daemon=True, name="pw-hard-kill")
        t.start()
        return cancelled

    async def _persist_grid_posts(
        self,
        grid_posts: List[Dict[str, Any]],
        account_handle: str,
        artifact_manager: "ArtifactManager",
    ) -> None:
        """
        Persist pre-fetched grid posts to ig_posts table.
        Lightweight: only stores shortcode, type, url, thumbnail.
        Uses ON CONFLICT to avoid duplicates.
        """
        import uuid
        from datetime import datetime, timezone

        try:
            from sqlalchemy import create_engine, text

            try:
                from app.database.config import get_postgres_url_core

                engine = create_engine(get_postgres_url_core())
            except ImportError:
                from backend.app.core.database import get_db_engine

                engine = get_db_engine()

            workspace_id = getattr(artifact_manager, "workspace_id", None)
            if not workspace_id:
                return

            now = datetime.now(timezone.utc)
            with engine.connect() as conn:
                # Ensure table exists (may not be created yet)
                check = conn.execute(
                    text(
                        "SELECT 1 FROM information_schema.tables "
                        "WHERE table_name = 'ig_posts' LIMIT 1"
                    )
                ).fetchone()
                if not check:
                    logger.debug(
                        "[PageVisitor] ig_posts table does not exist yet, skipping grid persist"
                    )
                    return

                for post in grid_posts:
                    try:
                        conn.execute(
                            text(
                                """
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
                                """
                            ),
                            {
                                "id": str(uuid.uuid4()),
                                "workspace_id": workspace_id,
                                "account_handle": account_handle,
                                "post_shortcode": post["post_shortcode"],
                                "post_type": post.get("post_type", "image"),
                                "post_url": post.get("post_url"),
                                "thumbnail_url": post.get("thumbnail_url"),
                                "captured_at": now,
                            },
                        )
                    except Exception as e:
                        logger.debug(
                            f"[PageVisitor] Failed to upsert post {post.get('post_shortcode')}: {e}"
                        )
                conn.commit()
            logger.info(
                f"[PageVisitor] Pre-fetched {len(grid_posts)} posts for @{account_handle}"
            )
        except Exception as e:
            logger.debug(f"[PageVisitor] Grid posts DB persist error: {e}")

    async def visit_all_accounts(
        self,
        page: Page,
        accounts: List[Dict[str, Any]],
        artifact_manager: "ArtifactManager",
        is_resume: bool = False,
        abort_check: Optional[Callable[[], bool]] = None,
        user_data_dir: Optional[str] = None,
    ) -> Tuple[int, int, List[Dict[str, Any]], Dict[str, Any]]:
        """
        Visit all account pages and extract detailed statistics.

        Primary path: i.instagram.com private API (~0.3s/account)
        Fallback:     Playwright DOM analysis   (~30-90s/account)

        Args:
            page: Playwright page instance (kept open for fallback + avatar caching)
            accounts: List of account dicts to visit
            artifact_manager: ArtifactManager for progress updates
            is_resume: Whether this is resuming from a previous run
            user_data_dir: Browser profile dir (for loading sessionid cookie).
                           Defaults to IG_USER_DATA_DIR env or /app/data/ig-browser-profiles/default

        Returns:
            Tuple of (success_count, error_count, updated_accounts, visit_meta)
        """
        logger.info(
            f"[IGFollowingAnalyzer] Visiting {len(accounts)} account pages for detailed analysis..."
        )

        success_count = 0
        error_count = 0
        consecutive_errors = 0
        crash_recovery_count = 0
        stop_reason = "completed"
        last_error_message: Optional[str] = None
        last_error_type: Optional[str] = None
        auto_batch_pin_candidate_count = 0
        auto_batch_pin_task_count = 0

        # Stall detection: count consecutive non-success iterations (skip + error)
        stall_counter = 0
        max_stall = 20

        # Normalize accounts list
        accounts = normalize_accounts(accounts)

        # ── DB-aware skip: pre-merge existing page visit data ─────────
        # If the DB already has follower_count for an account (from a
        # previous execution), inject page_analyzed_at into the in-memory
        # dict so needs_visit() returns False and we skip re-visiting.
        try:
            _pre_merge_db_visited(accounts, artifact_manager)
        except Exception as e:
            logger.debug(f"[PageVisitor] DB pre-merge skipped: {e}")

        # ── Soft deadline: exit cleanly before runner hard-kills subprocess ──
        # Read runner timeout from env (injected by runner worker) or default.
        # Use 85% of the timeout as soft deadline to leave buffer for cleanup.
        import time as _time

        _runner_timeout = int(os.environ.get("IG_RUNNER_SOFT_DEADLINE_SECONDS", "0"))
        if not _runner_timeout:
            _runner_timeout = (
                int(os.environ.get("LOCAL_CORE_RUNNER_TASK_TIMEOUT_SECONDS", "0"))
                or 14400
            )
        _soft_deadline = _time.time() + (_runner_timeout * 0.85)

        # ── Private API Visitor setup ──────────────────────────────────────
        # Resolve storage_state.json path from provided user_data_dir or env
        import os as _os

        _udd = (
            user_data_dir
            or _os.environ.get("IG_USER_DATA_DIR")
            or _DEFAULT_USER_DATA_DIR
        )
        _storage_state_path = _os.path.join(_udd, "storage_state.json")

        _api_visitor: Optional[PrivateAPIVisitor] = None
        _api_session_invalid = False  # set True if we get a 401/403 for the whole run
        try:
            _api_visitor = PrivateAPIVisitor(storage_state_path=_storage_state_path)
            await _api_visitor.__aenter__()
            logger.info(
                "[PageVisitor] Private API visitor enabled — storage_state: %s",
                _storage_state_path,
            )
        except (FileNotFoundError, ValueError) as api_init_err:
            logger.warning(
                "[PageVisitor] Private API visitor unavailable (%s), "
                "falling back to Playwright-only mode.",
                api_init_err,
            )
            _api_visitor = None

        for i, account in enumerate(accounts):
            # ── Soft deadline: exit cleanly for auto-resume ──
            if _time.time() > _soft_deadline:
                stop_reason = "soft_deadline"
                logger.info(
                    "[IGFollowingAnalyzer] Soft deadline reached after %d/%d accounts "
                    "(%d succeeded, %d failed). Saving state for auto-resume.",
                    i,
                    len(accounts),
                    success_count,
                    error_count,
                )
                break

            # ── Abort check: stop if task was cancelled externally ──
            if abort_check and abort_check():
                stop_reason = "aborted_externally"
                logger.warning(
                    "[IGFollowingAnalyzer] Visit loop aborted — task cancelled externally "
                    "(%d succeeded, %d failed)",
                    success_count,
                    error_count,
                )
                break

            try:
                # Risk signal check periodically or after errors
                if i == 0 or i % 3 == 0 or consecutive_errors >= 2:
                    risk = await detect_risk_signal(page)
                    if risk:
                        raise ValueError(
                            risk.get("error_message")
                            or "Instagram risk signal detected"
                        )

                account_url = (
                    f"https://www.instagram.com/{account.get('username', '')}/"
                )
                if not account.get("username"):
                    continue

                # Skip already analyzed accounts (always, not just on resume)
                if not needs_visit(account, self.resume_revisit_errors):
                    logger.debug(
                        f"[IGFollowingAnalyzer] Skipping already analyzed account: {account.get('username')}"
                    )
                    continue

                # Update progress
                try:
                    await artifact_manager.upsert_progress(
                        accounts=accounts,
                        progress={
                            "stage": "visiting_pages",
                            "total_accounts": len(accounts),
                            "page_index": i,
                            "page_total": len(accounts),
                            "current_account": account.get("username"),
                            "resume_from_artifact": is_resume,
                        },
                    )
                except Exception:
                    pass

                # ── Primary: try private API first ─────────────────────────
                username_str = account.get("username") or ""
                _used_api = False

                if (
                    _api_visitor is not None
                    and not _api_visitor.is_circuit_open
                    and not _api_session_invalid
                    and username_str
                ):
                    try:
                        stats = await _api_visitor.fetch_profile(username_str)
                        _api_visitor.record_success()
                        _used_api = True
                        logger.info(
                            "[PageVisitor] ✓ API [%d/%d] @%s — %s",
                            i + 1,
                            len(accounts),
                            username_str,
                            stats.get("follower_count_text", "?"),
                        )
                    except PrivateAPIAuthError as api_auth_err:
                        logger.warning(
                            "[PageVisitor] API auth error for @%s: %s — "
                            "disabling API for this run, falling back to Playwright.",
                            username_str,
                            api_auth_err,
                        )
                        _api_session_invalid = True
                        _api_visitor.record_fallback()
                    except PrivateAPINotFound:
                        # Account genuinely doesn't exist — treat as success
                        # with a minimal result rather than forcing a browser visit
                        logger.info(
                            "[PageVisitor] @%s not found via API, skipping browser visit.",
                            username_str,
                        )
                        stats = {
                            "page_analysis_error": "account_not_found_api",
                            "page_analyzed_at": __import__("datetime")
                            .datetime.now()
                            .isoformat(),
                        }
                        _used_api = True  # don't try browser for non-existent accounts
                        _api_visitor.record_success()
                    except (PrivateAPIRateLimited, Exception) as api_err:
                        _api_visitor.record_fallback()
                        if _api_visitor.is_circuit_open:
                            logger.warning(
                                "[PageVisitor] API circuit breaker OPEN after %s — "
                                "switching to Playwright-only for remaining accounts.",
                                api_err,
                            )
                        else:
                            logger.debug(
                                "[PageVisitor] API failed for @%s (%s), "
                                "falling back to Playwright.",
                                username_str,
                                api_err,
                            )

                # ── Fallback: Playwright DOM visit ──────────────────────────
                if not _used_api:
                    # Analyze account page with timeout + hard kill watchdog
                    hard_kill_cancel = self._schedule_hard_kill(
                        page,
                        self.per_account_timeout_sec + self.HARD_KILL_GRACE_SEC,
                    )
                    try:
                        stats = await asyncio.wait_for(
                            analyze_account_page(
                                page, account_url, account.get("username")
                            ),
                            timeout=self.per_account_timeout_sec,
                        )
                        hard_kill_cancel.set()
                    except asyncio.TimeoutError:
                        hard_kill_cancel.set()
                        # Capture diagnostic screenshot on timeout
                        diag_info = ""
                        try:
                            ts = (
                                __import__("datetime")
                                .datetime.now()
                                .strftime("%Y%m%dT%H%M%S")
                            )
                            shot_path = f"/app/data/ig_visit_timeout_{account.get('username','unknown')}_{ts}.png"
                            await page.screenshot(path=shot_path)
                            diag_info += f" Screenshot: {shot_path}."
                            logger.info(
                                f"[IGFollowingAnalyzer] Timeout screenshot saved: {shot_path}"
                            )
                            try:
                                artifact_manager.add_debug_screenshot(shot_path)
                            except Exception:
                                pass
                        except Exception as ss_err:
                            logger.debug(
                                f"[IGFollowingAnalyzer] Could not save timeout screenshot: {ss_err}"
                            )

                        # Check if IG is blocking us (login wall, challenge, rate limit)
                        try:
                            risk = await detect_risk_signal(page)
                            if risk:
                                raise ValueError(
                                    f"{risk.get('error_message', 'IG risk signal')}.{diag_info} "
                                    f"Current URL: {page.url}"
                                )
                        except ValueError:
                            raise
                        except Exception:
                            pass

                        # Reset page before raising — break the cascading timeout chain.
                        stuck_url = page.url
                        try:
                            await asyncio.wait_for(
                                page.goto("about:blank", wait_until="commit"),
                                timeout=5.0,
                            )
                        except Exception:
                            try:
                                page = await self._recreate_page(page)
                            except Exception:
                                pass

                        raise TimeoutError(
                            f"Timeout analyzing {account.get('username')} (>{int(self.per_account_timeout_sec)}s).{diag_info} "
                            f"Current URL: {stuck_url}"
                        )
                    except Exception:
                        # Hard kill may have fired (Target closed) — ensure cancel
                        hard_kill_cancel.set()
                        raise

                # Update account with stats
                account.update(stats)

                # analyze_account_page catches exceptions and returns
                # {page_analysis_error: ...} instead of raising.  Detect
                # this and route to the error path.
                if stats.get("page_analysis_error"):
                    raise RuntimeError(stats["page_analysis_error"])

                # CRITICAL FIX: Clear any previous error flag so we don't revisit this account on next resume.
                account.pop("page_analysis_error", None)

                success_count += 1
                consecutive_errors = 0
                stall_counter = 0

                logger.info(
                    f"[IGFollowingAnalyzer] ✓ Analyzed [{i+1}/{len(accounts)}] {account.get('username')}: "
                    f"Followers={stats.get('follower_count_text', 'N/A')}, "
                    f"Following={stats.get('following_count_text', 'N/A')}, "
                    f"Posts={stats.get('post_count_text', 'N/A')}"
                )

                # Periodic browser cache clearing to prevent memory pressure
                if (
                    self.cache_clear_interval > 0
                    and success_count > 0
                    and success_count % self.cache_clear_interval == 0
                ):
                    try:
                        cdp = await page.context.new_cdp_session(page)
                        await cdp.send("Network.clearBrowserCache")
                        await cdp.detach()
                        logger.info(
                            f"[PageVisitor] Cleared browser cache at visit #{success_count}"
                        )
                    except Exception:
                        pass

                # ── Persist grid_posts to ig_posts (pre-fetch) ──
                grid_posts = stats.pop("grid_posts", None)
                # ── Fallback: API returned post_count but no edges ──
                # The web_profile_info API often returns count without edges.
                # When this happens for a non-private account, do a quick
                # browser scrape of just the grid posts (no full page analysis).
                if (
                    not grid_posts
                    and _used_api
                    and not account.get("is_private")
                    and stats.get("_post_count_raw", 0) > 0
                ):
                    try:
                        grid_posts = await _scrape_grid_posts_only(
                            page, account.get("username", "")
                        )
                    except Exception as e:
                        logger.debug(
                            "[PageVisitor] Grid post fallback scrape failed for @%s: %s",
                            account.get("username", ""),
                            e,
                        )
                if grid_posts and artifact_manager:
                    try:
                        await self._persist_grid_posts(
                            grid_posts,
                            account.get("username", ""),
                            artifact_manager,
                        )
                    except Exception as gp_err:
                        logger.warning(
                            f"[IGFollowingAnalyzer] Grid posts persist failed for "
                            f"{account.get('username')}: {gp_err}"
                        )
                    else:
                        try:
                            auto_batch_pin_candidate_count += 1
                            from capabilities.ig.services.auto_analyze import (
                                enqueue_visit_analysis,
                            )

                            follow_up_execution_id = enqueue_visit_analysis(
                                workspace_id=getattr(
                                    artifact_manager, "workspace_id", ""
                                ),
                                target_username=account.get("username", ""),
                                source_handle=getattr(
                                    artifact_manager, "target_username", ""
                                ),
                                user_data_dir=getattr(
                                    artifact_manager, "user_data_dir", ""
                                ),
                                parent_execution_id=getattr(
                                    artifact_manager, "trace_id", ""
                                ),
                                target_count=max(1, len(grid_posts)),
                            )
                            if follow_up_execution_id:
                                account["batch_pin_execution_id"] = (
                                    follow_up_execution_id
                                )
                                auto_batch_pin_task_count += 1
                        except Exception as follow_up_err:
                            logger.warning(
                                "[IGFollowingAnalyzer] After-visit batch pin enqueue "
                                "failed for %s (non-fatal): %s",
                                account.get("username"),
                                follow_up_err,
                            )

                # ── Cache avatar image to ig_avatars/ ──────────────────────
                # CDN URLs from IG require the IG sessionid cookie.
                # Primary:  use _api_visitor's httpx client (already has cookie)
                # Fallback: use page.request.get() (Playwright carries cookies)
                avatar_cdn_url = (
                    stats.get("profile_image_url")
                    or account.get("profile_picture_url")
                    or account.get("avatar_url")
                )
                # Write back so upsert_progress persists to ig_accounts_flat.profile_picture_url
                if avatar_cdn_url and not account.get("avatar_url"):
                    account["avatar_url"] = avatar_cdn_url
                if avatar_cdn_url and account.get("username"):
                    try:
                        from ..api.avatar_proxy import get_cache_path, AVATAR_CACHE_DIR

                        cache_path = get_cache_path(account["username"])
                        # Re-download if missing OR expired (>7 days)
                        _needs_refresh = not cache_path.exists()
                        if not _needs_refresh and cache_path.exists():
                            from datetime import datetime, timedelta
                            _age = datetime.now() - datetime.fromtimestamp(cache_path.stat().st_mtime)
                            _needs_refresh = _age > timedelta(days=7)
                        if _needs_refresh:
                            AVATAR_CACHE_DIR.mkdir(parents=True, exist_ok=True)
                            img_bytes: Optional[bytes] = None

                            # 1. Try API visitor's httpx client (has sessionid)
                            if (
                                _api_visitor is not None
                                and _api_visitor._client is not None
                            ):
                                try:
                                    img_resp = await _api_visitor._client.get(
                                        avatar_cdn_url,
                                        headers={
                                            "Accept": "image/avif,image/webp,image/apng,*/*",
                                            "Referer": "https://www.instagram.com/",
                                        },
                                    )
                                    if (
                                        img_resp.status_code == 200
                                        and len(img_resp.content) > 100
                                    ):
                                        img_bytes = img_resp.content
                                except Exception:
                                    pass

                            # 2. Fallback: Playwright browser request (carries cookies via page context)
                            if img_bytes is None:
                                try:
                                    pw_resp = await page.request.get(
                                        avatar_cdn_url,
                                        headers={
                                            "Accept": "image/avif,image/webp,image/apng,*/*",
                                            "Referer": "https://www.instagram.com/",
                                        },
                                    )
                                    if pw_resp.ok and pw_resp.status == 200:
                                        body = await pw_resp.body()
                                        if len(body) > 100:
                                            img_bytes = body
                                except Exception:
                                    pass

                            if img_bytes:
                                cache_path.write_bytes(img_bytes)
                                logger.debug(
                                    "[PageVisitor] Avatar cached: @%s (%d bytes)",
                                    account["username"],
                                    len(img_bytes),
                                )
                    except Exception as av_err:
                        logger.debug(
                            f"[PageVisitor] Avatar cache failed for "
                            f"@{account.get('username')}: {av_err}"
                        )

                # Persist updated account to DB immediately after successful page analysis
                try:
                    await artifact_manager.upsert_progress(
                        accounts=accounts,
                        progress={
                            "stage": "visiting_pages",
                            "total_accounts": len(accounts),
                            "page_index": i + 1,
                            "page_total": len(accounts),
                            "current_account": account.get("username"),
                        },
                    )
                except Exception:
                    pass

                # Seed account: persist to DB immediately so data survives
                # even if the execution fails later.  Without this, the
                # seed's own profile info is lost on every failed run.
                if account.get("_is_seed_self"):
                    try:
                        from .persistence import persist_accounts_flat

                        persist_accounts_flat(
                            workspace_id=getattr(artifact_manager, "workspace_id", ""),
                            seed=account.get("username", ""),
                            source_account_handle=getattr(
                                artifact_manager, "source_account_handle", ""
                            ),
                            source_profile_ref=getattr(
                                artifact_manager, "user_data_dir", ""
                            ),
                            accounts=[account],
                            analyzed_at=account.get("page_analyzed_at", ""),
                            execution_id=getattr(artifact_manager, "trace_id", ""),
                            trace_id=getattr(artifact_manager, "trace_id", ""),
                            artifact_id=getattr(
                                artifact_manager, "progress_artifact_id", None
                            ),
                            schema_version=None,
                            seed_version=None,
                            capture_method="seed_self_visit",
                            run_mode=None,
                        )
                        logger.info(
                            "[PageVisitor] Seed '%s' profile persisted to DB immediately",
                            account.get("username"),
                        )
                    except Exception as db_err:
                        logger.warning(
                            "[PageVisitor] Seed DB persist failed (non-fatal): %s",
                            db_err,
                        )

                # Random delay between accounts
                if i < len(accounts) - 1:
                    delay = random_delay(3, 8) + min(
                        12.0, float(consecutive_errors) * 3.0
                    )
                    logger.debug(
                        f"[IGFollowingAnalyzer] Waiting {delay:.2f}s before next account..."
                    )
                    await asyncio.sleep(delay)

            except Exception as e:
                error_msg_lower = str(e).lower()
                is_browser_crash = any(
                    sig in error_msg_lower for sig in BROWSER_CRASH_SIGNATURES
                )

                # ── Browser crash recovery ──────────────────────
                # When the Chromium renderer dies, the page object is unusable.
                # Close it, create a fresh page from the same context, and retry.
                if (
                    is_browser_crash
                    and crash_recovery_count < self.max_crash_recoveries
                ):
                    crash_recovery_count += 1
                    logger.warning(
                        f"[PageVisitor] Browser crash detected "
                        f"({crash_recovery_count}/{self.max_crash_recoveries}), "
                        f"attempting page recovery for {account.get('username')}..."
                    )
                    try:
                        page = await self._recreate_page(page)
                        logger.info(
                            "[PageVisitor] Page recovery successful, "
                            "will retry current account"
                        )
                        # Cooldown before retrying
                        await asyncio.sleep(random_delay(5, 10))
                        # Retry: re-analyze the same account with fresh page
                        try:
                            stats = await asyncio.wait_for(
                                analyze_account_page(
                                    page, account_url, account.get("username")
                                ),
                                timeout=self.per_account_timeout_sec,
                            )
                            account.update(stats)
                            account.pop("page_analysis_error", None)
                            success_count += 1
                            consecutive_errors = 0
                            logger.info(
                                f"[PageVisitor] Recovery succeeded for {account.get('username')}"
                            )
                            continue
                        except Exception as retry_err:
                            logger.warning(
                                f"[PageVisitor] Recovery retry also failed for "
                                f"{account.get('username')}: {retry_err}"
                            )
                            # Fall through to normal error handling
                    except Exception as recovery_err:
                        logger.error(
                            f"[PageVisitor] Page recovery failed: {recovery_err}"
                        )

                error_count += 1
                consecutive_errors += 1
                last_error_message = str(e)[:300]
                last_error_type = classify_failure(str(e), page.url if page else None)
                logger.warning(
                    f"[IGFollowingAnalyzer] ✗ [{consecutive_errors}/{self.max_consecutive_errors}] "
                    f"Failed to analyze account {account.get('username')}: {e}"
                )
                account["page_analysis_error"] = str(e)

                # Keep UI updated even on failures so it doesn't go stale.
                try:
                    await artifact_manager.upsert_progress(
                        accounts=accounts,
                        progress={
                            "stage": "visiting_pages",
                            "total_accounts": len(accounts),
                            "page_index": i,
                            "page_total": len(accounts),
                            "current_account": account.get("username"),
                            "consecutive_errors": consecutive_errors,
                            "max_consecutive_errors": self.max_consecutive_errors,
                            "error_type": last_error_type,
                            "error_message": last_error_message,
                        },
                    )
                except Exception:
                    pass

                # Circuit breaker: stop after N consecutive errors
                if consecutive_errors >= self.max_consecutive_errors:
                    stop_reason = "circuit_breaker"
                    logger.error(
                        f"[IGFollowingAnalyzer] ✗✗✗ CIRCUIT BREAKER TRIPPED ✗✗✗\n"
                        f"  {consecutive_errors} consecutive errors reached threshold ({self.max_consecutive_errors}).\n"
                        f"  Last error: {last_error_message}\n"
                        f"  Stopping visit phase. {success_count} succeeded, {error_count} failed."
                    )
                    break

                # Error delay with backoff
                error_delay = random_delay(2, 5) + min(
                    15.0, float(consecutive_errors) * 3.5
                )
                await asyncio.sleep(error_delay)

                # Stall detection: break if too many non-success iterations
                stall_counter += 1
                if stall_counter >= max_stall:
                    stop_reason = "visit_stalled"
                    logger.warning(
                        "[IGFollowingAnalyzer] Visit loop stalled: %d consecutive "
                        "non-success iterations. %d succeeded, %d failed.",
                        stall_counter,
                        success_count,
                        error_count,
                    )
                    break

        # ── Tear down private API visitor ────────────────────────────────
        if _api_visitor is not None:
            try:
                await _api_visitor.__aexit__(None, None, None)
            except Exception:
                pass

        visit_meta = {
            "stop_reason": stop_reason,
            "last_error_message": last_error_message,
            "last_error_type": last_error_type,
            "consecutive_errors_at_stop": consecutive_errors,
            "api_success": getattr(_api_visitor, "_total_api_success", 0),
            "api_fallback": getattr(_api_visitor, "_total_api_fallback", 0),
            "auto_batch_pin_candidate_count": auto_batch_pin_candidate_count,
            "auto_batch_pin_task_count": auto_batch_pin_task_count,
        }

        logger.info(
            "[IGFollowingAnalyzer] Page analysis %s: %d succeeded, %d failed "
            "(api_success=%d, api_fallback=%d, auto_batch_pin=%d/%d)",
            stop_reason,
            success_count,
            error_count,
            visit_meta["api_success"],
            visit_meta["api_fallback"],
            auto_batch_pin_task_count,
            auto_batch_pin_candidate_count,
        )

        return success_count, error_count, accounts, visit_meta


async def visit_account_pages(
    page: Page,
    accounts: List[Dict[str, Any]],
    artifact_manager: "ArtifactManager",
    is_resume: bool = False,
    per_account_timeout_sec: Optional[float] = None,
) -> Tuple[int, int, List[Dict[str, Any]], Dict[str, Any]]:
    """
    Convenience function to visit account pages.

    Args:
        page: Playwright page instance
        accounts: List of account dicts to visit
        artifact_manager: ArtifactManager for progress updates
        is_resume: Whether this is resuming from a previous run
        per_account_timeout_sec: Timeout per account page

    Returns:
        Tuple of (success_count, error_count, updated_accounts, visit_meta)
    """
    visitor = PageVisitor(per_account_timeout_sec=per_account_timeout_sec)
    return await visitor.visit_all_accounts(page, accounts, artifact_manager, is_resume)
