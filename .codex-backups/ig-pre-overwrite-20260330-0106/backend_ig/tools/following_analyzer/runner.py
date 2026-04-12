"""
Instagram Following Analyzer - Main Runner Module

This module provides the main entry point for analyzing Instagram following lists.
It orchestrates the various components: browser session, scrolling, page visiting,
artifact management, and persistence.
"""

import asyncio
import logging
import os
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


from typing import Any, Dict, List, Optional

from playwright.async_api import Page

from backend.app.services.stores.postgres.artifacts_store import PostgresArtifactsStore

from capabilities.ig.source_filters import should_persist_source_pool
from .artifact_manager import ArtifactManager
from .auth import assert_logged_in, try_get_logged_in_username
from .browser_session import BrowserSession, prepare_browser_runtime
from .page_visitor import PageVisitor
from .persistence import (
    get_saved_count,
    load_accounts_from_db,
    persist_accounts_flat,
    persist_follow_edges,
)
from .search_extract import extract_following_by_search
from .progress import generate_summary
from .resume_manager import ResumeManager
from .scroll_extract import extract_following_list
from .utils import classify_failure, random_delay
from .watchdog import create_and_start_watchdog

logger = logging.getLogger(__name__)

# Default browser profile directory
DEFAULT_USER_DATA_DIR = "/app/data/ig-browser-profiles/default"


def _compact_error_message(error: Exception, limit: int = 240) -> str:
    """Trim noisy exception strings before persisting them into progress metadata."""
    message = (str(error) or error.__class__.__name__).strip()
    if len(message) <= limit:
        return message
    return f"{message[: limit - 3]}..."


def _build_pre_scroll_progress(
    *,
    stage: str,
    visit_account_pages: bool,
    run_mode: Optional[str],
    expected_following_count: Optional[int],
    status: str = "running",
    **extra: Any,
) -> Dict[str, Any]:
    """Build a consistent progress payload for phases before the scroll loop starts."""
    progress: Dict[str, Any] = {
        "stage": stage,
        "phase_group": "pre_scroll",
        "pre_scroll_phase": stage,
        "pre_scroll_status": status,
        "total_accounts": 0,
        "targets": 0,
        "expected": expected_following_count,
        "saved": 0,
        "visit_account_pages": visit_account_pages,
        "run_mode": (run_mode or "full").strip().lower() or "full",
    }
    for key, value in extra.items():
        if value is not None:
            progress[key] = value
    return progress


async def _upsert_pre_scroll_progress(
    *,
    artifact_manager: ArtifactManager,
    stage: str,
    visit_account_pages: bool,
    run_mode: Optional[str],
    status: str = "running",
    **extra: Any,
) -> None:
    """Persist pre-scroll progress so stuck runs stop looking like `profile_loaded` forever."""
    artifact_manager.update_pre_scroll_state(
        pre_scroll_phase=stage,
        pre_scroll_status=status,
        **{key: value for key, value in extra.items() if value is not None},
    )
    await artifact_manager.upsert_progress(
        accounts=[],
        progress=_build_pre_scroll_progress(
            stage=stage,
            visit_account_pages=visit_account_pages,
            run_mode=run_mode,
            expected_following_count=artifact_manager.expected_following_count,
            status=status,
            **extra,
        ),
    )


