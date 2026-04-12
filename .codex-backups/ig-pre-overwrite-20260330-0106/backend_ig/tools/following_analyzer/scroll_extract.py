"""
Instagram following list scroll extraction — orchestrator.

This module provides the public entry point ``extract_following_list()``
which coordinates scrolling, DOM collection, state-machine updates, and
stop-condition evaluation.  All heavy lifting is delegated to:

- scroll_config  — environment-variable parsing
- scroll_context  — mutable runtime state
- scroll_engine   — low-level scroll helpers
- dom_collector   — DOM scraping + source attribution
- scroll_debug    — diagnostic screenshots
"""

import asyncio
import logging
import os
import random
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

from playwright.async_api import Page

from .dom_collector import (
    apply_terminal_promotion,
    collect_accounts_from_dom,
    detect_replacement_signal,
    detect_scroll_advanced,
    update_dialog_state,
)
from .scroll_config import ScrollConfig
from .scroll_context import ScrollContext
from .scroll_debug import capture_debug_screens
from .scroll_engine import (
    ensure_container_focused,
    find_effective_scroll_container,
    get_scroll_metrics,
    get_scroll_top,
    get_window_scroll_top,
    human_like_scroll,
    js_scroll_best_container,
    wheel_over,
    window_scroll_by,
    with_timeout,
)
from .utils import detect_risk_signal, random_delay

logger = logging.getLogger(__name__)


