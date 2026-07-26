from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from backend.app.routes.core.tools import filtered
from backend.app.services.tools.registry import (
    get_mindscape_tool,
    register_reporting_tools,
)
from backend.app.services.tools.reporting import report_bundle_graph
from backend.app.services.tools.reporting.report_bundle_tool import (
    WorkspaceReportBundleTool,
)
from backend.app.services.unified_tool_executor import UnifiedToolExecutor
from backend.app.services.unified_tool_executor_core.governance_context import (
    VerifiedToolExecutionContext,
)


def _governance_context(
    workspace_id: str = "workspace-1",
    selector_key: str = "workspace_package_report",
) -> VerifiedToolExecutionContext:
    return VerifiedToolExecutionContext(
        snapshot_hash="1" * 64,
        workspace_id=workspace_id,
        actor_user_id="owner-1",
        allowed_workspace_ids=(workspace_id,),
        allowed_group_ids=(),
        workspace_owner_user_id="owner-1",
        active_group_id=None,
        group_owner_user_id=None,
        root_execution_id="root-1",
        trace_id="trace-1",
        source_entry="local",
        selector_lineage=(selector_key,),
        context_sha256="2" * 64,
    )


async def _execute(tool, **arguments):
    return await tool.execute_with_context(
        governance_context=_governance_context(
            arguments.get("workspace_id") or "workspace-1"
        ),
        **arguments,
    )


def _write_fixture_report(sandbox_path: Path) -> Path:
    report_path = sandbox_path / "reports" / "html" / "acceptance.html"
    css_path = sandbox_path / "reports" / "html" / "assets" / "report.css"
    background_path = sandbox_path / "reports" / "html" / "images" / "bg.png"
    evidence_path = sandbox_path / "reports" / "evidence" / "receipt.json"
    plan_path = sandbox_path / "plans" / "implementation.md"

    for path in (
        report_path,
        css_path,
        background_path,
        evidence_path,
        plan_path,
    ):
        path.parent.mkdir(parents=True, exist_ok=True)

    report_path.write_text(
        """
<!doctype html>
<html>
<head>
  <link rel="stylesheet" href="assets/report.css">
</head>
<body style="background-image: url('images/bg.png')">
  <a href="../../plans/implementation.md">Plan</a>
  <a href="../evidence/receipt.json">Receipt</a>
  <a href="https://example.com/reference">External</a>
</body>
</html>
""".strip(),
        encoding="utf-8",
    )
    css_path.write_text(
        '@import "../theme/base.css";\n.hero { background: url("../images/bg.png"); }\n',
        encoding="utf-8",
    )
    theme_path = sandbox_path / "reports" / "html" / "theme" / "base.css"
    theme_path.parent.mkdir(parents=True, exist_ok=True)
    theme_path.write_text(".hero { color: #111; }\n", encoding="utf-8")
    background_path.write_bytes(b"\x89PNG\r\nfixture")
    evidence_path.write_text('{"status":"passed"}\n', encoding="utf-8")
    plan_path.write_text("# Implementation plan\n", encoding="utf-8")
    return report_path


def _assert_manifest_hashes(
    archive: zipfile.ZipFile,
    manifest: dict,
) -> None:
    for item in manifest["files"]:
        content = archive.read(item["archive_path"])
        assert len(content) == item["size"]
        assert hashlib.sha256(content).hexdigest() == item["sha256"]


def test_report_bundle_declares_max_bound_execution_budget():
    metadata = WorkspaceReportBundleTool().metadata

    assert metadata.execution_timeout_seconds == 90


