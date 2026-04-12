"""
Scroll extraction configuration.

Parses all IG_SCROLL_* environment variables into a frozen dataclass.
Previously inlined as ~110 lines of try/except blocks at the top of
extract_following_list().
"""

import os
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class ScrollConfig:
    """Immutable configuration for a single scroll extraction run."""

    max_iterations: int
    max_iterations_source: str
    min_iters_before_streak_stop: int
    no_new_streak_limit: int
    streak_screenshot_points: List[int]
    bottom_incomplete_min_iters: int
    bottom_incomplete_min_streak: int
    exhausted_streak_limit_bottom: int
    exhausted_streak_limit_no_bottom: int
    require_full_expected: bool
    screenshot_every_n: int

    @classmethod
    def from_env(
        cls,
        expected_following_count: Optional[int] = None,
        max_accounts: Optional[int] = None,
    ) -> "ScrollConfig":
        """Build config from environment variables with safe defaults."""

        # ── max_iterations ──
        max_iterations_env = (os.environ.get("IG_SCROLL_MAX_ITERATIONS") or "").strip()
        max_iterations_source = "env" if max_iterations_env else "adaptive_default"

        adaptive_default = 120
        try:
            if expected_following_count and not max_accounts:
                expected_int = int(expected_following_count)
                if expected_int > 0:
                    adaptive_default = max(
                        adaptive_default, min(10_000, (expected_int // 10) + 50)
                    )
        except Exception:
            pass

        try:
            max_iterations_raw = int(max_iterations_env or adaptive_default)
            if max_iterations_raw == 0:
                max_iterations = 10_000
            elif max_iterations_raw < 0:
                max_iterations = adaptive_default
                max_iterations_source = "adaptive_default"
            else:
                max_iterations = max_iterations_raw
        except Exception:
            max_iterations = 120
            max_iterations_source = "adaptive_default"

        # ── streak-based stop guard ──
        try:
            min_iters_before_streak_stop = int(
                os.environ.get("IG_SCROLL_MIN_ITERATIONS_BEFORE_STOP") or 8
            )
        except Exception:
            min_iters_before_streak_stop = 8
        try:
            no_new_streak_limit = int(
                os.environ.get("IG_SCROLL_NO_NEW_STREAK_LIMIT") or 10
            )
        except Exception:
            no_new_streak_limit = 10
        if min_iters_before_streak_stop < 0:
            min_iters_before_streak_stop = 0
        if no_new_streak_limit < 1:
            no_new_streak_limit = 1

        # ── streak screenshot points ──
        streak_screenshot_points: List[int] = []
        try:
            raw = (
                os.environ.get("IG_SCROLL_STREAK_SCREENSHOT_POINTS") or "5,8,10"
            ).strip()
            for part in raw.split(","):
                part = part.strip()
                if not part:
                    continue
                n = int(part)
                if n > 0:
                    streak_screenshot_points.append(n)
        except Exception:
            streak_screenshot_points = [5, 8, 10]
        if not streak_screenshot_points:
            streak_screenshot_points = [5, 8, 10]
        streak_screenshot_points = sorted(set(streak_screenshot_points))

        # ── bottom-reached-but-incomplete thresholds ──
        try:
            bottom_incomplete_min_iters = int(
                os.environ.get("IG_SCROLL_BOTTOM_INCOMPLETE_MIN_ITERS") or 12
            )
        except Exception:
            bottom_incomplete_min_iters = 12
        try:
            bottom_incomplete_min_streak = int(
                os.environ.get("IG_SCROLL_BOTTOM_INCOMPLETE_MIN_STREAK") or 5
            )
        except Exception:
            bottom_incomplete_min_streak = 5
        if bottom_incomplete_min_iters < 0:
            bottom_incomplete_min_iters = 0
        if bottom_incomplete_min_streak < 1:
            bottom_incomplete_min_streak = 1

        # ── exhausted streak limits ──
        try:
            exhausted_streak_limit_bottom = int(
                os.environ.get("IG_SCROLL_EXHAUSTED_STREAK_LIMIT_BOTTOM") or 8
            )
        except Exception:
            exhausted_streak_limit_bottom = 8
        try:
            exhausted_streak_limit_no_bottom = int(
                os.environ.get("IG_SCROLL_EXHAUSTED_STREAK_LIMIT_NO_BOTTOM") or 18
            )
        except Exception:
            exhausted_streak_limit_no_bottom = 18
        if exhausted_streak_limit_bottom < 3:
            exhausted_streak_limit_bottom = 3
        if exhausted_streak_limit_no_bottom < 5:
            exhausted_streak_limit_no_bottom = 5

        # ── require full expected ──
        try:
            require_full_expected = (
                os.environ.get("IG_SCROLL_REQUIRE_FULL_EXPECTED") or "1"
            ).strip() != "0"
        except Exception:
            require_full_expected = True

        # ── periodic screenshot interval ──
        try:
            screenshot_every_n = int(
                os.environ.get("IG_SCROLL_SCREENSHOT_EVERY_N") or 40
            )
        except Exception:
            screenshot_every_n = 40

        return cls(
            max_iterations=max_iterations,
            max_iterations_source=max_iterations_source,
            min_iters_before_streak_stop=min_iters_before_streak_stop,
            no_new_streak_limit=no_new_streak_limit,
            streak_screenshot_points=streak_screenshot_points,
            bottom_incomplete_min_iters=bottom_incomplete_min_iters,
            bottom_incomplete_min_streak=bottom_incomplete_min_streak,
            exhausted_streak_limit_bottom=exhausted_streak_limit_bottom,
            exhausted_streak_limit_no_bottom=exhausted_streak_limit_no_bottom,
            require_full_expected=require_full_expected,
            screenshot_every_n=screenshot_every_n,
        )
