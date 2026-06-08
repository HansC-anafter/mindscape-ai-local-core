"""Reporting tool factory functions."""

from backend.app.services.tools.reporting.html_report_tool import (
    WorkspaceHtmlReportTool,
)


def create_reporting_tools():
    """Create builtin reporting tools."""
    return [WorkspaceHtmlReportTool()]


__all__ = ["WorkspaceHtmlReportTool", "create_reporting_tools"]
