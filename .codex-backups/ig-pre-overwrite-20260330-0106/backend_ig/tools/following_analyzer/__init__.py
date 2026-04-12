"""
Following analyzer tool implementation modules.

This package is intentionally split to keep each file readable and maintainable.
The legacy entrypoint remains in `capabilities/ig/tools/ig_following_analyzer.py`.

Module structure:
- runner.py: Main orchestration (~550 lines)
- auth.py: Authentication helpers
- persistence.py: Database persistence
- resume_manager.py: Resume and artifact merging logic
- artifact_manager.py: Progress artifact CRUD
- watchdog.py: Background heartbeat thread
- browser_session.py: Playwright browser lifecycle
- page_visitor.py: Account page visiting logic
"""

from .tool import IGFollowingAnalyzerTool, ig_analyze_following_tool
from .runner import ig_analyze_following

# Export new modules for external use if needed
from .auth import assert_logged_in, try_get_logged_in_username
from .persistence import persist_accounts_flat, persist_follow_edges
from .resume_manager import ResumeManager, normalize_accounts
from .artifact_manager import ArtifactManager
from .watchdog import ProgressWatchdog, create_and_start_watchdog
from .browser_session import BrowserSession
from .page_visitor import PageVisitor, visit_account_pages

__all__ = [
    # Main exports
    "IGFollowingAnalyzerTool",
    "ig_analyze_following",
    "ig_analyze_following_tool",
    # New modular components
    "assert_logged_in",
    "try_get_logged_in_username",
    "persist_accounts_flat",
    "persist_follow_edges",
    "ResumeManager",
    "normalize_accounts",
    "ArtifactManager",
    "ProgressWatchdog",
    "create_and_start_watchdog",
    "BrowserSession",
    "PageVisitor",
    "visit_account_pages",
]