async def extract_following_list(
    page: Page,
    dialog: Any,
    max_accounts: Optional[int] = None,
    expected_following_count: Optional[int] = None,
    trace_id: Optional[str] = None,
    on_progress: Optional[Callable[..., Awaitable[None]]] = None,
    get_saved_count: Optional[Callable[[], int]] = None,
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Extract account list from following dialog by scrolling.

    Public API is unchanged — callers receive the same
    (accounts_list, metadata_dict) tuple.
    """

    # ── Build config & context ──────────────────────────────────────
    config = ScrollConfig.from_env(
        expected_following_count=expected_following_count,
        max_accounts=max_accounts,
    )
    ctx = ScrollContext(
        page=page,
        dialog=dialog,
        config=config,
        trace_id=trace_id,
        on_progress=on_progress,
        get_saved_count=get_saved_count,
        max_accounts=max_accounts,
        expected_following_count=expected_following_count,
    )

    # ── Find scrollable container ───────────────────────────────────
    ctx.scroll_container = await find_effective_scroll_container(dialog)

    # ── Wait for initial links ──────────────────────────────────────
    try:
        await dialog.locator('a[href^="/"]').first.wait_for(timeout=10000)
    except Exception:
        try:
            await page.screenshot(path="/app/data/ig_debug_following_dialog.png")
            logger.info(
                "[IGFollowingAnalyzer] Debug dialog screenshot saved to /app/data/ig_debug_following_dialog.png"
            )
        except Exception:
            pass

    # ── Initial DOM collection ──────────────────────────────────────
    ctx.visible_prev = await collect_accounts_from_dom(ctx)
    if on_progress:
        try:
            _all_count = (
                len(ctx.unique_accounts)
                + len(ctx.unknown_accounts)
                + len(ctx.suggestion_accounts)
            )
            logger.info(
                f"[IGFollowingAnalyzer] Progress: initial_collect "
                f"following_list={len(ctx.unique_accounts)} unknown={len(ctx.unknown_accounts)} "
                f"suggestion={len(ctx.suggestion_accounts)} dialog_state={ctx.dialog_state}"
            )
            await on_progress(
                accounts=list(ctx.unique_accounts.values())
                or list(ctx.unknown_accounts.values()),
                progress={
                    "stage": "initial_collect",
                    "iteration": 0,
                    "total_accounts": _all_count,
                    "dialog_state": ctx.dialog_state,
                },
            )
        except Exception:
            pass

    # ── Prepare scrolling ───────────────────────────────────────────
    await ensure_container_focused(page, ctx.scroll_container)
    try:
        if ctx.scroll_container == dialog:
            m = await get_scroll_metrics(ctx.scroll_container)
            if float(m.get("scrollHeight", 0)) <= float(m.get("clientHeight", 0)) + 10:
                ctx.scroll_mode = "window"
    except Exception:
        pass

    # ── Main scroll loop ────────────────────────────────────────────
    iteration = 0
    for iteration in range(1, config.max_iterations + 1):
        before_count = len(ctx.unique_accounts)
        # Track ALL pools for state machine transition (unconfirmed → healthy
        # routes everything to unknown, so unique-only counts stay at 0).
        before_all_count = (
            len(ctx.unique_accounts)
            + len(ctx.unknown_accounts)
            + len(ctx.suggestion_accounts)
        )
        after_count = before_count
        reached_bottom = False
        pre_metrics: Dict[str, Any] = {}
        post_metrics: Dict[str, Any] = {}
        js_metrics: Dict[str, Any] = {}

        # ── Risk detection ──
        if iteration == 1 or iteration % 5 == 0 or ctx.no_change_count >= 2:
            ctx.risk = await detect_risk_signal(page)
            if ctx.risk:
                try:
                    await capture_debug_screens(
                        ctx,
                        reason=f"risk_{(ctx.risk.get('error_type') or 'unknown')}",
                        iteration=iteration,
                        before_count=before_count,
                        after_count=after_count,
                        reached_bottom=reached_bottom,
                        pre_metrics=pre_metrics,
                        post_metrics=post_metrics,
                        js_metrics=js_metrics,
                    )
                except Exception:
                    pass
                if on_progress:
                    try:
                        await on_progress(
                            accounts=list(ctx.unique_accounts.values()),
                            progress={
                                "stage": "blocked",
                                "error_type": ctx.risk.get("error_type"),
                                "error_message": ctx.risk.get("error_message"),
                                "last_url": page.url,
                                "iteration": iteration,
                                "total_accounts": len(ctx.unique_accounts),
                            },
                        )
                    except Exception:
                        pass
                ctx.stop_reason = "blocked"
                break

        # ── max_accounts guard ──
        if max_accounts and len(ctx.unique_accounts) >= max_accounts:
            ctx.stop_reason = "max_accounts_reached"
            break

        # ── Scroll ──
        pre_scroll_top = await get_scroll_top(ctx.scroll_container)
        pre_window_top = await get_window_scroll_top(page)
        pre_metrics = await get_scroll_metrics(ctx.scroll_container)
        await with_timeout(
            human_like_scroll(page, ctx.scroll_container),
            timeout_seconds=10.0,
            default=None,
        )
        await wheel_over(page, ctx.scroll_container, random.randint(260, 420))
        js_metrics = await js_scroll_best_container(dialog, random.randint(260, 420))

        # Track JS scroll position
        pre_js_scroll_top = ctx.last_js_scroll_top
        try:
            ctx.last_js_metrics = dict(js_metrics or {})
            jt = js_metrics.get("scrollTop")
            if isinstance(jt, (int, float)):
                ctx.last_js_scroll_top = float(jt)
            lc = js_metrics.get("linkCount")
            if isinstance(lc, int):
                ctx.last_js_link_count = lc
        except Exception:
            pass

        # Window scroll fallback
        try:
            post_scroll_top_probe = await get_scroll_top(ctx.scroll_container)
            if ctx.scroll_mode == "window" or (
                pre_scroll_top is not None
                and post_scroll_top_probe is not None
                and pre_scroll_top == post_scroll_top_probe
            ):
                await window_scroll_by(page, random.randint(260, 420))
        except Exception:
            pass

        base_delay = random_delay(1.5, 3.0)
        backoff_seconds = min(10.0, float(ctx.no_change_count) * 1.75)
        await asyncio.sleep(min(12.0, base_delay + backoff_seconds))
        post_scroll_top = await get_scroll_top(ctx.scroll_container)
        post_window_top = await get_window_scroll_top(page)
        post_metrics = await get_scroll_metrics(ctx.scroll_container)

        # ── Collect accounts ──
        visible_now = await collect_accounts_from_dom(ctx)
        after_count = len(ctx.unique_accounts)
        after_all_count = (
            len(ctx.unique_accounts)
            + len(ctx.unknown_accounts)
            + len(ctx.suggestion_accounts)
        )
        # Use all-pool growth for streak detection so it works during
        # unconfirmed state (where unique_accounts stays empty).
        if after_all_count <= before_all_count:
            ctx.no_new_accounts_streak += 1
        else:
            ctx.no_new_accounts_streak = 0

        # ── Source attribution ──
        scroll_advanced = detect_scroll_advanced(
            pre_scroll_top,
            post_scroll_top,
            pre_window_top,
            post_window_top,
            js_metrics,
            pre_js_scroll_top,
        )
        replacement_signal = detect_replacement_signal(
            visible_now,
            ctx.visible_prev,
            scroll_advanced,
            ctx.no_new_accounts_streak,
        )
        update_dialog_state(
            ctx,
            iteration=iteration,
            before_count=before_count,
            after_count=after_count,
            replacement_signal=replacement_signal,
            visible_now=visible_now,
            before_all_count=before_all_count,
            after_all_count=after_all_count,
        )
        ctx.visible_prev = visible_now

        # ── Strict full-list mode check ──
        if (
            config.require_full_expected
            and expected_following_count
            and not max_accounts
        ):
            try:
                if len(ctx.unique_accounts) >= int(expected_following_count):
                    ctx.stop_reason = "expected_following_count_reached"
                    break
            except Exception:
                pass

            if get_saved_count and iteration > 0 and iteration % 5 == 0:
                try:
                    saved = get_saved_count()
                    if saved >= int(expected_following_count):
                        logger.info(
                            f"[IGFollowingAnalyzer] Saved dedup count {saved} >= expected {expected_following_count}, stopping scroll"
                        )
                        ctx.stop_reason = "saved_dedup_count_reached"
                        break
                except Exception:
                    pass

        # ── Bottom detection ──
        try:
            if isinstance(js_metrics, dict) and js_metrics.get("ok") is True:
                reached_bottom = (
                    float(js_metrics.get("scrollTop", 0))
                    + float(js_metrics.get("clientHeight", 0))
                ) >= (float(js_metrics.get("scrollHeight", 0)) - 5)
            else:
                reached_bottom = (
                    float(post_metrics.get("scrollTop", 0))
                    + float(post_metrics.get("clientHeight", 0))
                ) >= (float(post_metrics.get("scrollHeight", 0)) - 5)
        except Exception:
            reached_bottom = False

        # ── Stall detection ──
        scroll_stalled = False
        try:
            js_stalled = False
            if isinstance(js_metrics, dict) and js_metrics.get("ok") is True:
                if ctx.last_js_scroll_top is not None:
                    js_stalled = (
                        abs(
                            float(js_metrics.get("scrollTop", 0))
                            - float(ctx.last_js_scroll_top)
                        )
                        < 1.0
                    )
            container_stalled = (
                pre_scroll_top is not None
                and post_scroll_top is not None
                and pre_scroll_top == post_scroll_top
            )
            window_stalled = (
                pre_window_top is not None
                and post_window_top is not None
                and pre_window_top == post_window_top
            )
            scroll_stalled = js_stalled or (container_stalled and window_stalled)
        except Exception:
            scroll_stalled = False

        if scroll_stalled:
            ctx.consecutive_scroll_stall_count += 1
        else:
            ctx.consecutive_scroll_stall_count = 0

        current_unique_count = len(ctx.unique_accounts)
        if current_unique_count == ctx.previous_unique_count and scroll_stalled:
            ctx.no_change_count += 1
        else:
            ctx.no_change_count = 0
            ctx.previous_unique_count = current_unique_count

        # ── Progress callback ──
        if on_progress:
            try:
                await on_progress(
                    accounts=list(ctx.unique_accounts.values()),
                    progress={
                        "stage": "scrolling",
                        "iteration": iteration,
                        "total_accounts": len(ctx.unique_accounts),
                        "reached_bottom": reached_bottom,
                        "no_change_count": ctx.no_change_count,
                        "no_new_accounts_streak": ctx.no_new_accounts_streak,
                        "count_before": before_count,
                        "count_after": after_count,
                        "pre_metrics": pre_metrics,
                        "post_metrics": post_metrics,
                        "pre_window_scroll_top": pre_window_top,
                        "post_window_scroll_top": post_window_top,
                        "scroll_mode": ctx.scroll_mode,
                        "js_scroll_metrics": js_metrics,
                        "screenshots": ctx.screenshots[-6:],
                    },
                )
            except Exception:
                pass

        # ── Debug screenshots ──
        try:
            if iteration % max(5, config.screenshot_every_n) == 0:
                await capture_debug_screens(
                    ctx,
                    reason="periodic",
                    iteration=iteration,
                    before_count=before_count,
                    after_count=after_count,
                    reached_bottom=reached_bottom,
                    pre_metrics=pre_metrics,
                    post_metrics=post_metrics,
                    js_metrics=js_metrics,
                )
            elif ctx.no_new_accounts_streak in config.streak_screenshot_points:
                await capture_debug_screens(
                    ctx,
                    reason=f"no_new_accounts_streak_{ctx.no_new_accounts_streak}",
                    iteration=iteration,
                    before_count=before_count,
                    after_count=after_count,
                    reached_bottom=reached_bottom,
                    pre_metrics=pre_metrics,
                    post_metrics=post_metrics,
                    js_metrics=js_metrics,
                )
        except Exception:
            pass

        # ── Recovery: early stuck ──
        try:
            if (
                expected_following_count
                and ctx.no_new_accounts_streak >= 4
                and len(ctx.unique_accounts)
                < min(80, int(expected_following_count * 0.1))
                and ctx.recovery_attempts < 3
            ):
                ctx.recovery_attempts += 1
                logger.info(
                    f"[IGFollowingAnalyzer] Recovery attempt {ctx.recovery_attempts}: re-selecting scroll container (accounts={len(ctx.unique_accounts)}, expected={expected_following_count})"
                )
                try:
                    ctx.scroll_container = await find_effective_scroll_container(dialog)
                    await ensure_container_focused(page, ctx.scroll_container)
                    _ = await js_scroll_best_container(dialog, random.randint(520, 780))
                    await asyncio.sleep(random_delay(1.0, 2.0))
                    ctx.no_new_accounts_streak = max(0, ctx.no_new_accounts_streak - 2)
                except Exception:
                    pass
        except Exception:
            pass

        # ── Recovery: mid-run ──
        try:
            if (
                expected_following_count
                and len(ctx.unique_accounts) < int(expected_following_count * 0.9)
                and ctx.no_new_accounts_streak in (6, 9, 12)
                and ctx.recovery_attempts < 8
            ):
                ctx.recovery_attempts += 1
                logger.info(
                    f"[IGFollowingAnalyzer] Mid-run recovery attempt {ctx.recovery_attempts}: "
                    f"accounts={len(ctx.unique_accounts)} expected={expected_following_count} streak={ctx.no_new_accounts_streak}"
                )
                try:
                    ctx.scroll_container = await find_effective_scroll_container(dialog)
                    await ensure_container_focused(page, ctx.scroll_container)
                    _ = await js_scroll_best_container(
                        dialog, random.randint(900, 1400)
                    )
                    _ = await js_scroll_best_container(
                        dialog, random.randint(900, 1400)
                    )
                    await asyncio.sleep(random_delay(0.8, 1.6))
                    ctx.no_new_accounts_streak = max(0, ctx.no_new_accounts_streak - 2)
                    ctx.js_reselect_count += 1
                except Exception:
                    pass
        except Exception:
            pass

        # ── Risk control / rate-limit early exit ──
        try:
            _visible_non_following = len(ctx.suggestion_accounts) + len(
                ctx.unknown_accounts
            )
            _link_count = (
                ctx.last_js_metrics.get("linkCount")
                if isinstance(ctx.last_js_metrics, dict)
                else None
            )
            _looks_like_empty_risk_wall = (
                _visible_non_following == 0
                and len(ctx.unique_accounts) <= 1
                and (
                    _link_count is None
                    or (isinstance(_link_count, int) and _link_count < 30)
                )
            )
            if (
                expected_following_count
                and iteration >= config.min_iters_before_streak_stop
                and ctx.no_new_accounts_streak >= 5
                and (
                    len(ctx.unique_accounts)
                    < max(50, int(expected_following_count * 0.05))
                )
            ):
                if _looks_like_empty_risk_wall:
                    try:
                        await capture_debug_screens(
                            ctx,
                            reason="risk_control_suspected",
                            iteration=iteration,
                            before_count=before_count,
                            after_count=after_count,
                            reached_bottom=reached_bottom,
                            pre_metrics=pre_metrics,
                            post_metrics=post_metrics,
                            js_metrics=js_metrics,
                        )
                    except Exception:
                        pass
                    logger.warning(
                        "[IGFollowingAnalyzer] Risk control detected: "
                        f"accounts={len(ctx.unique_accounts)} expected={expected_following_count} "
                        f"streak={ctx.no_new_accounts_streak} iter={iteration}. Stopping."
                    )
                    ctx.stop_reason = "risk_control_suspected"
                    break
                if reached_bottom:
                    logger.info(
                        "[IGFollowingAnalyzer] Risk-control heuristic downgraded to exhausted_incomplete: "
                        f"accounts={len(ctx.unique_accounts)} unknown={len(ctx.unknown_accounts)} "
                        f"suggestion={len(ctx.suggestion_accounts)} linkCount={_link_count}"
                    )
                    ctx.stop_reason = "exhausted_incomplete"
                    break
                logger.info(
                    "[IGFollowingAnalyzer] Risk-control heuristic ignored (not empty-risk shape): "
                    f"accounts={len(ctx.unique_accounts)} unknown={len(ctx.unknown_accounts)} "
                    f"suggestion={len(ctx.suggestion_accounts)} linkCount={_link_count}"
                )
        except Exception:
            pass

        # ── Streak-based stop ──
        if (
            (
                not (
                    config.require_full_expected
                    and expected_following_count
                    and not max_accounts
                )
            )
            and ctx.no_new_accounts_streak >= config.no_new_streak_limit
            and iteration >= config.min_iters_before_streak_stop
        ):
            if (
                expected_following_count
                and len(ctx.unique_accounts) < int(expected_following_count * 0.9)
                and not reached_bottom
            ):
                if ctx.recovery_attempts < 10:
                    ctx.recovery_attempts += 1
                    logger.info(
                        f"[IGFollowingAnalyzer] Extending scroll runway (streak={ctx.no_new_accounts_streak}, accounts={len(ctx.unique_accounts)}, expected={expected_following_count})"
                    )
                    ctx.no_new_accounts_streak = max(0, ctx.no_new_accounts_streak - 3)
                else:
                    ctx.stop_reason = "no_new_accounts_streak"
                    break
            else:
                ctx.stop_reason = "no_new_accounts_streak"
                break

        # ── Bottom reached but incomplete ──
        try:
            if (
                not (
                    config.require_full_expected
                    and expected_following_count
                    and not max_accounts
                )
                and expected_following_count
                and reached_bottom
                and iteration >= config.bottom_incomplete_min_iters
                and ctx.no_new_accounts_streak >= config.bottom_incomplete_min_streak
                and len(ctx.unique_accounts) < int(expected_following_count * 0.9)
            ):
                ctx.stop_reason = "bottom_reached_but_incomplete"
                break
        except Exception:
            pass

        # ── Exhausted in strict mode ──
        try:
            effective_exhausted_limit = (
                config.exhausted_streak_limit_bottom
                if reached_bottom
                else config.exhausted_streak_limit_no_bottom
            )
            if (
                config.require_full_expected
                and expected_following_count
                and not max_accounts
                and len(ctx.unique_accounts) < int(expected_following_count)
                and ctx.no_new_accounts_streak >= effective_exhausted_limit
                and iteration
                >= max(
                    config.min_iters_before_streak_stop,
                    config.bottom_incomplete_min_iters,
                )
            ):
                try:
                    await capture_debug_screens(
                        ctx,
                        reason=(
                            "exhausted_incomplete_bottom"
                            if reached_bottom
                            else "exhausted_incomplete_no_bottom"
                        ),
                        iteration=iteration,
                        before_count=before_count,
                        after_count=after_count,
                        reached_bottom=reached_bottom,
                        pre_metrics=pre_metrics,
                        post_metrics=post_metrics,
                        js_metrics=js_metrics,
                    )
                except Exception:
                    pass
                ctx.stop_reason = "exhausted_incomplete"
                break
        except Exception:
            pass

    # ── Build return value ──────────────────────────────────────────
    if not ctx.stop_reason:
        ctx.stop_reason = (
            "max_iterations_reached"
            if iteration >= config.max_iterations
            else "unknown"
        )

    # Terminal promotion: if we never got scroll growth evidence to
    # transition out of 'unconfirmed', promote unknown → unique so
    # final_accounts is not empty when data exists.
    apply_terminal_promotion(ctx, iteration)

    final_accounts = list(ctx.unique_accounts.values())
    final_suggestion = list(ctx.suggestion_accounts.values())
    final_unknown = list(ctx.unknown_accounts.values())

    list_capture_status = "unknown"
    try:
        if (
            expected_following_count
            and not max_accounts
            and len(final_accounts) >= int(expected_following_count)
        ):
            list_capture_status = "full"
        elif ctx.stop_reason == "blocked":
            list_capture_status = "blocked"
        elif ctx.stop_reason == "exhausted_incomplete":
            list_capture_status = "exhausted_incomplete"
        elif (
            expected_following_count
            and not max_accounts
            and reached_bottom
            and ctx.no_new_accounts_streak >= config.bottom_incomplete_min_streak
        ):
            list_capture_status = "exhausted_incomplete"
        elif expected_following_count and not max_accounts:
            list_capture_status = "interrupted_incomplete"
    except Exception:
        list_capture_status = "unknown"

    _retryable_reasons = {
        "exhausted_incomplete",
        "no_new_accounts_streak",
        "max_iterations_reached",
        "bottom_reached_but_incomplete",
    }
    is_retryable = ctx.stop_reason in _retryable_reasons

    return final_accounts, {
        "stop_reason": ctx.stop_reason,
        "list_capture_status": list_capture_status,
        "is_retryable": is_retryable,
        "suggestion_accounts": final_suggestion,
        "unknown_accounts": final_unknown,
        "source_attribution": {
            "dialog_state": ctx.dialog_state,
            "dialog_state_transitions": ctx.dialog_state_transitions,
            "following_list_count": len(final_accounts),
            "suggestion_count": len(final_suggestion),
            "unknown_count": len(final_unknown),
        },
        "list_capture_evidence": {
            "expected_following_count": expected_following_count,
            "final_accounts": len(final_accounts),
            "iterations": iteration,
            "reached_bottom": reached_bottom,
            "no_new_accounts_streak": ctx.no_new_accounts_streak,
            "scroll_mode": ctx.scroll_mode,
            "last_js_metrics": ctx.last_js_metrics,
            "js_reselect_count": ctx.js_reselect_count,
            "exhausted_streak_limit_bottom": config.exhausted_streak_limit_bottom,
            "exhausted_streak_limit_no_bottom": config.exhausted_streak_limit_no_bottom,
            "max_iterations_source": config.max_iterations_source,
            "risk": ctx.risk,
        },
        "iterations": iteration,
        "max_iterations": config.max_iterations,
        "screenshots": ctx.screenshots[-10:],
        "screenshot_notes": ctx.screenshot_notes[-10:],
        "recovery_attempts": ctx.recovery_attempts,
        "no_new_streak_limit": config.no_new_streak_limit,
        "min_iters_before_streak_stop": config.min_iters_before_streak_stop,
        "last_js_metrics": ctx.last_js_metrics,
        "js_reselect_count": ctx.js_reselect_count,
    }
