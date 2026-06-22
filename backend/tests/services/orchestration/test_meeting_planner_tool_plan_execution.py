import pytest

from backend.app.services.orchestration.meeting.planner_contract_execution.tool_plan_compiler import (
    PlannerToolPlanCompiler,
)

from backend.tests.services.orchestration.meeting_planner_tool_plan_test_support import (
    FakeRegistry,
    build_legacy_binding_plan,
    install_fake_executor,
)


@pytest.mark.asyncio
async def test_execute_planner_tool_plan_merges_seed_and_reference_members(monkeypatch):
    from backend.app.services.tools.meeting_planner import tool_plan as tool_plan_module

    def result_for_tool(tool_name):
        if tool_name.endswith("ig_list_seeds"):
            return {
                "seeds": [
                    {
                        "handle": "yoga_studio",
                        "object_uri": "mindscape://ig/seed/yoga_studio",
                    }
                ]
            }
        if tool_name.endswith("ig_query_references"):
            return {
                "references": [
                    {
                        "reference_id": "ref_yoga",
                        "object_uri": "mindscape://ig/reference/ref_yoga",
                    }
                ]
            }
        if tool_name.endswith("ig_create_creative_space"):
            return {"creative_space": {"id": "space_yoga", "title": "瑜伽"}}
        return {"added_count": 2, "members": []}

    calls = install_fake_executor(monkeypatch, tool_plan_module, result_for_tool)
    plan = PlannerToolPlanCompiler(FakeRegistry()).compile(
        request_contract={
            "source_message": "幫我把所有當前跟瑜伽的 seed / refs 分門別類，各新增一個 creative space"
        },
        session_metadata={"active_capability_code": "ig"},
        workspace_id="ws_demo",
        meeting_id="mtg_demo",
    )
    assert plan is not None

    tool = tool_plan_module.ExecutePlannerToolPlanTool()
    result = await tool.execute(planner_tool_plan=plan.as_execution_payload())

    assert result["status"] == "success"
    add_members_call = calls[-1]
    assert add_members_call[0] == "ig.ig_add_creative_space_members"
    assert add_members_call[1]["creative_space_id"] == "space_yoga"
    assert add_members_call[1]["reference_ids"] == ["ref_yoga"]
    assert add_members_call[1]["object_uris"] == [
        "mindscape://ig/seed/yoga_studio",
        "mindscape://ig/reference/ref_yoga",
    ]


@pytest.mark.asyncio
async def test_execute_planner_tool_plan_legacy_role_bindings_resolve_to_step_results(
    monkeypatch,
):
    from backend.app.services.tools.meeting_planner import tool_plan as tool_plan_module

    def result_for_tool(tool_name):
        if tool_name.endswith("bfc_build_opportunity_sprint"):
            return {
                "objects": {
                    "opportunity_brief": {"opportunity_brief_id": "brief-1"},
                    "practice_sprint": {"practice_sprint_id": "sprint-1"},
                    "delivery_rubric": {"delivery_rubric_id": "rubric-1"},
                }
            }
        if tool_name.endswith("bfc_review_artifact_attempt"):
            return {
                "objects": {
                    "artifact_attempt": {"artifact_attempt_id": "artifact-attempt-1"},
                    "artifact_qa_report": {
                        "artifact_qa_report_id": "artifact-qa-1"
                    },
                }
            }
        if tool_name.endswith("bfc_draft_application_package"):
            return {
                "objects": {
                    "proposal_draft": {"proposal_draft_id": "proposal-1"},
                    "application_attempt": {
                        "application_attempt_id": "application-attempt-1"
                    },
                    "portfolio_case": {"portfolio_case_id": "portfolio-1"},
                }
            }
        return {}

    calls = install_fake_executor(monkeypatch, tool_plan_module, result_for_tool)

    tool = tool_plan_module.ExecutePlannerToolPlanTool()
    result = await tool.execute(
        planner_tool_plan=build_legacy_binding_plan().as_execution_payload()
    )

    assert result["status"] == "success"
    assert len(calls) == 3
    _, review_args = calls[1]
    assert review_args["practice_sprint_id"] == "sprint-1"
    assert review_args["opportunity_brief_id"] == "brief-1"
    assert review_args["delivery_rubric_id"] == "rubric-1"
    _, draft_args = calls[2]
    assert draft_args["opportunity_brief_id"] == "brief-1"
    assert draft_args["artifact_attempt_id"] == "artifact-attempt-1"
    assert draft_args["artifact_qa_report_id"] == "artifact-qa-1"
