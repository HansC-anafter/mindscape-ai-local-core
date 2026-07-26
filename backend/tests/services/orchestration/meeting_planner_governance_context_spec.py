from types import SimpleNamespace
from pathlib import Path

import pytest

from backend.app.services.tools.meeting_planner import tool_plan
from backend.app.services.tools.meeting_planner.tool_plan import (
    ExecutePlannerToolPlanTool,
)
from backend.app.services.tools.registry import register_reporting_tools
from backend.app.services.unified_tool_executor_core.governance_context import (
    VerifiedToolExecutionContext,
)


def _context():
    selector = ExecutePlannerToolPlanTool.TOOL_NAME
    return VerifiedToolExecutionContext(
        snapshot_hash="1" * 64,
        workspace_id="workspace-a",
        actor_user_id="owner-a",
        allowed_workspace_ids=("workspace-a",),
        allowed_group_ids=(),
        workspace_owner_user_id="owner-a",
        active_group_id=None,
        group_owner_user_id=None,
        root_execution_id="root-a",
        trace_id="trace-a",
        source_entry="local",
        selector_lineage=(selector,),
        context_sha256="2" * 64,
    )


@pytest.mark.asyncio
async def test_meeting_planner_derives_context_for_each_child_step(
    monkeypatch,
):
    calls = []

    class FakeExecutor:
        async def execute_tool(
            self,
            tool_name,
            arguments,
            *,
            governance_context=None,
        ):
            calls.append((tool_name, arguments, governance_context))
            return SimpleNamespace(
                success=True,
                result={"archive_path": "/tmp/report.zip"},
                error=None,
            )

    monkeypatch.setattr(
        tool_plan,
        "UnifiedToolExecutor",
        FakeExecutor,
    )
    result = await ExecutePlannerToolPlanTool().execute_with_context(
        governance_context=_context(),
        planner_tool_plan={
            "plan_id": "plan-a",
            "workspace_id": "workspace-a",
            "meeting_id": "meeting-a",
            "pack_id": "core",
            "categories": [],
            "steps": [
                {
                    "step_id": "share-report",
                    "role": "report_packager",
                    "category_id": "report",
                    "category_label": "Report",
                    "tool_name": "core.workspace_package_report",
                    "resource_kind": "report",
                    "effect": "write",
                    "arguments": {
                        "workspace_id": "workspace-a",
                        "report_path": "reports/html/report.html",
                    },
                }
            ],
        },
    )

    assert result["status"] == "success"
    assert len(calls) == 1
    child = calls[0][2]
    assert child.selector_lineage == (
        ExecutePlannerToolPlanTool.TOOL_NAME,
        "core.workspace_package_report",
    )
    assert child.workspace_id == "workspace-a"


@pytest.mark.asyncio
async def test_meeting_planner_stops_for_structured_owner_review(
    monkeypatch,
):
    class FakeExecutor:
        async def execute_tool(
            self,
            tool_name,
            arguments,
            *,
            governance_context=None,
        ):
            return SimpleNamespace(
                success=True,
                result={
                    "status": "preflight_completed",
                    "artifact_created": False,
                    "review_requirements": [
                        "verified_owner_review:report.html"
                    ],
                    "blocking_codes": [],
                    "review_binding_sha256": "a" * 64,
                },
                error=None,
            )

    monkeypatch.setattr(
        tool_plan,
        "UnifiedToolExecutor",
        FakeExecutor,
    )
    result = await ExecutePlannerToolPlanTool().execute_with_context(
        governance_context=_context(),
        planner_tool_plan={
            "plan_id": "plan-a",
            "workspace_id": "workspace-a",
            "meeting_id": "meeting-a",
            "pack_id": "core",
            "steps": [
                {
                    "step_id": "share-report",
                    "role": "report_packager",
                    "category_id": "report",
                    "category_label": "Report",
                    "tool_name": "core.workspace_package_report",
                    "resource_kind": "report",
                    "effect": "write",
                }
            ],
        },
    )

    assert result["status"] == "waiting"
    assert result["completed_count"] == 0
    assert result["plan_steps"][0]["status"] == "waiting"


@pytest.mark.asyncio
async def test_meeting_planner_executes_canonical_report_child(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    sandbox = (
        tmp_path / "workspaces" / "workspace-a" / "sandbox"
    )
    report = sandbox / "reports" / "html" / "report.html"
    report.parent.mkdir(parents=True)
    report.write_text(
        "<!doctype html><p>Meeting report</p>",
        encoding="utf-8",
    )
    register_reporting_tools()

    result = await ExecutePlannerToolPlanTool().execute_with_context(
        governance_context=_context(),
        planner_tool_plan={
            "plan_id": "plan-live",
            "workspace_id": "workspace-a",
            "meeting_id": "meeting-a",
            "pack_id": "core",
            "steps": [
                {
                    "step_id": "share-report",
                    "role": "report_packager",
                    "category_id": "report",
                    "category_label": "Report",
                    "tool_name": "core.workspace_package_report",
                    "resource_kind": "report",
                    "effect": "write",
                    "arguments": {
                        "workspace_id": "workspace-a",
                        "report_path": (
                            report.relative_to(sandbox).as_posix()
                        ),
                    },
                }
            ],
        },
    )

    assert result["status"] == "success"
    archive_path = Path(
        result["plan_steps"][0]["result"]["archive_path"]
    )
    assert archive_path.exists()
