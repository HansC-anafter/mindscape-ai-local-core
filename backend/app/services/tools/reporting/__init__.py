"""Reporting tool factory functions."""

from backend.app.services.tools.reporting.html_report_tool import (
    WorkspaceHtmlReportTool,
)
from backend.app.services.tools.reporting.report_bundle_tool import (
    WorkspaceReportBundleTool,
)


def create_reporting_tools():
    """Create builtin reporting tools."""
    return [
        WorkspaceHtmlReportTool(),
        WorkspaceReportBundleTool(),
    ]


__all__ = [
    "WorkspaceHtmlReportTool",
    "WorkspaceReportBundleTool",
    "create_reporting_tools",
]