@pytest.mark.asyncio
async def test_report_bundle_packages_linked_files_with_manifest(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    sandbox_path = tmp_path / "workspaces" / "workspace-1" / "sandbox"
    report_path = _write_fixture_report(sandbox_path)

    result = await _execute(
        WorkspaceReportBundleTool(),
        workspace_id="workspace-1",
        sandbox_path=str(sandbox_path),
        report_path=report_path.relative_to(sandbox_path).as_posix(),
    )

    archive_path = Path(result["archive_path"])
    assert result["success"] is True
    assert result["status"] == "completed"
    assert result["terminal"] is True
    assert result["artifact_kind"] == "report_share_bundle"
    assert result["bundle_completeness"] == "complete"
    assert result["file_count"] == 6
    assert result["missing_references"] == []
    assert len(result["external_references"]) == 1
    assert result["external_references"][0]["reference"] == (
        "https://example.com/reference"
    )
    assert hashlib.sha256(archive_path.read_bytes()).hexdigest() == (
        result["archive_sha256"]
    )

    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        assert names[:2] == ["index.html", "manifest.json"]
        assert "report/reports/html/acceptance.html" in names
        assert "report/reports/html/assets/report.css" in names
        assert "report/reports/html/theme/base.css" in names
        assert "report/reports/html/images/bg.png" in names
        assert "report/reports/evidence/receipt.json" in names
        assert "report/plans/implementation.md" in names
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["entrypoint"] == "report/reports/html/acceptance.html"
        assert manifest["bundle_status"] == "complete"
        assert manifest["graph_sha256"] == result["graph_sha256"]
        assert len(manifest["review_binding_sha256"]) == 64
        _assert_manifest_hashes(archive, manifest)


@pytest.mark.asyncio
async def test_report_bundle_binds_omitted_workspace_to_verified_context(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    sandbox_path = tmp_path / "workspaces" / "workspace-1" / "sandbox"
    report_path = _write_fixture_report(sandbox_path)

    result = await _execute(
        WorkspaceReportBundleTool(),
        sandbox_path=str(sandbox_path),
        report_path=report_path.relative_to(sandbox_path).as_posix(),
    )

    assert result["workspace_id"] == "workspace-1"
    assert Path(result["archive_path"]).exists()


@pytest.mark.asyncio
async def test_report_bundle_rechecks_source_hash_before_archive_commit(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    sandbox_path = tmp_path / "workspaces" / "workspace-1" / "sandbox"
    report_path = _write_fixture_report(sandbox_path)
    delegate = WorkspaceReportBundleTool()._disclosure_adapter

    class MutatingAdapter:
        def evaluate(self, **kwargs):
            plan = delegate.evaluate(**kwargs)
            report_path.write_text(
                "<!doctype html><p>changed after decision</p>",
                encoding="utf-8",
            )
            return plan

    with pytest.raises(
        ValueError,
        match="artifact_source_(size|hash)_drift",
    ):
        await _execute(
            WorkspaceReportBundleTool(
                disclosure_adapter=MutatingAdapter()
            ),
            workspace_id="workspace-1",
            sandbox_path=str(sandbox_path),
            report_path=report_path.relative_to(sandbox_path).as_posix(),
            archive_name="drift.zip",
        )

    assert not (sandbox_path / "reports" / "shared" / "drift.zip").exists()


@pytest.mark.asyncio
async def test_report_bundle_rechecks_redacted_source_and_reads_it_twice(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    sandbox_path = tmp_path / "workspaces" / "workspace-1" / "sandbox"
    report_path = sandbox_path / "reports" / "html" / "confidential.html"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        "<!doctype html><p>person@example.com</p>",
        encoding="utf-8",
    )
    source_open_count = 0
    original_open = Path.open

    def tracking_open(path, *args, **kwargs):
        nonlocal source_open_count
        if path == report_path:
            source_open_count += 1
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", tracking_open)
    result = await _execute(
        WorkspaceReportBundleTool(),
        workspace_id="workspace-1",
        sandbox_path=str(sandbox_path),
        report_path=report_path.relative_to(sandbox_path).as_posix(),
        archive_name="redacted.zip",
    )

    assert source_open_count == 2
    with zipfile.ZipFile(result["archive_path"]) as archive:
        content = archive.read("report/confidential.html")
    assert b"person@example.com" not in content
    assert b"[REDACTED:EMAIL]" in content
    assert b"person@example.com" in report_path.read_bytes()


@pytest.mark.asyncio
async def test_report_bundle_rejects_redacted_source_drift(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    sandbox_path = tmp_path / "workspaces" / "workspace-1" / "sandbox"
    report_path = sandbox_path / "reports" / "html" / "confidential.html"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        "<!doctype html><p>person@example.com</p>",
        encoding="utf-8",
    )
    delegate = WorkspaceReportBundleTool()._disclosure_adapter

    class MutatingAdapter:
        def evaluate(self, **kwargs):
            plan = delegate.evaluate(**kwargs)
            report_path.write_text(
                "<!doctype html><p>changed@example.com</p>",
                encoding="utf-8",
            )
            return plan

    with pytest.raises(
        ValueError,
        match="artifact_source_(size|hash)_drift",
    ):
        await _execute(
            WorkspaceReportBundleTool(
                disclosure_adapter=MutatingAdapter()
            ),
            workspace_id="workspace-1",
            sandbox_path=str(sandbox_path),
            report_path=report_path.relative_to(sandbox_path).as_posix(),
            archive_name="redacted-drift.zip",
        )

    assert not (
        sandbox_path / "reports" / "shared" / "redacted-drift.zip"
    ).exists()


@pytest.mark.asyncio
async def test_report_bundle_is_deterministic(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    sandbox_path = tmp_path / "workspaces" / "workspace-1" / "sandbox"
    report_path = _write_fixture_report(sandbox_path)
    tool = WorkspaceReportBundleTool()
    arguments = {
        "workspace_id": "workspace-1",
        "sandbox_path": str(sandbox_path),
        "report_path": report_path.relative_to(sandbox_path).as_posix(),
    }

    first = await _execute(
        tool,
        **arguments,
        archive_name="first.zip",
    )
    second = await _execute(
        tool,
        **arguments,
        archive_name="second.zip",
    )

    assert Path(first["archive_path"]).read_bytes() == Path(
        second["archive_path"]
    ).read_bytes()
    assert first["archive_sha256"] == second["archive_sha256"]


@pytest.mark.asyncio
async def test_report_bundle_requires_explicit_overwrite(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    sandbox_path = tmp_path / "workspaces" / "workspace-1" / "sandbox"
    report_path = _write_fixture_report(sandbox_path)
    tool = WorkspaceReportBundleTool()
    arguments = {
        "workspace_id": "workspace-1",
        "sandbox_path": str(sandbox_path),
        "report_path": report_path.relative_to(sandbox_path).as_posix(),
        "archive_name": "existing.zip",
    }

    first = await _execute(tool, **arguments)
    with pytest.raises(ValueError, match="overwrite is false"):
        await _execute(tool, **arguments)
    replaced = await _execute(tool, **arguments, overwrite=True)

    assert first["file_existed"] is False
    assert replaced["file_existed"] is True
    assert replaced["overwrite"] is True
    assert replaced["archive_sha256"] == first["archive_sha256"]


@pytest.mark.asyncio
async def test_report_bundle_missing_reference_policy(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    sandbox_path = tmp_path / "workspaces" / "workspace-1" / "sandbox"
    report_path = sandbox_path / "reports" / "html" / "missing.html"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        '<!doctype html><img src="../evidence/missing.png">',
        encoding="utf-8",
    )
    tool = WorkspaceReportBundleTool()
    arguments = {
        "workspace_id": "workspace-1",
        "sandbox_path": str(sandbox_path),
        "report_path": report_path.relative_to(sandbox_path).as_posix(),
    }

    with pytest.raises(ValueError, match="missing local references"):
        await _execute(tool, **arguments)

    result = await _execute(
        tool,
        **arguments,
        archive_name="partial.zip",
        missing_reference_policy="record",
    )

    assert result["bundle_completeness"] == "partial"
    assert result["missing_references"] == [
        {
            "source": "reports/html/missing.html",
            "reference": "../evidence/missing.png",
            "kind": "missing",
        }
    ]


@pytest.mark.asyncio
async def test_report_bundle_rejects_traversal_and_symlinks(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    sandbox_path = tmp_path / "workspaces" / "workspace-1" / "sandbox"
    report_path = _write_fixture_report(sandbox_path)
    tool = WorkspaceReportBundleTool()

    with pytest.raises(ValueError, match="safe relative path"):
        await _execute(
            tool,
            workspace_id="workspace-1",
            sandbox_path=str(sandbox_path),
            report_path="../outside.html",
        )

    linked_report = report_path.parent / "linked.html"
    linked_report.symlink_to(report_path)
    with pytest.raises(ValueError, match="symlink"):
        await _execute(
            tool,
            workspace_id="workspace-1",
            sandbox_path=str(sandbox_path),
            report_path=linked_report.relative_to(sandbox_path).as_posix(),
        )


@pytest.mark.asyncio
async def test_report_bundle_enforces_file_and_byte_limits(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    sandbox_path = tmp_path / "workspaces" / "workspace-1" / "sandbox"
    report_path = _write_fixture_report(sandbox_path)
    arguments = {
        "workspace_id": "workspace-1",
        "sandbox_path": str(sandbox_path),
        "report_path": report_path.relative_to(sandbox_path).as_posix(),
    }

    monkeypatch.setattr(report_bundle_graph, "MAX_BUNDLE_FILES", 2)
    with pytest.raises(ValueError, match="2 file limit"):
        await _execute(WorkspaceReportBundleTool(), **arguments)

    monkeypatch.setattr(report_bundle_graph, "MAX_BUNDLE_FILES", 256)
    monkeypatch.setattr(report_bundle_graph, "MAX_BUNDLE_SOURCE_BYTES", 10)
    with pytest.raises(ValueError, match="128 MiB"):
        await _execute(WorkspaceReportBundleTool(), **arguments)


@pytest.mark.asyncio
async def test_report_bundle_registers_for_executor(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    sandbox_path = tmp_path / "workspaces" / "workspace-1" / "sandbox"
    report_path = _write_fixture_report(sandbox_path)

    register_reporting_tools()
    assert get_mindscape_tool("workspace_package_report") is not None
    assert get_mindscape_tool("core.workspace_package_report") is not None

    result = await UnifiedToolExecutor().execute_tool(
        "core.workspace_package_report",
        {
            "workspace_id": "workspace-1",
            "sandbox_path": str(sandbox_path),
            "report_path": report_path.relative_to(sandbox_path).as_posix(),
            "archive_name": "executor.zip",
        },
        governance_context=_governance_context(
            selector_key="core.workspace_package_report"
        ),
    )

    assert result.success is True
    assert result.result["status"] == "completed"
    assert result.result["terminal"] is True
    assert Path(result.result["archive_path"]).exists()


def test_filtered_tools_prioritize_packager_and_preserve_writer():
    packager = type("Tool", (), {"tool_id": "workspace_package_report"})()
    writer = type("Tool", (), {"tool_id": "core.workspace_write_html_report"})()
    tool_by_id = {
        "workspace_package_report": packager,
        "core.workspace_write_html_report": writer,
    }

    packaging_result = filtered._ensure_reporting_tool(
        [],
        tool_by_id,
        "Package and share this HTML report as a ZIP bundle",
    )
    writer_result = filtered._ensure_reporting_tool(
        [],
        tool_by_id,
        "Meeting Engine should output an HTML report",
    )

    assert [item.tool_id for item in packaging_result] == [
        "workspace_package_report",
        "core.workspace_write_html_report",
    ]
    assert [item.tool_id for item in writer_result] == [
        "core.workspace_write_html_report"
    ]
