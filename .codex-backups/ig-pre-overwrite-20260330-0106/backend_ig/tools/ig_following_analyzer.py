"""
IG Following Analyzer Tool (Entry Point)

This file intentionally remains as a thin entrypoint to preserve import paths for the
capability registry. The implementation has been migrated into:

- `capabilities/ig/tools/following_analyzer/runner.py`
- `capabilities/ig/tools/following_analyzer/tool.py`
- `capabilities/ig/tools/following_analyzer/*` helpers
"""

from .following_analyzer.runner import ig_analyze_following
from .following_analyzer.scroll_extract import extract_following_list as _extract_following_list
from .following_analyzer.page_analyzer import analyze_account_page as _analyze_account_page
from .following_analyzer.progress import generate_summary as _generate_summary
from .following_analyzer.utils import (
    classify_failure as _classify_failure,
    detect_risk_signal as _detect_risk_signal,
    get_chromium_executable_path as _get_chromium_executable_path,
    parse_count_text_to_int as _parse_count_text_to_int,
    random_delay as _random_delay,
)
from .following_analyzer.tool import IGFollowingAnalyzerTool, ig_analyze_following_tool

__all__ = [
    "IGFollowingAnalyzerTool",
    "ig_analyze_following",
    "ig_analyze_following_tool",
    # Legacy helper exports (kept for backwards compatibility within the repo)
    "_classify_failure",
    "_parse_count_text_to_int",
    "_detect_risk_signal",
    "_get_chromium_executable_path",
    "_random_delay",
    "_extract_following_list",
    "_analyze_account_page",
    "_generate_summary",
]

