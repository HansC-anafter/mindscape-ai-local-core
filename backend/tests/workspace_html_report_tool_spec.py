from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.services.tools.registry import (
    get_mindscape_tool,
    register_reporting_tools,
)
from backend.app.services.tools.reporting.html_report_tool import WorkspaceHtmlReportTool
from backend.app.services.unified_tool_executor import UnifiedToolExecutor
from backend.app.routes.core.tools import filtered


@pytest.mark.asyncio
async def test_workspace_html_report_tool_writes_static_html(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    sandbox_path = tmp_path / "workspaces" / "workspace-1" / "sandbox"

    tool = WorkspaceHtmlReportTool()
    result = await tool.execute(
        workspace_id="workspace-1",
        sandbox_path=str(sandbox_path),
        file_name="practice-summary.html",
        html="<main><h1>Practice Summary</h1></main>",
        title="Practice Summary",
    )

    target_path = Path(result["file_path"])
    assert result["success"] is True
    assert result["artifact_kind"] == "html_report"
    assert result["relative_path"] == "reports/html/practice-summary.html"
    assert target_path.exists()
    assert target_path.read_text(encoding="utf-8").startswith("<!doctype html>")


@pytest.mark.asyncio
async def test_workspace_html_report_tool_preserves_slash_wrapped_subdir(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    sandbox_path = tmp_path / "workspaces" / "workspace-1" / "sandbox"

    result = await WorkspaceHtmlReportTool().execute(
        workspace_id="workspace-1",
        sandbox_path=str(sandbox_path),
        report_subdir="/reports/custom/",
        file_name="compatibility.html",
        html="<main>Compatibility</main>",
    )

    assert result["relative_path"] == "reports/custom/compatibility.html"
    assert Path(result["file_path"]).is_file()


@pytest.mark.asyncio
async def test_workspace_html_report_tool_rejects_path_traversal(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    sandbox_path = tmp_path / "workspaces" / "workspace-1" / "sandbox"

    tool = WorkspaceHtmlReportTool()

    with pytest.raises(ValueError, match="single file name"):
        await tool.execute(
            workspace_id="workspace-1",
            sandbox_path=str(sandbox_path),
            file_name="../outside.html",
            html="<main>Report</main>",
        )


@pytest.mark.asyncio
async def test_workspace_html_report_tool_rejects_non_html_filename(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    sandbox_path = tmp_path / "workspaces" / "workspace-1" / "sandbox"

    tool = WorkspaceHtmlReportTool()

    with pytest.raises(ValueError, match="must end with .html"):
        await tool.execute(
            workspace_id="workspace-1",
            sandbox_path=str(sandbox_path),
            file_name="practice-summary.txt",
            html="<main>Report</main>",
        )


@pytest.mark.asyncio
async def test_workspace_html_report_tool_rejects_script_like_content(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    sandbox_path = tmp_path / "workspaces" / "workspace-1" / "sandbox"

    tool = WorkspaceHtmlReportTool()

    with pytest.raises(ValueError, match="must be static"):
        await tool.execute(
            workspace_id="workspace-1",
            sandbox_path=str(sandbox_path),
            file_name="practice-summary.html",
            html="<script>alert('x')</script>",
        )


@pytest.mark.asyncio
async def test_reporting_tools_register_for_catalog_and_executor(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    sandbox_path = tmp_path / "workspaces" / "workspace-1" / "sandbox"

    register_reporting_tools()
    assert get_mindscape_tool("workspace_write_html_report") is not None
    assert get_mindscape_tool("core.workspace_write_html_report") is not None
    assert get_mindscape_tool("workspace_package_report") is not None
    assert get_mindscape_tool("core.workspace_package_report") is not None

    executor = UnifiedToolExecutor()
    result = await executor.execute_tool(
        "core.workspace_write_html_report",
        {
            "workspace_id": "workspace-1",
            "sandbox_path": str(sandbox_path),
            "file_name": "executor-report.html",
            "html": "<main>Executor report</main>",
            "title": "Executor Report",
        },
    )

    assert result.success is True
    assert result.result["relative_path"] == "reports/html/executor-report.html"
    assert Path(result.result["file_path"]).exists()


def test_filtered_tools_include_reporting_tool_for_report_tasks():
    tool = type("Tool", (), {"tool_id": "core.workspace_write_html_report"})()
    tools = []

    result = filtered._ensure_reporting_tool(
        tools,
        {"core.workspace_write_html_report": tool},
        "Meeting Engine should output an HTML report",
    )

    assert [item.tool_id for item in result] == ["core.workspace_write_html_report"]