async def ig_analyze_following(
    target_username: str,
    workspace_id: str,
    execution_id: Optional[str] = None,
    max_accounts: Optional[int] = None,
    visit_account_pages: bool = True,
    run_mode: Optional[str] = None,
    allow_partial_resume: bool = False,
    user_data_dir: Optional[str] = None,
    trace_id: Optional[str] = None,
    seed_posts_count: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Extract Instagram following list and analyze account pages.

    Args:
        target_username: Instagram username to analyze
        workspace_id: Workspace ID for artifact storage
        execution_id: Optional execution ID for tracing
        max_accounts: Maximum accounts to extract (None = all)
        visit_account_pages: Whether to visit individual account pages
        run_mode: 'list' (scroll only), 'visit' (resume + visit), 'full' (scroll + visit)
        allow_partial_resume: Allow resume on incomplete lists
        user_data_dir: Browser profile directory
        trace_id: Trace ID for artifact tracking

    Returns:
        Dict containing summary, accounts list, and metadata
    """
    # Log configuration
    logger.info("=" * 80)
    logger.info("[IGFollowingAnalyzer] Starting analysis")
    logger.info(f"  Target Username: {target_username}")
    logger.info(f"  Workspace ID: {workspace_id}")
    logger.info(f"  Execution ID: {execution_id}")
    logger.info(f"  Max Accounts: {max_accounts}")
    logger.info(f"  Visit Account Pages: {visit_account_pages}")

    # Normalize user_data_dir
    if user_data_dir is not None:
        user_data_dir = user_data_dir.strip() or None
    if not user_data_dir:
        user_data_dir = DEFAULT_USER_DATA_DIR
    logger.info(f"  User Data Dir: {user_data_dir}")

    # Use trace_id or fall back to execution_id
    if not trace_id:
        trace_id = (execution_id or "").strip() or None
    logger.info(f"  Trace ID: {trace_id}")
    logger.info("=" * 80)

    # Write seed bootstrap record immediately at start
    # This ensures the seed appears in the seed list right away

    persist_accounts_flat(
        workspace_id=workspace_id,
        seed=target_username,
        source_account_handle=None,
        source_profile_ref=f"https://www.instagram.com/{target_username}/",
        accounts=[{"username": target_username, "fetched_at": _utc_now().isoformat()}],
        analyzed_at=_utc_now().isoformat(),
        execution_id=execution_id,
        trace_id=trace_id,
        artifact_id=None,
        schema_version="ig.seed_bootstrap.v1",
        seed_version=trace_id,
        capture_method="seed_init",
        run_mode=run_mode,
        source_context="following_list",
    )
    logger.info(
        f"[IGFollowingAnalyzer] Seed '{target_username}' bootstrap record written"
    )

    # Initialize state
    schema_version = "ig.following_list.v1"
    seed_version = trace_id
    latest_accounts: List[Dict[str, Any]] = []
    last_url: Optional[str] = None
    artifact_manager = None
    watchdog = None

    try:
        # Initialize artifacts store
        artifacts_store: Optional[PostgresArtifactsStore] = None
        if workspace_id and trace_id:
            try:
                artifacts_store = PostgresArtifactsStore()
                _debug_log(
                    f"PostgresArtifactsStore initialized: workspace_id={workspace_id}, trace_id={trace_id}"
                )
            except Exception as e:
                logger.warning(
                    f"[IGFollowingAnalyzer] Failed to initialize artifacts store: {e}"
                )
                _debug_log(f"artifacts_store init FAILED: {e}")
        else:
            _debug_log(
                f"artifacts_store NOT initialized: workspace_id={workspace_id}, trace_id={trace_id}"
            )

        # Initialize managers
        artifact_manager = ArtifactManager(
            artifacts_store=artifacts_store,
            workspace_id=workspace_id,
            trace_id=trace_id,
            target_username=target_username,
            user_data_dir=user_data_dir,
            visit_account_pages=visit_account_pages,
            schema_version=schema_version,
            seed_version=seed_version,
            run_mode=run_mode,
        )

        resume_manager = ResumeManager(
            artifacts_store=artifacts_store,
            workspace_id=workspace_id,
            target_username=target_username,
            user_data_dir=user_data_dir,
            run_mode=run_mode,
        )

        # Start watchdog thread
        watchdog = create_and_start_watchdog(artifact_manager)

        # Initial progress update
        try:
            await artifact_manager.upsert_progress(
                accounts=[],
                progress={
                    "stage": "initial_collect",
                    "iteration": 0,
                    "targets": 0,
                    "expected": None,
                    "saved": 0,
                    "visit_account_pages": visit_account_pages,
                    "run_mode": run_mode,
                },
            )
            _debug_log("Initial progress artifact upsert SUCCEEDED")
        except Exception as e:
            _debug_log(f"Initial progress artifact upsert FAILED: {e}")

        # Main browser session with crash-retry loop.
        # When Chromium crashes (zombie processes, corrupted cache), retry with
        # a fresh session after cleanup. Independent of playbook-level retries.
        try:
            max_browser_retries = int(os.environ.get("IG_MAX_BROWSER_RETRIES") or 2)
        except Exception:
            max_browser_retries = 2

        browser_session = BrowserSession(user_data_dir)

        for browser_attempt in range(1, max_browser_retries + 1):
            try:
                async with browser_session as (browser, context, page):
                    try:
                        result = await _run_analysis(
                            page=page,
                            context=context,
                            target_username=target_username,
                            workspace_id=workspace_id,
                            artifact_manager=artifact_manager,
                            resume_manager=resume_manager,
                            trace_id=trace_id,
                            max_accounts=max_accounts,
                            visit_account_pages=visit_account_pages,
                            run_mode=run_mode,
                            allow_partial_resume=allow_partial_resume,
                            schema_version=schema_version,
                            seed_version=seed_version,
                            seed_posts_count=seed_posts_count,
                            watchdog=watchdog,
                        )
                        latest_accounts = result.get("accounts", [])
                        return result
                    finally:
                        try:
                            last_url = page.url if page else last_url
                        except Exception:
                            pass
            except Exception as browser_err:
                error_type = classify_failure(str(browser_err), last_url)
                if (
                    error_type == "browser_crash"
                    and browser_attempt < max_browser_retries
                ):
                    logger.warning(
                        f"[IGFollowingAnalyzer] Browser crash on attempt "
                        f"{browser_attempt}/{max_browser_retries}, "
                        f"retrying with fresh session..."
                    )
                    prepare_browser_runtime(user_data_dir, reap_zombies=True)
                    browser_session = BrowserSession(user_data_dir)
                    await asyncio.sleep(random_delay(3, 6))
                    continue
                raise

    except Exception as e:
        # Error handling
        try:
            error_message = str(e)
            error_type = classify_failure(error_message, last_url)
            if artifact_manager:
                await artifact_manager.upsert_progress(
                    accounts=latest_accounts,
                    progress={
                        "stage": "error",
                        "error_type": error_type,
                        "error_message": error_message[:800],
                        "last_url": last_url,
                        "total_accounts": len(latest_accounts),
                    },
                )
        except Exception:
            pass

        logger.error("=" * 80)
        logger.error(f"[IGFollowingAnalyzer] ✗ Analysis failed: {e}")
        logger.error("=" * 80, exc_info=True)
        raise
    finally:
        if watchdog:
            watchdog.stop()


from .seed_posts import extract_seed_posts as _extract_seed_posts


async def _run_analysis(
    page: Page,
    context,
    target_username: str,
    workspace_id: str,
    artifact_manager: ArtifactManager,
    resume_manager: ResumeManager,
    trace_id: Optional[str],
    max_accounts: Optional[int],
    visit_account_pages: bool,
    run_mode: Optional[str],
    allow_partial_resume: bool,
    schema_version: str,
    seed_version: Optional[str],
    seed_posts_count: Optional[int] = None,
    watchdog=None,
) -> Dict[str, Any]:
    """
    Core analysis logic - separated for cleaner error handling.
    """
    # Navigate to profile
    profile_url = f"https://www.instagram.com/{target_username}/"
    logger.info(f"[IGFollowingAnalyzer] Navigating to profile: {profile_url}")

    await page.goto(profile_url, wait_until="domcontentloaded", timeout=120000)
    try:
        await page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    logger.info("[IGFollowingAnalyzer] Page loaded successfully")
    await asyncio.sleep(random_delay(2, 4))

    # Save debug screenshot
    await _save_debug_screenshot(page, artifact_manager, trace_id)
    await artifact_manager.upsert_progress(
        accounts=[], progress={"stage": "profile_loaded", "total_accounts": 0}
    )

    # Verify login
    await assert_logged_in(page)
    source_account_handle = await try_get_logged_in_username(page)
    artifact_manager.set_source_account_handle(source_account_handle)

    # Register seed immediately so it appears in the seed list dropdown right away
    from .persistence import register_seed_immediately

    register_seed_immediately(
        workspace_id=workspace_id,
        seed=target_username,
        execution_id=trace_id,
        source_handle=source_account_handle,
        source_profile_ref=artifact_manager.user_data_dir,
    )

    # Handle run mode routing
    mode = (run_mode or "full").strip().lower()
    if mode == "list":
        visit_account_pages = False
    elif mode == "visit":
        visit_account_pages = True

    # Try to resume from existing artifact
    resumed = resume_manager.load_resume_accounts()
    accounts: List[Dict[str, Any]] = []
    expected_following_count: Optional[int] = None
    scroll_stop_reason: Optional[str] = None
    list_capture_status: Optional[str] = None
    list_capture_evidence: Optional[Dict[str, Any]] = None

    if resumed:
        accounts = resumed.get("accounts") or []
        meta0 = resumed.get("meta") or {}
        expected_following_count = meta0.get("expected_following_count")
        list_capture_status = meta0.get("list_capture_status")
        lce0 = meta0.get("list_capture_evidence")
        if isinstance(lce0, dict):
            list_capture_evidence = lce0
        scroll_stop_reason = "resume_from_artifact"
        logger.info(
            f"[IGFollowingAnalyzer] Resume enabled: loaded {len(accounts)} accounts from artifact"
        )
    elif mode == "visit":
        raise ValueError(
            "run_mode='visit' requires an existing accounts list, but none was found. "
            "Please run 'rerun list' first to build a full list."
        )

    # Parse expected following count from profile
    expected_following_count = (
        await _parse_following_count(page) or expected_following_count
    )
    if expected_following_count:
        artifact_manager.set_expected_following_count(expected_following_count)
        logger.info(
            f"[IGFollowingAnalyzer] Expected following count: {expected_following_count}"
        )

    # Checkpoint storage state
    storage_state_path = os.path.join(
        artifact_manager.user_data_dir or "", "storage_state.json"
    )
    if storage_state_path and artifact_manager.user_data_dir:
        try:
            await context.storage_state(path=storage_state_path)
            logger.info(
                f"[IGFollowingAnalyzer] Checkpointed storage_state: {storage_state_path}"
            )
        except Exception as e:
            logger.warning(
                f"[IGFollowingAnalyzer] Failed to checkpoint storage_state: {e}"
            )

    # ── Seed post extraction (before scroll phase) ────────────────
    # When running full/list mode, automatically extract the seed account's
    # own posts and persist to ig_posts.  This ensures the seed's Posts tab
    # has data without requiring a separate ig_analyze_content run.
    if mode in ("full", "list"):
        _spc = seed_posts_count if seed_posts_count and seed_posts_count > 0 else 30
        seed_posts_started_at = _utc_now().isoformat()
        await _upsert_pre_scroll_progress(
            artifact_manager=artifact_manager,
            stage="seed_posts",
            visit_account_pages=visit_account_pages,
            run_mode=mode,
            status="running",
            seed_posts_status="running",
            seed_posts_started_at=seed_posts_started_at,
            seed_posts_target_count=_spc,
        )
        try:
            seed_posts_persisted = await _extract_seed_posts(
                page=page,
                seed_handle=target_username,
                workspace_id=workspace_id,
                target_count=_spc,
                trace_id=trace_id,
            )
            artifact_manager.update_pre_scroll_state(
                seed_posts_status="completed",
                seed_posts_completed_at=_utc_now().isoformat(),
                seed_posts_persisted_count=seed_posts_persisted,
            )
        except Exception as e:
            artifact_manager.update_pre_scroll_state(
                seed_posts_status="failed",
                seed_posts_completed_at=_utc_now().isoformat(),
                seed_posts_error=_compact_error_message(e),
            )
            logger.warning(
                f"[IGFollowingAnalyzer] Seed post extraction failed (non-fatal): {e}"
            )
        # Ensure we're back on the seed profile after post extraction.
        # CRITICAL: We must check that the URL is actually the profile page,
        # not just that it contains the username. Post URLs like
        # /dearruigallery/p/DSz57dFD5YM/ also contain the username but do NOT
        # have the Following button — causing _find_following_button() to fail.
        try:
            current = (page.url or "").rstrip("/").lower()
            expected_profile_suffix = f"instagram.com/{target_username.lower()}"
            is_on_profile = current.endswith(expected_profile_suffix)
            if not is_on_profile:
                logger.info(
                    f"[IGFollowingAnalyzer] Not on profile page after seed post extraction "
                    f"(current={page.url}), navigating back to profile"
                )
                await page.goto(
                    f"https://www.instagram.com/{target_username}/",
                    wait_until="domcontentloaded",
                    timeout=30000,
                )
                await asyncio.sleep(random_delay(1, 2))
        except Exception:
            pass

    # Seed self-visit: scrape seed profile data BEFORE scroll.
    # Uses visit_all_accounts with single-element list to inherit all
    # timeout/crash-recovery/DB-persist infrastructure.
    if mode in ("full", "list"):
        seed_self_visit_started_at = _utc_now().isoformat()
        await _upsert_pre_scroll_progress(
            artifact_manager=artifact_manager,
            stage="seed_self_visit",
            visit_account_pages=visit_account_pages,
            run_mode=mode,
            status="running",
            seed_self_visit_status="running",
            seed_self_visit_started_at=seed_self_visit_started_at,
        )
        try:
            _seed_account = {
                "username": target_username,
                "fetched_at": _utc_now().isoformat(),
                "_is_seed_self": True,
            }
            _seed_visitor = PageVisitor()
            await _seed_visitor.visit_all_accounts(
                page=page,
                accounts=[_seed_account],
                artifact_manager=artifact_manager,
                is_resume=False,
                user_data_dir=artifact_manager.user_data_dir,
            )
            artifact_manager.update_pre_scroll_state(
                seed_self_visit_status="completed",
                seed_self_visit_completed_at=_utc_now().isoformat(),
                pre_scroll_status="completed",
                pre_scroll_completed_at=_utc_now().isoformat(),
            )
            logger.info("[IGFollowingAnalyzer] Seed self-visit completed before scroll")
        except Exception as e:
            artifact_manager.update_pre_scroll_state(
                seed_self_visit_status="failed",
                seed_self_visit_completed_at=_utc_now().isoformat(),
                seed_self_visit_error=_compact_error_message(e),
            )
            logger.warning(
                "[IGFollowingAnalyzer] Seed self-visit failed (non-fatal): %s", e
            )
        # Navigate back to seed profile after self-visit
        try:
            current = (page.url or "").rstrip("/").lower()
            expected_profile_suffix = f"instagram.com/{target_username.lower()}"
            if not current.endswith(expected_profile_suffix):
                await page.goto(
                    f"https://www.instagram.com/{target_username}/",
                    wait_until="domcontentloaded",
                    timeout=30000,
                )
                await asyncio.sleep(random_delay(1, 2))
        except Exception:
            pass

    # Multi-round scroll with auto-restart
    # When scrolling gets stuck (exhausted_incomplete, no_new_accounts_streak, etc.),
    # automatically close the dialog, navigate back to the profile, re-open the
    # following dialog, and start a fresh scroll round. Each round persists results
    # via UPSERT so accounts accumulate across rounds.
    if not resumed:
        try:
            max_scroll_rounds = int(os.environ.get("IG_SCROLL_MAX_ROUNDS") or 5)
        except Exception:
            max_scroll_rounds = 5
        if max_scroll_rounds < 1:
            max_scroll_rounds = 1

        total_scroll_rounds = 0
        all_round_accounts: List[Dict[str, Any]] = []

        for scroll_round in range(1, max_scroll_rounds + 1):
            # ── Abort check: stop if task was cancelled externally ──
            if watchdog and watchdog.is_abort_requested():
                logger.warning(
                    "[IGFollowingAnalyzer] Scroll loop aborted — task cancelled externally"
                )
                scroll_stop_reason = "aborted_externally"
                break

            total_scroll_rounds = scroll_round

            # Check if persisted dedup count already meets expected
            if expected_following_count and not max_accounts:
                try:
                    saved = get_saved_count(workspace_id, target_username)
                    if saved >= int(expected_following_count):
                        logger.info(
                            f"[IGFollowingAnalyzer] Round {scroll_round}: saved_count ({saved}) "
                            f">= expected ({expected_following_count}), skipping scroll"
                        )
                        scroll_stop_reason = "saved_dedup_count_reached"
                        list_capture_status = "full"
                        break
                except Exception:
                    pass

            # Navigate to profile (rounds > 1 need full reload to reset dialog state)
            if scroll_round > 1:
                logger.info(
                    f"[IGFollowingAnalyzer] === Round {scroll_round}/{max_scroll_rounds}: "
                    f"reloading profile to start fresh scroll ==="
                )
                # Anti-detection delay between rounds (increases with each round)
                round_delay = random_delay(8, 15) + (scroll_round - 1) * 2.0
                logger.info(
                    f"[IGFollowingAnalyzer] Anti-detection delay: {round_delay:.1f}s"
                )
                await asyncio.sleep(round_delay)

                await page.goto(
                    profile_url, wait_until="domcontentloaded", timeout=120000
                )
                try:
                    await page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass
                await asyncio.sleep(random_delay(2, 4))

            # Click Following button and open dialog
            following_button = await _find_following_button(page, target_username)
            await following_button.scroll_into_view_if_needed()
            await asyncio.sleep(random_delay(0.2, 0.6))
            await following_button.click(timeout=30000, force=True)
            logger.info(
                f"[IGFollowingAnalyzer] Round {scroll_round}/{max_scroll_rounds}: "
                f"clicked Following button, waiting for dialog"
            )
            await asyncio.sleep(random_delay(2, 4))

            dialog = await _find_following_dialog(page, target_username)

            await artifact_manager.upsert_progress(
                accounts=all_round_accounts,
                progress={
                    "stage": "dialog_opened",
                    "iteration": 0,
                    "total_accounts": len(all_round_accounts),
                    "scroll_round": scroll_round,
                    "scroll_total_rounds": max_scroll_rounds,
                },
            )

            # Build on_progress callback that surfaces screenshots in real-time
            _sr, _smr = scroll_round, max_scroll_rounds

            async def _scroll_progress_cb(accounts, progress, *, _round=_sr, _max=_smr):
                # Register any new screenshots immediately
                new_shots = progress.get("screenshots") or []
                for shot in new_shots:
                    if shot not in artifact_manager.scroll_debug_screenshots:
                        artifact_manager.add_debug_screenshot(str(shot))
                await artifact_manager.upsert_progress(
                    accounts=accounts,
                    progress={
                        **progress,
                        "scroll_round": _round,
                        "scroll_total_rounds": _max,
                        "saved": get_saved_count(workspace_id, target_username),
                    },
                )

            round_accounts, scroll_meta = await extract_following_list(
                page,
                dialog,
                max_accounts,
                expected_following_count=expected_following_count,
                trace_id=trace_id,
                on_progress=_scroll_progress_cb,
                get_saved_count=lambda: get_saved_count(workspace_id, target_username),
            )

            scroll_stop_reason = (scroll_meta or {}).get("stop_reason")
            list_capture_status = (scroll_meta or {}).get("list_capture_status")
            list_capture_evidence = (scroll_meta or {}).get("list_capture_evidence")
            is_retryable = (scroll_meta or {}).get("is_retryable", False)

            if scroll_stop_reason == "saved_dedup_count_reached":
                # The effective saved list already satisfies the expected target,
                # so downstream visit/result stages should treat the list phase as full.
                list_capture_status = "full"

            # Merge round accounts into cumulative list (dedup by username)
            existing_usernames = {a.get("username") for a in all_round_accounts}
            new_in_round = 0
            for acc in round_accounts:
                uname = (acc.get("username") or "").strip()
                if uname and uname not in existing_usernames:
                    all_round_accounts.append(acc)
                    existing_usernames.add(uname)
                    new_in_round += 1

            logger.info(
                f"[IGFollowingAnalyzer] Round {scroll_round}/{max_scroll_rounds}: "
                f"got {len(round_accounts)} (new={new_in_round}), "
                f"cumulative={len(all_round_accounts)}, "
                f"stop_reason={scroll_stop_reason}, retryable={is_retryable}"
            )

            # Persist this round's results immediately (UPSERT accumulates)
            try:
                persist_accounts_flat(
                    workspace_id=workspace_id,
                    seed=target_username,
                    source_account_handle=artifact_manager.source_account_handle,
                    source_profile_ref=artifact_manager.user_data_dir,
                    accounts=round_accounts,
                    analyzed_at=datetime.now().isoformat(),
                    execution_id=trace_id,
                    trace_id=trace_id,
                    artifact_id=artifact_manager.progress_artifact_id,
                    schema_version=schema_version,
                    seed_version=seed_version,
                    capture_method="following_list",
                    run_mode=run_mode,
                    source_context="following_list",
                )
            except Exception:
                pass

            # Persist suggestion and unknown pools separately (source attribution v7)
            _sa = (scroll_meta or {}).get("source_attribution") or {}
            for _pool_key, _pool_ctx in [
                ("suggestion_accounts", "suggestion"),
                ("unknown_accounts", "unknown"),
            ]:
                _pool = (scroll_meta or {}).get(_pool_key) or []
                if _pool:
                    if not should_persist_source_pool(_pool_ctx, scroll_stop_reason):
                        logger.info(
                            "[IGFollowingAnalyzer] Skipping %s account persist for seed=%s "
                            "(stop_reason=%s, count=%s)",
                            _pool_ctx,
                            target_username,
                            scroll_stop_reason,
                            len(_pool),
                        )
                        continue
                    try:
                        persist_accounts_flat(
                            workspace_id=workspace_id,
                            seed=target_username,
                            source_account_handle=artifact_manager.source_account_handle,
                            source_profile_ref=artifact_manager.user_data_dir,
                            accounts=_pool,
                            analyzed_at=datetime.now().isoformat(),
                            execution_id=trace_id,
                            trace_id=trace_id,
                            artifact_id=artifact_manager.progress_artifact_id,
                            schema_version=schema_version,
                            seed_version=seed_version,
                            capture_method="following_list",
                            run_mode=run_mode,
                            source_context=_pool_ctx,
                        )
                        logger.info(
                            f"[IGFollowingAnalyzer] Persisted {len(_pool)} {_pool_ctx} accounts for seed={target_username}"
                        )
                    except Exception:
                        pass

            # Log source attribution state if available
            if _sa:
                logger.info(
                    f"[IGFollowingAnalyzer] Source attribution: dialog_state={_sa.get('dialog_state')}, "
                    f"following_list={_sa.get('following_list_count', 0)}, "
                    f"suggestion={_sa.get('suggestion_count', 0)}, "
                    f"unknown={_sa.get('unknown_count', 0)}"
                )

            # Capture screenshots from this round
            shots = (scroll_meta or {}).get("screenshots") or []
            for shot in shots:
                artifact_manager.add_debug_screenshot(str(shot))

            # Check if we should stop or retry
            if not is_retryable:
                logger.info(
                    f"[IGFollowingAnalyzer] Round {scroll_round}: "
                    f"stop_reason '{scroll_stop_reason}' is not retryable, ending scroll phase"
                )
                break

            # Check persisted count after this round
            if expected_following_count and not max_accounts:
                try:
                    saved = get_saved_count(workspace_id, target_username)
                    if saved >= int(expected_following_count):
                        logger.info(
                            f"[IGFollowingAnalyzer] Round {scroll_round}: saved_count ({saved}) "
                            f">= expected ({expected_following_count}), stopping"
                        )
                        scroll_stop_reason = "saved_dedup_count_reached"
                        list_capture_status = "full"
                        break
                except Exception:
                    pass

            # If no new accounts were found in this round, stop to avoid infinite loops
            if new_in_round == 0:
                logger.info(
                    f"[IGFollowingAnalyzer] Round {scroll_round}: "
                    f"no new accounts found in this round, stopping"
                )
                break

            if scroll_round < max_scroll_rounds:
                logger.info(
                    f"[IGFollowingAnalyzer] Round {scroll_round}: "
                    f"will retry with fresh dialog (round {scroll_round + 1}/{max_scroll_rounds})"
                )

        # Use cumulative accounts across all rounds
        accounts = all_round_accounts

        # DB fallback: when saved_dedup_count_reached fired before any scrolling,
        # all_round_accounts is empty. Load from DB so the visit phase has data.
        if (
            not accounts
            and scroll_stop_reason == "saved_dedup_count_reached"
            and visit_account_pages
        ):
            logger.info(
                "[IGFollowingAnalyzer] Scroll skipped (all accounts already saved). "
                "Loading from DB for visit phase."
            )
            accounts = load_accounts_from_db(
                workspace_id, target_username, include_unverified=True
            )

        logger.info(
            f"[IGFollowingAnalyzer] Scroll phase completed after {total_scroll_rounds} round(s): "
            f"{len(accounts)} cumulative accounts"
        )

    # A-Z search augmentation: when scroll captured <50% of expected
    # accounts and the expected count is large (>3000), use dialog
    # search to fetch additional accounts letter-by-letter.
    _search_threshold = float(os.environ.get("IG_SEARCH_TRIGGER_RATIO", "0.5"))
    _search_min_expected = int(os.environ.get("IG_SEARCH_MIN_EXPECTED", "3000"))
    if (
        not resumed
        and expected_following_count
        and expected_following_count > _search_min_expected
        and len(accounts) < expected_following_count * _search_threshold
        and list_capture_status
        in ("exhausted_incomplete", "interrupted_incomplete", "unknown")
        and mode in ("full", "list")
    ):
        logger.info(
            "[IGFollowingAnalyzer] Entering search mode: "
            "scroll_saved=%d, expected=%d, ratio=%.2f",
            len(accounts),
            expected_following_count,
            len(accounts) / max(expected_following_count, 1),
        )
        try:
            # Navigate to profile and re-open dialog
            await page.goto(profile_url, wait_until="domcontentloaded", timeout=120000)
            try:
                await page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            await asyncio.sleep(random_delay(3, 6))

            following_button = await _find_following_button(page, target_username)
            await following_button.scroll_into_view_if_needed()
            await asyncio.sleep(random_delay(0.2, 0.6))
            await following_button.click(timeout=30000, force=True)
            await asyncio.sleep(random_delay(2, 4))
            dialog = await _find_following_dialog(page, target_username)

            await artifact_manager.upsert_progress(
                accounts=accounts,
                progress={
                    "stage": "search_extract",
                    "total_accounts": len(accounts),
                },
            )

            search_accounts, search_meta = await extract_following_by_search(
                page=page,
                dialog=dialog,
                existing_accounts=accounts,
                expected_following_count=expected_following_count,
                scroll_evidence=list_capture_evidence,
                completed_letters=None,
            )

            # Merge results
            accounts = search_accounts
            list_capture_status = (search_meta or {}).get(
                "list_capture_status", list_capture_status
            )
            list_capture_evidence = (search_meta or {}).get(
                "list_capture_evidence", list_capture_evidence
            )
            scroll_stop_reason = (search_meta or {}).get(
                "stop_reason", scroll_stop_reason
            )

            # Persist search results
            try:
                persist_accounts_flat(
                    workspace_id=workspace_id,
                    seed=target_username,
                    source_account_handle=artifact_manager.source_account_handle,
                    source_profile_ref=artifact_manager.user_data_dir,
                    accounts=accounts,
                    analyzed_at=_utc_now().isoformat(),
                    execution_id=trace_id,
                    trace_id=trace_id,
                    artifact_id=artifact_manager.progress_artifact_id,
                    schema_version=None,
                    seed_version=None,
                    capture_method="search_augmented",
                    run_mode=mode,
                )
            except Exception as e:
                logger.warning(
                    "[IGFollowingAnalyzer] Search results persist failed: %s", e
                )

            logger.info(
                "[IGFollowingAnalyzer] Search phase completed: "
                "%d total accounts (search_new=%d)",
                len(accounts),
                (search_meta or {})
                .get("list_capture_evidence", {})
                .get("search_new_accounts", 0),
            )
        except Exception as e:
            logger.warning(
                "[IGFollowingAnalyzer] Search augmentation failed (non-fatal): %s", e
            )

    artifact_manager.set_scroll_stop_reason(scroll_stop_reason)
    artifact_manager.set_list_capture_status(list_capture_status)
    artifact_manager.set_list_capture_evidence(list_capture_evidence)

    logger.info(
        f"[IGFollowingAnalyzer] ✓ Extracted {len(accounts)} accounts from following list"
    )

    # Check if we should proceed to visiting pages
    visit_account_pages = await _should_visit_pages(
        visit_account_pages=visit_account_pages,
        accounts=accounts,
        expected_following_count=expected_following_count,
        list_capture_status=list_capture_status,
        max_accounts=max_accounts,
        resume_manager=resume_manager,
        artifact_manager=artifact_manager,
        mode=mode,
        allow_partial_resume=allow_partial_resume,
    )

    # Filter out placeholder accounts (used for UI availability) before visiting/reporting
    accounts = [
        a
        for a in accounts
        if not (a.get("username") or "").startswith("__seed_placeholder__")
    ]

    # Prepend seed account so its own profile gets visited too.
    # Skip if already visited in pre-scroll seed self-visit phase
    # (the DB-aware pre-merge in visit_all_accounts provides a second
    # layer of dedup, but we skip the prepend entirely if possible).
    seed_already_in_list = any(
        (a.get("username") or a.get("handle", "")).lower() == target_username.lower()
        for a in accounts
    )
    if not seed_already_in_list:
        accounts.insert(
            0,
            {
                "username": target_username,
                "fetched_at": _utc_now().isoformat(),
                "_is_seed_self": True,
            },
        )
        logger.info(
            "[IGFollowingAnalyzer] Prepended seed '%s' to visit list",
            target_username,
        )

    # Visit account pages
    if visit_account_pages:
        await artifact_manager.upsert_progress(
            accounts=accounts,
            progress={
                "stage": "visiting_pages",
                "total_accounts": len(accounts),
                "page_index": 0,
                "page_total": len(accounts),
            },
        )

        visitor = PageVisitor()
        success_count, error_count, accounts, visit_meta = (
            await visitor.visit_all_accounts(
                page=page,
                accounts=accounts,
                artifact_manager=artifact_manager,
                is_resume=bool(resumed),
                abort_check=watchdog.is_abort_requested if watchdog else None,
                user_data_dir=artifact_manager.user_data_dir,
            )
        )
        visit_stop_reason = (visit_meta or {}).get("stop_reason", "completed")
    else:
        success_count = 0
        error_count = 0
        visit_meta = {}
        visit_stop_reason = None
        logger.info("[IGFollowingAnalyzer] Skipping account page visits")

    # Generate summary and build result
    summary = generate_summary(accounts)
    logger.info(
        f"[IGFollowingAnalyzer] Summary: Total={summary['total_accounts']}, "
        f"Verified={summary['verified_accounts']} ({summary['verified_percentage']:.1f}%), "
        f"WithBio={summary['accounts_with_bio']} ({summary['bio_percentage']:.1f}%)"
    )

    metadata = {
        "schema_version": schema_version,
        "seed_version": seed_version,
        "target_username": target_username,
        "workspace_id": workspace_id,
        "analyzed_at": datetime.now().isoformat(),
        "total_accounts": len(accounts),
        "visit_account_pages": visit_account_pages,
        "trace_id": trace_id,
        "source_account_handle": artifact_manager.source_account_handle,
        "source_profile_ref": artifact_manager.user_data_dir,
        "target_seed": target_username,
        "capture_method": "following_list",
        "expected_following_count": expected_following_count,
        "scroll_stop_reason": scroll_stop_reason,
        "visit_success_count": success_count if visit_account_pages else None,
        "visit_error_count": error_count if visit_account_pages else None,
        "visit_stop_reason": visit_stop_reason if visit_account_pages else None,
        "auto_batch_pin_candidate_count": (
            (visit_meta or {}).get("auto_batch_pin_candidate_count")
            if visit_account_pages
            else None
        ),
        "auto_batch_pin_task_count": (
            (visit_meta or {}).get("auto_batch_pin_task_count")
            if visit_account_pages
            else None
        ),
    }

    result = {
        "summary": summary,
        "accounts": accounts,
        "metadata": metadata,
    }

    # Final progress update
    is_partial = _is_partial_result(accounts, expected_following_count, max_accounts)

    # Determine final stage -- non-completed visit reasons are errors
    _visit_error_reasons = {"circuit_breaker", "visit_stalled", "aborted_externally"}
    if visit_account_pages and visit_stop_reason in _visit_error_reasons:
        visit_err_meta = visit_meta or {}
        await artifact_manager.upsert_progress(
            accounts=accounts,
            progress={
                "stage": "error",
                "error_type": visit_err_meta.get(
                    "last_error_type", "visit_circuit_breaker"
                ),
                "error_message": (
                    f"Visit phase stopped: {visit_err_meta.get('consecutive_errors_at_stop', 0)} consecutive errors. "
                    f"Last: {(visit_err_meta.get('last_error_message') or 'unknown')[:200]}"
                ),
                "total_accounts": len(accounts),
                "expected_following_count": expected_following_count,
                "scroll_stop_reason": scroll_stop_reason,
                "visit_success_count": success_count,
                "visit_error_count": error_count,
            },
        )
    else:
        await artifact_manager.upsert_progress(
            accounts=accounts,
            progress={
                "stage": "completed_partial" if is_partial else "completed",
                "total_accounts": len(accounts),
                "expected_following_count": expected_following_count,
                "scroll_stop_reason": scroll_stop_reason,
            },
        )

    logger.info("=" * 80)
    logger.info("[IGFollowingAnalyzer] ✓ Analysis completed successfully")
    logger.info(f"  Total Accounts: {len(accounts)}")
    logger.info(
        f"  Verified: {summary['verified_accounts']} ({summary['verified_percentage']:.1f}%)"
    )
    logger.info(
        f"  With Bio: {summary['accounts_with_bio']} ({summary['bio_percentage']:.1f}%)"
    )
    logger.info("=" * 80)

    # Persist to database
    try:
        persist_accounts_flat(
            workspace_id=workspace_id,
            seed=target_username,
            source_account_handle=artifact_manager.source_account_handle,
            source_profile_ref=artifact_manager.user_data_dir,
            accounts=accounts,
            analyzed_at=metadata.get("analyzed_at") or "",
            execution_id=trace_id,
            trace_id=trace_id,
            artifact_id=artifact_manager.progress_artifact_id,
            schema_version=schema_version,
            seed_version=seed_version,
            capture_method="following_list",
            run_mode=run_mode,
            source_context="following_list",
        )
    except Exception:
        pass

    try:
        persist_follow_edges(
            workspace_id=workspace_id,
            seed=target_username,
            accounts=accounts,
            execution_id=trace_id,
        )
    except Exception:
        pass

    # ── Auto-tag profiles after crawl ──────────────────────────────
    # Run ig_profile_tagger to populate ig_account_profiles from the
    # enriched data in ig_accounts_flat.  This ensures the insight tabs
    # (Tags, Content, Persona) have data immediately after crawling.
    try:
        from ..ig_profile_tagger import ig_profile_tagger

        logger.info(
            f"[IGFollowingAnalyzer] Auto-running profile tagger for seed={target_username}"
        )
        tagger_result = await ig_profile_tagger(
            workspace_id=workspace_id,
            seed=target_username,
            force_recompute=False,
            batch_size=200,
        )
        logger.info(
            f"[IGFollowingAnalyzer] Profile tagger completed: "
            f"processed={tagger_result.get('processed', 0)}, "
            f"created={tagger_result.get('created', 0)}, "
            f"skipped={tagger_result.get('skipped', 0)}"
        )
    except Exception as e:
        logger.warning(f"[IGFollowingAnalyzer] Profile tagger failed (non-fatal): {e}")

    auto_batch_pin_task_count = int((visit_meta or {}).get("auto_batch_pin_task_count", 0))
    # Follow-up analysis now stays on the regular, user-visible reference flow.
    # Successful page visits may enqueue visible ig_batch_pin_references tasks
    # that consume the already captured posts without reopening a browser.
    result["captured_posts_ready"] = True
    result["auto_batch_pin_task_count"] = auto_batch_pin_task_count
    result["recommended_follow_up"] = (
        "auto_batch_pin_enqueued"
        if auto_batch_pin_task_count > 0
        else "batch_pin_from_captured_posts"
    )

    return result


# ============================================================================
# Re-exports from extracted modules
# ============================================================================

from .browser_helpers import (
    debug_log as _debug_log,
    save_debug_screenshot as _save_debug_screenshot,
    parse_following_count as _parse_following_count,
    find_following_button as _find_following_button,
    find_following_dialog as _find_following_dialog,
)

from .runner_visit import (
    should_visit_pages as _should_visit_pages,
    is_partial_result as _is_partial_result,
)


# Legacy aliases for backward compatibility
_assert_logged_in = assert_logged_in
_try_get_logged_in_username = try_get_logged_in_username
