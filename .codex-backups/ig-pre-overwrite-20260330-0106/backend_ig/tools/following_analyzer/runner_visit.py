"""
Visit Phase Orchestration Module.

Contains the flow-control logic for the visit phase:
- Determining whether to visit account pages
- Checking if results are partial
"""

import logging
from typing import Any, Dict, List, Optional

from .artifact_manager import ArtifactManager
from .resume_manager import ResumeManager

logger = logging.getLogger(__name__)


async def should_visit_pages(
    visit_account_pages: bool,
    accounts: List[Dict[str, Any]],
    expected_following_count: Optional[int],
    list_capture_status: Optional[str],
    max_accounts: Optional[int],
    resume_manager: ResumeManager,
    artifact_manager: ArtifactManager,
    mode: str,
    allow_partial_resume: bool,
) -> bool:
    """Determine if we should proceed to visiting account pages.

    When visit_account_pages is True, always honor the user's request.
    Visiting unvisited accounts takes priority over list completeness.
    The full-list gate has been removed: if the user enables visit_pages,
    we proceed regardless of whether the list is complete.
    """
    if not visit_account_pages:
        return False

    if not accounts:
        logger.info("[IGFollowingAnalyzer] No accounts available to visit")
        return False

    # Best-effort: try to supplement accounts from saved dedup union
    # so we visit as many accounts as possible.
    if expected_following_count and not max_accounts:
        if len(accounts) < int(expected_following_count):
            try:
                saved_union = resume_manager.load_saved_accounts_union(
                    expected_following_count
                )
            except Exception:
                saved_union = None

            if saved_union and isinstance(saved_union.get("accounts"), list):
                accounts_saved = saved_union.get("accounts") or []
                if len(accounts_saved) > len(accounts):
                    logger.info(
                        f"[IGFollowingAnalyzer] Supplementing account list from "
                        f"saved dedup union (current={len(accounts)}, "
                        f"saved={len(accounts_saved)})"
                    )
                    accounts.clear()
                    accounts.extend(accounts_saved)
                    if len(accounts_saved) >= int(expected_following_count):
                        artifact_manager.set_list_capture_status("full")
                        artifact_manager.set_scroll_stop_reason(
                            "saved_list_satisfies_expected"
                        )

    logger.info(
        f"[IGFollowingAnalyzer] Proceeding to visit_pages: "
        f"{len(accounts)} accounts "
        f"(expected={expected_following_count or 'unknown'})"
    )
    return True


def is_partial_result(
    accounts: List[Dict[str, Any]],
    expected_following_count: Optional[int],
    max_accounts: Optional[int],
) -> bool:
    """Determine if result is partial (significantly below expected)."""
    if not expected_following_count or max_accounts:
        return False
    gap = int(expected_following_count) - len(accounts)
    return gap > 50 and len(accounts) < int(expected_following_count * 0.9)
