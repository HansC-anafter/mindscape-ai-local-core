"""
Debug utilities for scroll extraction.

Handles marking elements with visual outlines and capturing diagnostic
screenshots during scrolling.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict

from .scroll_context import ScrollContext
from .scroll_engine import with_timeout

logger = logging.getLogger(__name__)


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


async def mark_debug_elements(ctx: ScrollContext) -> None:
    """Outline the dialog and the chosen scroll_container for screenshots."""
    try:
        await ctx.dialog.evaluate(
            """
            (root) => {
              try { root.style.outline = '3px solid #22c55e'; root.style.outlineOffset = '-2px'; } catch (e) {}
            }
            """
        )
    except Exception:
        pass
    try:
        if ctx.scroll_container is not None:
            await ctx.scroll_container.evaluate(
                """
                (el) => {
                  try {
                    el.setAttribute('data-ig-debug-scroll-container','1');
                    el.style.outline = '3px solid #ef4444'; // red
                    el.style.outlineOffset = '-2px';
                  } catch (e) {}
                }
                """
            )
    except Exception:
        pass


async def capture_debug_screens(
    ctx: ScrollContext,
    reason: str,
    iteration: int,
    before_count: int,
    after_count: int,
    reached_bottom: bool,
    pre_metrics: Dict[str, Any],
    post_metrics: Dict[str, Any],
    js_metrics: Dict[str, Any],
) -> None:
    """Capture dialog, container, and page screenshots with metadata."""
    if not ctx.trace_id:
        return

    ts = _utc_now().strftime("%Y%m%dT%H%M%SZ")
    base = f"/app/data/ig_debug_scroll_{ctx.trace_id}_{ts}_iter{iteration}_n{len(ctx.unique_accounts)}"
    path_page = f"{base}_page.png"
    path_dialog = f"{base}_dialog.png"
    path_container = f"{base}_container.png"

    try:
        await mark_debug_elements(ctx)
    except Exception:
        pass

    # Always try to capture dialog (most informative)
    try:
        try:
            await ctx.dialog.scroll_into_view_if_needed(timeout=2000)
        except Exception:
            pass
        await ctx.dialog.screenshot(path=path_dialog)
        ctx.screenshots.append(path_dialog)
    except Exception:
        pass

    # Capture the chosen scroll container if possible
    try:
        if ctx.scroll_container is not None:
            try:
                await ctx.scroll_container.scroll_into_view_if_needed(timeout=2000)
            except Exception:
                pass
            await ctx.scroll_container.screenshot(path=path_container)
            ctx.screenshots.append(path_container)
    except Exception:
        pass

    # Capture viewport as a fallback/context
    try:
        await ctx.page.screenshot(path=path_page)
        ctx.screenshots.append(path_page)
    except Exception:
        pass

    try:
        ctx.screenshot_notes.append(
            {
                "reason": reason,
                "iteration": iteration,
                "count_before": before_count,
                "count_after": after_count,
                "total_accounts": len(ctx.unique_accounts),
                "no_new_accounts_streak": ctx.no_new_accounts_streak,
                "reached_bottom": reached_bottom,
                "scroll_mode": ctx.scroll_mode,
                "pre_metrics": pre_metrics,
                "post_metrics": post_metrics,
                "js_scroll_metrics": js_metrics,
                "url": ctx.page.url,
                "paths": [path_dialog, path_container, path_page],
            }
        )
    except Exception:
        pass
