"""
Unified browser session management for all Instagram tools.

Provides a single BrowserSession context manager used by:
- ig_account_snapshot (visit page)
- ig_content_analyzer (scroll posts)
- following_analyzer (scroll following list)

Key design decisions:
- Always use storage_state.json for session persistence (never persistent_context)
- Persist and reuse the same User-Agent across sessions to avoid IG device checks
- Save storage_state on every exit to keep cookies fresh
- Apply anti-detection measures on every launch
"""

import asyncio
import json
import logging
import os
import random
import shutil
from typing import Any, Dict, List, Optional, Tuple

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from .utils import get_chromium_executable_path

logger = logging.getLogger(__name__)


# Default user agent (Chrome 120 on macOS, most common)
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# User agent pool — only used on first-time profile creation
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

# Default viewport
DEFAULT_VIEWPORT = {"width": 1920, "height": 1080}

# Anti-detection script to hide webdriver property
ANTI_DETECTION_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined
});
"""

# Profile config filename (stored alongside storage_state.json)
PROFILE_CONFIG_FILE = "browser_profile.json"

# Cache directories that can grow unbounded and cause Chromium crashes.
# These are safe to delete — session data lives in storage_state.json.
EXPENDABLE_CACHE_DIRS = [
    "Default/Cache",
    "Default/Code Cache",
    "Default/GPUCache",
    "Default/Service Worker/CacheStorage",
    "GrShaderCache",
    "ShaderCache",
]


def is_docker_environment() -> bool:
    """Check if running inside Docker container."""
    return os.path.exists("/.dockerenv") or os.environ.get("DOCKER_CONTAINER") == "true"


def should_use_headless() -> bool:
    """Determine if browser should run in headless mode."""
    return is_docker_environment() or os.environ.get("DISPLAY") is None


def reap_zombie_children() -> None:
    """Reap zombie child processes without touching active browser sessions."""
    try:
        while True:
            pid, _ = os.waitpid(-1, os.WNOHANG)
            if pid == 0:
                break
            logger.debug("[BrowserSession] Reaped zombie child pid=%s", pid)
    except ChildProcessError:
        pass


def cleanup_browser_cache(user_data_dir: Optional[str]) -> None:
    """Remove expendable Chromium cache dirs that can cause crashes."""
    if not user_data_dir or not os.path.isdir(user_data_dir):
        return

    cleaned = 0
    for subdir in EXPENDABLE_CACHE_DIRS:
        path = os.path.join(user_data_dir, subdir)
        if os.path.isdir(path):
            try:
                shutil.rmtree(path)
                cleaned += 1
            except Exception:
                pass
    if cleaned:
        logger.info(f"[BrowserSession] Cleaned {cleaned} cache dirs in {user_data_dir}")


def prepare_browser_runtime(
    user_data_dir: Optional[str],
    *,
    reap_zombies: bool = True,
) -> None:
    """Run non-destructive pre-launch cleanup for a browser session.

    This intentionally avoids global process killing. Different IG tasks may
    run in parallel when they use different profile locks, so startup hygiene
    must not terminate unrelated Chromium/Playwright processes.
    """
    if reap_zombies:
        reap_zombie_children()
    cleanup_browser_cache(user_data_dir)


def _load_profile_config(user_data_dir: str) -> Dict[str, Any]:
    """
    Load persisted browser profile config (user_agent, viewport).

    The config is saved on first session creation and reused for all
    subsequent sessions to avoid IG flagging a new device.
    """
    config_path = os.path.join(user_data_dir, PROFILE_CONFIG_FILE)
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                config = json.load(f)
            logger.debug(f"[BrowserSession] Loaded profile config: {config_path}")
            return config
        except Exception as e:
            logger.warning(f"[BrowserSession] Failed to load profile config: {e}")
    return {}


def _save_profile_config(user_data_dir: str, config: Dict[str, Any]) -> None:
    """Save browser profile config for future reuse."""
    config_path = os.path.join(user_data_dir, PROFILE_CONFIG_FILE)
    try:
        os.makedirs(user_data_dir, exist_ok=True)
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)
        logger.debug(f"[BrowserSession] Saved profile config: {config_path}")
    except Exception as e:
        logger.warning(f"[BrowserSession] Failed to save profile config: {e}")


def get_browser_config(user_data_dir: Optional[str] = None) -> Dict[str, Any]:
    """
    Get browser configuration, reusing persisted values when available.

    On first run: picks a random UA/viewport, saves to profile config.
    On subsequent runs: reuses the saved UA/viewport for consistency.
    """
    saved = {}
    if user_data_dir:
        saved = _load_profile_config(user_data_dir)

    # Reuse saved config or generate new one
    user_agent = saved.get("user_agent") or random.choice(USER_AGENTS)
    viewport = saved.get("viewport") or DEFAULT_VIEWPORT

    config = {
        "user_agent": user_agent,
        "viewport": viewport,
        "is_docker": is_docker_environment(),
        "use_headless": should_use_headless(),
    }

    # Persist if this is a new profile or config changed
    if user_data_dir and (
        not saved
        or saved.get("user_agent") != user_agent
        or saved.get("viewport") != viewport
    ):
        _save_profile_config(
            user_data_dir,
            {
                "user_agent": user_agent,
                "viewport": viewport,
            },
        )

    return config


class BrowserSession:
    """
    Unified context manager for Playwright browser sessions.

    Always uses browser.launch() + new_context(storage_state=) pattern.
    Never uses launch_persistent_context to avoid profile locking issues
    and ensure consistent session management across all IG tools.

    Handles:
    - Browser/context lifecycle management
    - Session persistence via storage_state.json (always saved on exit)
    - Consistent User-Agent (persisted per profile, never randomized)
    - Anti-detection measures
    """

    def __init__(
        self,
        user_data_dir: Optional[str] = None,
        cleanup_stale: bool = True,
    ):
        self.user_data_dir = user_data_dir
        self.cleanup_stale = cleanup_stale
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.storage_state_path: Optional[str] = None
        self._playwright = None
        self._config: Dict[str, Any] = {}

    async def __aenter__(self) -> Tuple[Browser, BrowserContext, Page]:
        """Start browser session and return browser, context, and page."""
        # Pre-launch hygiene: reap zombies and clean corrupted cache without
        # terminating active Chromium sessions from other tasks.
        prepare_browser_runtime(
            self.user_data_dir,
            reap_zombies=self.cleanup_stale,
        )

        self._config = get_browser_config(self.user_data_dir)

        logger.info(
            f"[BrowserSession] UA={self._config['user_agent'][:50]}..., "
            f"Viewport={self._config['viewport']}"
        )
        logger.info(
            f"[BrowserSession] is_docker={self._config['is_docker']}, "
            f"use_headless={self._config['use_headless']}"
        )

        # Wrap entire launch in timeout to prevent indefinite hangs
        # after crash recovery (stale node drivers / corrupted state).
        launch_timeout = float(os.environ.get("IG_BROWSER_LAUNCH_TIMEOUT", "60"))
        try:
            return await asyncio.wait_for(self._do_launch(), timeout=launch_timeout)
        except asyncio.TimeoutError:
            logger.error(
                "[BrowserSession] Browser launch timed out after %.0fs, "
                "cleaning up and re-raising",
                launch_timeout,
            )
            # Clean up only this session's resources. Do not kill global
            # Chromium/Playwright processes that may belong to other tasks.
            await self.__aexit__(None, None, None)
            prepare_browser_runtime(self.user_data_dir, reap_zombies=True)
            raise RuntimeError(
                f"Browser launch timed out after {launch_timeout}s "
                "(session cleanup applied without global process kill)"
            )

    async def _do_launch(self) -> Tuple[Browser, BrowserContext, Page]:
        """Internal launch logic, separated so __aenter__ can wrap with timeout."""
        self._playwright = await async_playwright().start()
        p = self._playwright

        chromium_path = get_chromium_executable_path()

        # Docker requires additional Chromium flags to prevent renderer crashes
        docker_args = [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
        ]

        self.browser = await p.chromium.launch(
            headless=self._config["use_headless"],
            executable_path=chromium_path,
            args=docker_args if self._config["is_docker"] else [],
        )

        # Build context options
        context_opts: Dict[str, Any] = {
            "viewport": self._config["viewport"],
            "user_agent": self._config["user_agent"],
            "locale": "en-US",
            "timezone_id": "America/New_York",
        }

        # Load storage_state if available
        if self.user_data_dir:
            self.storage_state_path = os.path.join(
                self.user_data_dir, "storage_state.json"
            )
            if os.path.exists(self.storage_state_path):
                logger.info(
                    f"[BrowserSession] Loading storage_state: {self.storage_state_path}"
                )
                context_opts["storage_state"] = self.storage_state_path
            else:
                logger.info(
                    f"[BrowserSession] No storage_state found, starting fresh session"
                )
                os.makedirs(self.user_data_dir, exist_ok=True)

        self.context = await self.browser.new_context(**context_opts)
        self.page = await self.context.new_page()

        # Apply anti-detection measures
        await self.page.add_init_script(ANTI_DETECTION_SCRIPT)
        logger.info("[BrowserSession] Anti-detection script applied")

        return self.browser, self.context, self.page

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Clean up browser session and save storage state if session is valid."""
        # Save storage state on exit — but ONLY if sessionid cookie is still
        # present.  After page crashes or IG challenge redirects the context
        # may have lost the sessionid cookie.  Blindly saving that corrupted
        # state would overwrite the good session file, forcing a re-login.
        if self.context and self.storage_state_path:
            try:
                state = await self.context.storage_state()
                cookies = state.get("cookies", [])
                has_sessionid = any(c.get("name") == "sessionid" for c in cookies)
                if has_sessionid:
                    with open(self.storage_state_path, "w") as f:
                        json.dump(state, f)
                    logger.info(
                        f"[BrowserSession] Saved storage_state: "
                        f"{self.storage_state_path}"
                    )
                else:
                    logger.warning(
                        "[BrowserSession] sessionid cookie missing from "
                        "context — skipping storage_state save to preserve "
                        "existing session"
                    )
            except Exception as e:
                logger.warning(f"[BrowserSession] Failed to save storage_state: {e}")

        # Close context
        if self.context:
            try:
                await self.context.close()
            except Exception:
                pass

        # Close browser
        if self.browser:
            try:
                await self.browser.close()
            except Exception:
                pass

        # Stop playwright
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass

    @property
    def config(self) -> Dict[str, Any]:
        """Get current browser configuration."""
        return self._config


async def create_browser_session(
    user_data_dir: Optional[str] = None,
) -> BrowserSession:
    """
    Factory function to create a browser session.

    Example usage:
        async with BrowserSession(user_data_dir) as (browser, context, page):
            await page.goto("https://instagram.com")
    """
    return BrowserSession(user_data_dir)
