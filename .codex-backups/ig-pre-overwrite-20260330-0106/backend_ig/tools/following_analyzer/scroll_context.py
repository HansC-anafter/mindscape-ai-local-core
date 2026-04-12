"""
Scroll extraction runtime context.

Encapsulates all mutable state that was previously shared via closure
variables inside extract_following_list().  Every extracted helper
receives a ScrollContext instead of relying on nonlocal scope.
"""

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

from playwright.async_api import Locator, Page

from .scroll_config import ScrollConfig


@dataclass
class ScrollContext:
    """Mutable runtime state for a single scroll extraction run."""

    # Playwright handles
    page: Page
    dialog: Any

    # Configuration (immutable)
    config: ScrollConfig

    # Caller-provided callbacks
    trace_id: Optional[str] = None
    on_progress: Optional[Callable[..., Awaitable[None]]] = None
    get_saved_count: Optional[Callable[[], int]] = None
    max_accounts: Optional[int] = None
    expected_following_count: Optional[int] = None

    # ── Account pools ──
    unique_accounts: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    suggestion_accounts: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    unknown_accounts: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # ── Source attribution state machine (v7) ──
    dialog_state: str = "unconfirmed"  # "unconfirmed" | "healthy" | "degraded"
    degraded_consecutive: int = 0
    visible_prev: set = field(default_factory=set)
    following_list_snapshot: set = field(default_factory=set)
    dialog_state_transitions: List[Dict[str, Any]] = field(default_factory=list)

    # ── Scroll tracking ──
    scroll_container: Optional[Locator] = None
    scroll_mode: str = "container"
    no_change_count: int = 0
    no_new_accounts_streak: int = 0
    consecutive_scroll_stall_count: int = 0
    previous_unique_count: int = 0
    recovery_attempts: int = 0
    last_js_scroll_top: Optional[float] = None
    last_js_link_count: Optional[int] = None
    last_js_metrics: Dict[str, Any] = field(default_factory=dict)
    js_reselect_count: int = 0

    # ── Outputs ──
    stop_reason: Optional[str] = None
    risk: Optional[Dict[str, Any]] = None
    screenshots: List[str] = field(default_factory=list)
    screenshot_notes: List[Dict[str, Any]] = field(default_factory=list)
