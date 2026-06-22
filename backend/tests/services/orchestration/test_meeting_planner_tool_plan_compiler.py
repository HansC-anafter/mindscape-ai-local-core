import pytest

from backend.app.services.orchestration.meeting.planner_contract_execution.tool_plan_compiler import (
    PlannerToolPlanCompiler,
)

from backend.tests.services.orchestration.meeting_planner_tool_plan_test_support import (
    DeclarativeRegistry,
    DeclarativeRoleProfileResolver,
    FakeRegistry,
    bfc_session_metadata,
)


def test_planner_tool_plan_compiler_builds_ig_category_plan():
    plan = PlannerToolPlanCompiler(FakeRegistry()).compile(
        request_contract={
            "source_message": (
                "幫我把所有當前跟瑜伽、健身、舞蹈的 seed / refs 分門別類，"
                "各新增一個 creative space"
            )
        },
        session_metadata={"active_capability_code": "ig"},
        workspace_id="ws_demo",
        meeting_id="mtg_demo",
    )

    assert plan is not None
    assert [category.label for category in plan.categories] == ["瑜伽", "健身", "舞蹈"]
    assert len(plan.steps) == 12
    first_add_members = next(
        step
        for step in plan.steps
        if step.role == "add_members" and step.category_label == "瑜伽"
    )
    assert first_add_members.tool_name == "ig.ig_add_creative_space_members"
    assert first_add_members.input_bindings["creative_space_id"].startswith(
        "$steps.create_space_cat_"
    )
    assert first_add_members.input_bindings["reference_ids"].startswith(
        "$steps.query_references_cat_"
    )
    assert first_add_members.input_bindings["object_uris"][0].startswith(
        "$steps.list_seeds_cat_"
    )


def test_declarative_planner_lane_compiler_builds_fixture_role_profile_plan(
    monkeypatch,
):
    monkeypatch.setenv("MEETING_ROLE_PROFILES_ENABLED", "true")
    monkeypatch.setenv("DECLARATIVE_PLANNER_LANE_ENABLED", "true")

    plan = PlannerToolPlanCompiler(
        DeclarativeRegistry(),
        DeclarativeRoleProfileResolver(),
    ).compile(
        request_contract={"source_message": "fixture practice"},
        session_metadata={
            "active_capability_code": "fixture_pack",
            "trace_id": "trace-fixture-role-profile",
            "resource_budget_class": "interactive",
        },
        workspace_id="ws_demo",
        meeting_id="mtg_demo",
    )

    assert plan is not None
    assert plan.metadata["source"] == "meeting_role_profile_planner_lane"
    assert plan.metadata["meeting_role_profile_code"] == "fixture_practice_plan"
    assert plan.metadata["meeting_lane_code"] == "fixture_practice_lane"
    assert [category.label for category in plan.categories] == ["Product render"]
    assert [step.role for step in plan.steps] == [
        "create_practice_sprint",
        "update_learning_ledger",
    ]
    assert plan.steps[0].tool_name == "fixture_pack.fixture_create_practice_sprint"
    assert plan.steps[0].arguments["title"] == "Product render"
    assert plan.steps[0].arguments["brief_text"] == "Create one bounded product render."
    assert plan.steps[0].arguments["required_skills"] == ["lighting", "materials"]
    assert plan.steps[0].arguments["duration_days"] == 5
    assert plan.steps[0].arguments["score"] == 0.74
    assert plan.steps[0].arguments["metadata"]["source"] == (
        "mindscape://fixture/opportunity/1"
    )
    assert plan.steps[0].pack_role_name == "fixture_mentor"
    assert plan.steps[0].trace_id == "trace-fixture-role-profile"
    assert plan.steps[1].depends_on == ["create_practice_sprint_active_opportunity"]
    assert (
        plan.steps[1].arguments["metadata"]["planner_contract"][
            "meeting_role_profile_code"
        ]
        == "fixture_practice_plan"
    )


def test_declarative_planner_lane_rejects_mutating_step_without_idempotency(
    monkeypatch,
):
    monkeypatch.setenv("MEETING_ROLE_PROFILES_ENABLED", "true")
    monkeypatch.setenv("DECLARATIVE_PLANNER_LANE_ENABLED", "true")

    with pytest.raises(ValueError, match="needs idempotency"):
        PlannerToolPlanCompiler(
            DeclarativeRegistry(idempotency="none"),
            DeclarativeRoleProfileResolver(),
        ).compile(
            request_contract={"source_message": "fixture practice"},
            session_metadata={"active_capability_code": "fixture_pack"},
            workspace_id="ws_demo",
            meeting_id="mtg_demo",
        )


def test_compile_bfc_declarative_plan_step_bindings_use_step_id(monkeypatch):
    monkeypatch.setenv("MEETING_ROLE_PROFILES_ENABLED", "true")
    monkeypatch.setenv("DECLARATIVE_PLANNER_LANE_ENABLED", "true")
    monkeypatch.setenv(
        "MEETING_ROLE_PROFILES_ENABLED_PACK_CODES",
        "blender_freelance_coach",
    )

    plan = PlannerToolPlanCompiler().compile(
        request_contract={"source_message": "practice delivery"},
        session_metadata=bfc_session_metadata(),
        workspace_id="ws_demo_bfc",
        meeting_id="mtg_demo_bfc",
    )

    assert plan is not None
    assert [step.role for step in plan.steps] == [
        "build_opportunity_sprint",
        "review_artifact_attempt",
        "draft_application_package",
    ]

    for step in plan.steps:
        for binding in step.input_bindings.values():
            if isinstance(binding, str):
                assert binding.startswith("$steps.")
                assert not binding.startswith("$steps.build_opportunity_sprint.")
                assert not binding.startswith("$steps.review_artifact_attempt.")
            elif isinstance(binding, list):
                for item in binding:
                    assert isinstance(item, str)
                    assert item.startswith("$steps.")
                    assert not item.startswith("$steps.build_opportunity_sprint.")
                    assert not item.startswith("$steps.review_artifact_attempt.")
