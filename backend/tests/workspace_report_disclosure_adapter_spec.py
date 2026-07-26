from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from backend.app.services.tools.reporting.report_bundle_tool import (
    WorkspaceReportBundleTool,
)
from backend.app.services.unified_tool_executor_core.governance_context import (
    VerifiedToolExecutionContext,
)


def _context(
    *,
    actor: str = "owner-a",
    owner: str = "owner-a",
) -> VerifiedToolExecutionContext:
    return VerifiedToolExecutionContext(
        snapshot_hash="1" * 64,
        workspace_id="workspace-a",
        actor_user_id=actor,
        allowed_workspace_ids=("workspace-a",),
        allowed_group_ids=(),
        workspace_owner_user_id=owner,
        active_group_id=None,
        group_owner_user_id=None,
        root_execution_id="root-a",
        trace_id="trace-a",
        source_entry="local",
        selector_lineage=("workspace_package_report",),
        context_sha256="2" * 64,
    )


async def _call(tool, context, **arguments):
    return await tool.execute_with_context(
        governance_context=context,
        **arguments,
    )


@pytest.mark.asyncio
async def test_external_preflight_review_and_redacted_archive(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    sandbox = tmp_path / "workspaces" / "workspace-a" / "sandbox"
    report = sandbox / "reports" / "html" / "report.html"
    report.parent.mkdir(parents=True)
    report.write_text(
        "<!doctype html><p>Contact person@example.com</p>",
        encoding="utf-8",
    )
    tool = WorkspaceReportBundleTool()
    arguments = {
        "workspace_id": "workspace-a",
        "sandbox_path": str(sandbox),
        "report_path": report.relative_to(sandbox).as_posix(),
        "distribution_scope": "external",
        "recipient_ref": "recipient:acceptance",
    }

    preflight = await _call(
        tool,
        _context(),
        operation="preflight",
        **arguments,
    )
    assert preflight["status"] == "preflight_completed"
    assert preflight["artifact_created"] is False
    assert preflight["share_authorization"] == "external_review_required"
    assert not list(sandbox.rglob("*.zip"))

    packaged = await _call(
        tool,
        _context(),
        operation="package",
        disclosure_review={
            "binding_sha256": preflight["review_binding_sha256"],
            "acknowledgement": "I_APPROVE_EXTERNAL_DISCLOSURE",
        },
        **arguments,
    )
    assert packaged["artifact_created"] is True
    assert packaged["share_authorization"] == "external_authorized"
    assert report.read_text(encoding="utf-8").endswith(
        "person@example.com</p>"
    )
    with zipfile.ZipFile(packaged["archive_path"]) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        archived = archive.read(manifest["files"][0]["archive_path"])
        assert b"person@example.com" not in archived
        assert b"[REDACTED:EMAIL]" in archived
        assert manifest["schema_version"] == (
            "mindscape.report-share-bundle.v2"
        )
        assert manifest["files"][0]["classification"] == "confidential"
        assert manifest["files"][0]["action"] == "redact"
        assert manifest["files"][0]["source_sha256"] != (
            manifest["files"][0]["output_sha256"]
        )


@pytest.mark.asyncio
async def test_tool_rejects_missing_context_and_owner_spoof(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    sandbox = tmp_path / "workspaces" / "workspace-a" / "sandbox"
    report = sandbox / "reports" / "html" / "report.html"
    report.parent.mkdir(parents=True)
    report.write_text("<!doctype html><p>Internal</p>", encoding="utf-8")
    arguments = {
        "workspace_id": "workspace-a",
        "sandbox_path": str(sandbox),
        "report_path": report.relative_to(sandbox).as_posix(),
    }
    tool = WorkspaceReportBundleTool()

    with pytest.raises(
        ValueError,
        match="verified_tool_execution_context_required",
    ):
        await tool.execute(**arguments)

    preflight = await _call(
        tool,
        _context(actor="member-a", owner="owner-a"),
        operation="preflight",
        distribution_scope="external",
        recipient_ref="recipient:blocked",
        disclosure_review={
            "binding_sha256": "f" * 64,
            "acknowledgement": "I_APPROVE_EXTERNAL_DISCLOSURE",
            "reviewer_id": "owner-a",
        },
        **arguments,
    )
    assert "external_workspace_owner_required" in (
        preflight["blocking_codes"]
    )
    assert preflight["artifact_created"] is False
