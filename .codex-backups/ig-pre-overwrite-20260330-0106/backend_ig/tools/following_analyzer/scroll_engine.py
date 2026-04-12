"""
Scroll engine — low-level scroll helpers.

All functions that physically scroll the page or probe scroll metrics
live here.  Each takes explicit Page/Locator/dialog args instead of
relying on closure scope.
"""

import asyncio
import logging
import random
from typing import Any, Dict, Optional

from playwright.async_api import Locator, Page

from .utils import random_delay

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


async def with_timeout(coro, timeout_seconds: float, default):
    """Run *coro* with a timeout; return *default* on any failure."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout_seconds)
    except Exception:
        return default


# ---------------------------------------------------------------------------
# Scroll helpers
# ---------------------------------------------------------------------------


async def human_like_scroll(
    page: Page, scroll_container: Locator, distance: int = None
) -> None:
    """Simulate human-like scrolling behavior using mouse wheel."""
    if distance is None:
        distance = random.randint(200, 400)

    scroll_steps = random.randint(2, 4)
    step_distance = distance // scroll_steps

    try:
        box = await scroll_container.bounding_box()
        if box:
            await page.mouse.move(
                box["x"] + box["width"] / 2,
                box["y"] + box["height"] / 2,
            )
    except Exception:
        pass

    for _ in range(scroll_steps):
        try:
            await scroll_container.evaluate(
                "(el, delta) => { el.scrollTop += delta; }",
                step_distance,
            )
        except Exception:
            pass
        # Always send wheel events too (IG lists are often virtualized and rely on wheel/scroll events)
        try:
            await page.mouse.wheel(0, step_distance)
        except Exception:
            pass
        await asyncio.sleep(random_delay(0.2, 0.5))


async def find_effective_scroll_container(root: Locator) -> Locator:
    """Probe children of *root* to find the actual scrollable container."""
    candidates = root.locator("div, ul, section")
    count = await with_timeout(candidates.count(), timeout_seconds=3.0, default=0)
    best: Optional[Locator] = None
    best_score = 0

    for i in range(min(int(count or 0), 250)):
        cand = candidates.nth(i)
        metrics = await with_timeout(
            cand.evaluate(
                """
                (el) => {
                  const style = window.getComputedStyle(el);
                  const overflowY = style.overflowY;
                  const scrollHeight = el.scrollHeight || 0;
                  const clientHeight = el.clientHeight || 0;
                  const scrollTop = el.scrollTop || 0;
                  const linkCount = el.querySelectorAll ? el.querySelectorAll('a[href^="/"]').length : 0;
                  return { overflowY, scrollHeight, clientHeight, scrollTop, linkCount };
                }
                """
            ),
            timeout_seconds=2.0,
            default=None,
        )
        if not metrics:
            continue

        scroll_height = float(metrics.get("scrollHeight") or 0)
        client_height = float(metrics.get("clientHeight") or 0)
        link_count = float(metrics.get("linkCount") or 0)

        scroll_range = max(0.0, scroll_height - client_height)
        # Prefer containers that actually contain lots of username links.
        score = int(link_count * 1000) + int(scroll_range)
        if score > best_score:
            best_score = score
            best = cand

    return best or root


async def get_scroll_top(container: Locator) -> Optional[float]:
    """Read scrollTop from *container*."""
    return await with_timeout(
        container.evaluate("el => el.scrollTop"), timeout_seconds=3.0, default=None
    )


async def get_window_scroll_top(page: Page) -> Optional[float]:
    """Read the window/document scroll position."""
    return await with_timeout(
        page.evaluate(
            "() => {\n"
            "  const el = document.scrollingElement || document.documentElement || document.body;\n"
            "  const v = (el && (el.scrollTop || 0)) || (window && (window.scrollY || 0)) || 0;\n"
            "  return v;\n"
            "}"
        ),
        timeout_seconds=2.0,
        default=None,
    )


async def window_scroll_by(page: Page, delta: int) -> None:
    """Scroll the window/document by *delta* pixels."""
    await with_timeout(
        page.evaluate(
            "(dy) => {\n"
            "  const el = document.scrollingElement || document.documentElement || document.body;\n"
            "  try { if (el) el.scrollTop = (el.scrollTop || 0) + dy; } catch (e) {}\n"
            "  try { window.scrollBy(0, dy); } catch (e) {}\n"
            "}",
            delta,
        ),
        timeout_seconds=2.0,
        default=None,
    )


async def get_scroll_metrics(container: Locator) -> Dict[str, Any]:
    """Read scrollTop / scrollHeight / clientHeight from *container*."""
    return await with_timeout(
        container.evaluate(
            """
            (el) => ({
                scrollTop: el.scrollTop || 0,
                scrollHeight: el.scrollHeight || 0,
                clientHeight: el.clientHeight || 0
            })
            """
        ),
        timeout_seconds=3.0,
        default={"scrollTop": 0, "scrollHeight": 0, "clientHeight": 0},
    )


async def ensure_container_focused(page: Page, container: Locator) -> None:
    """Move the mouse to the center of *container* and click to focus."""
    try:
        box = await container.bounding_box()
        if box:
            await page.mouse.move(
                box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
            )
            await page.mouse.click(
                box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
            )
    except Exception:
        pass


async def wheel_over(page: Page, container: Locator, delta: int) -> None:
    """Send a wheel event over *container*."""
    try:
        box = await with_timeout(
            container.bounding_box(), timeout_seconds=2.0, default=None
        )
        if box:
            await page.mouse.move(
                box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
            )
            await page.mouse.wheel(0, delta)
            return
    except Exception:
        pass
    try:
        await page.mouse.wheel(0, delta)
    except Exception:
        pass


async def js_scroll_best_container(dialog: Any, delta: int) -> Dict[str, Any]:
    """
    Find the best scrollable element inside the dialog and scroll it.

    IG following dialog often uses a virtualized list.  Directly setting
    scrollTop on a wrong element won't load more rows.  This helper finds
    the best candidate element INSIDE the dialog and scrolls it, also
    dispatching a scroll event to trigger loading.
    Returns debug metrics about the chosen element.
    """
    return await with_timeout(
        dialog.evaluate(
            """
            (root, dy) => {
              // Prefer a previously-selected element if it still exists.
              let prevBest = null;
              try { prevBest = root.querySelector('[data-ig-scroll-best="1"]'); } catch (e) { prevBest = null; }

              const nodes = Array.from(root.querySelectorAll('div, ul, section'));
              const candidates = [];
              for (const el of nodes) {
                try {
                  const style = window.getComputedStyle(el);
                  const overflowY = style.overflowY;
                  const scrollHeight = el.scrollHeight || 0;
                  const clientHeight = el.clientHeight || 0;
                  const scrollTop = el.scrollTop || 0;
                  const linkCount = el.querySelectorAll('a[href^="/"]').length;
                  const isScrollable = scrollHeight > clientHeight + 10 && (overflowY === 'auto' || overflowY === 'scroll' || overflowY === 'overlay');
                  // Prefer elements that contain lots of username links (actual list subtree).
                  const score = (linkCount * 1000) + (isScrollable ? 100000 : 0) + Math.max(0, scrollHeight - clientHeight);
                  if (linkCount >= 10) {
                    candidates.push({ el, score, overflowY, scrollHeight, clientHeight, scrollTop, linkCount, isScrollable });
                  }
                } catch (e) {}
              }
              candidates.sort((a,b) => (b.score - a.score));
              const best = candidates[0] || null;
              if (!best && !prevBest) return { ok:false };

              // If we have a prevBest, decide whether to keep it.
              let chosen = best;
              if (prevBest) {
                try {
                  const style = window.getComputedStyle(prevBest);
                  const overflowY = style.overflowY;
                  const scrollHeight = prevBest.scrollHeight || 0;
                  const clientHeight = prevBest.clientHeight || 0;
                  const scrollTop = prevBest.scrollTop || 0;
                  const linkCount = prevBest.querySelectorAll('a[href^="/"]').length;
                  const isScrollable = scrollHeight > clientHeight + 10 && (overflowY === 'auto' || overflowY === 'scroll' || overflowY === 'overlay');
                  const score = (linkCount * 1000) + (isScrollable ? 100000 : 0) + Math.max(0, scrollHeight - clientHeight);
                  // Keep previous if it is still reasonable (>=70% of best score)
                  if (!chosen || score >= (chosen.score * 0.7)) {
                    chosen = { el: prevBest, score, overflowY, scrollHeight, clientHeight, scrollTop, linkCount, isScrollable };
                  }
                } catch (e) {}
              }

              if (!chosen) return { ok:false };
              try {
                chosen.el.scrollTop = (chosen.el.scrollTop || 0) + dy;
                // Dispatch both wheel and scroll to trigger virtualized loading.
                try { chosen.el.dispatchEvent(new WheelEvent('wheel', { deltaY: dy, bubbles: true })); } catch (e) {}
                try { chosen.el.dispatchEvent(new Event('scroll', { bubbles: true })); } catch (e) {}
              } catch (e) {}

              // Mark/outline chosen element so screenshots show what we're scrolling.
              try {
                // Clear outline from previous chosen markers.
                const prev = root.querySelectorAll('[data-ig-scroll-best="1"]');
                for (const el of Array.from(prev)) {
                  try { el.style.outline = ''; el.style.outlineOffset = ''; } catch (e) {}
                  try { el.removeAttribute('data-ig-scroll-best'); } catch (e) {}
                }
                chosen.el.setAttribute('data-ig-scroll-best', '1');
                chosen.el.style.outline = '3px solid #3b82f6'; // blue
                chosen.el.style.outlineOffset = '-2px';
              } catch (e) {}
              let tagName = '';
              let role = '';
              let ariaLabel = '';
              let className = '';
              try { tagName = (chosen.el.tagName || '').toString().toLowerCase(); } catch (e) {}
              try { role = (chosen.el.getAttribute('role') || '').toString(); } catch (e) {}
              try { ariaLabel = (chosen.el.getAttribute('aria-label') || '').toString(); } catch (e) {}
              try { className = (chosen.el.className || '').toString().slice(0, 120); } catch (e) {}
              return {
                ok: true,
                overflowY: chosen.overflowY,
                scrollHeight: chosen.scrollHeight,
                clientHeight: chosen.clientHeight,
                scrollTop: chosen.el.scrollTop || chosen.scrollTop || 0,
                linkCount: chosen.linkCount,
                isScrollable: chosen.isScrollable,
                tagName,
                role,
                ariaLabel,
                className,
              };
            }
            """,
            delta,
        ),
        timeout_seconds=3.0,
        default={"ok": False},
    )
