"""
Page visitor for Instagram following analyzer.

This module handles visiting individual account pages and extracting
detailed profile statistics.
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

if TYPE_CHECKING:
    from .artifact_manager import ArtifactManager

logger = logging.getLogger(__name__)

# Error signatures that indicate a browser crash (page is dead, cannot be reused)
BROWSER_CRASH_SIGNATURES = ("page crashed", "target closed", "browser disconnected")


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
                    SELECT handle, follower_count, following_count, post_count,
                           bio, name, is_verified, is_private, profile_picture_url,
                           category, external_url, captured_at
                    FROM ig_accounts_flat
                    WHERE workspace_id = :wid
                      AND follower_count IS NOT NULL
                      AND bio IS NOT NULL
                      AND bio != ''
                      AND handle = ANY(:handles)
                    ORDER BY handle, captured_at DESC
                    """
                ),
                {"wid": workspace_id, "handles": need_handles},
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
    ) -> Tuple[int, int, List[Dict[str, Any]], Dict[str, Any]]:
        """
        Visit all account pages and extract detailed statistics.

        Args:
            page: Playwright page instance
            accounts: List of account dicts to visit
            artifact_manager: ArtifactManager for progress updates
            is_resume: Whether this is resuming from a previous run

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

                account_url = account.get("account_link")
                if not account_url:
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

                # Analyze account page with timeout
                try:
                    stats = await asyncio.wait_for(
                        analyze_account_page(
                            page, account_url, account.get("username")
                        ),
                        timeout=self.per_account_timeout_sec,
                    )
                except asyncio.TimeoutError:
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
                        # Register with artifact_manager so it appears in the Debug Card
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
                            # Fatal: IG is blocking — no point retrying more accounts
                            raise ValueError(
                                f"{risk.get('error_message', 'IG risk signal')}.{diag_info} "
                                f"Current URL: {page.url}"
                            )
                    except ValueError:
                        raise  # Re-raise the risk signal error
                    except Exception:
                        pass

                    # Reset page before raising — break the cascading timeout chain.
                    # When asyncio.wait_for cancels the coroutine, Playwright's in-flight
                    # page.goto() is still pending. The next page.goto() queues behind it,
                    # causing every subsequent visit to also timeout.
                    stuck_url = page.url
                    try:
                        await asyncio.wait_for(
                            page.goto("about:blank", wait_until="commit"),
                            timeout=5.0,
                        )
                    except Exception:
                        pass

                    raise TimeoutError(
                        f"Timeout analyzing {account.get('username')} (>{int(self.per_account_timeout_sec)}s).{diag_info} "
                        f"Current URL: {stuck_url}"
                    )

                # Update account with stats
                account.update(stats)
                # CRITICAL FIX: Clear any previous error flag so we don't revisit this account on next resume.
                account.pop("page_analysis_error", None)

                success_count += 1
                consecutive_errors = 0

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
                if grid_posts and artifact_manager:
                    try:
                        await self._persist_grid_posts(
                            grid_posts,
                            account.get("username", ""),
                            artifact_manager,
                        )
                    except Exception as gp_err:
                        logger.debug(
                            f"[IGFollowingAnalyzer] Grid posts persist failed for "
                            f"{account.get('username')}: {gp_err}"
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
                        try:
                            await page.close()
                        except Exception:
                            pass
                        page = await page.context.new_page()
                        await page.add_init_script(ANTI_DETECTION_SCRIPT)
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

        visit_meta = {
            "stop_reason": stop_reason,
            "last_error_message": last_error_message,
            "last_error_type": last_error_type,
            "consecutive_errors_at_stop": consecutive_errors,
        }

        logger.info(
            f"[IGFollowingAnalyzer] Page analysis {stop_reason}: {success_count} succeeded, {error_count} failed"
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
