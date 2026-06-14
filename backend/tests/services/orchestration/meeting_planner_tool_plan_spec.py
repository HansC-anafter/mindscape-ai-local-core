import pytest

from backend.app.services.orchestration.meeting.planner_contract_execution.manifest_registry import (
    PlannerContractManifestRegistry,
)
from backend.app.services.orchestration.meeting.planner_contract_execution.tool_plan_compiler import (
    PlannerToolPlanCompiler,
)
from backend.app.services.orchestration.meeting.role_profiles.resolver import (
    SelectedMeetingRoleProfile,
)


def _planner_tool(code, resource_kind, effect, execution_hints):
    return {
        "pack_id": "ig",
        "tool_code": code,
        "canonical_tool_name": f"ig.{code}",
        "planner_contract": {
            "exposed": True,
            "resource_kind": resource_kind,
            "effect": effect,
            "workspace_scoped": True,
            "idempotency": "none" if effect == "read" else "idempotency_key",
            "audit_fields": ["workspace_id"],
            "execution_hints": execution_hints,
        },
        "execution_hints": execution_hints,
        "manifest_path": "/tmp/ig/manifest.yaml",
    }


class FakeRegistry(PlannerContractManifestRegistry):
    @staticmethod
    def active_pack_id(session_metadata):
        return "ig"

    def load_planner_tools_for_pack(self, pack_id):
        assert pack_id == "ig"
        return [
            _planner_tool(
                "ig_list_seeds",
                "seed",
                "read",
                {
                    "result_selectors": {
                        "seed_handles": "$.seeds[*].handle",
                        "seed_object_uris": "$.seeds[*].object_uri",
                    },
                    "input_bindings": {"query": "$category.label"},
                    "max_selector_fanout": 500,
                },
            ),
            _planner_tool(
                "ig_query_references",
                "reference",
                "read",
                {
                    "result_selectors": {
                        "reference_ids": "$.references[*].reference_id",
                        "object_uris": "$.references[*].object_uri",
                    },
                    "input_bindings": {"query": "$category.label"},
                    "max_selector_fanout": 200,
                },
            ),
            _planner_tool(
                "ig_create_creative_space",
                "creative_space",
                "write",
                {
                    "result_selectors": {
                        "creative_space_id": "$.creative_space.id",
                    },
                    "input_bindings": {
                        "title": "$category.label",
                        "description": "$category.description",
                        "idempotency_key": "$category.idempotency_key",
                    },
                    "max_selector_fanout": 1,
                },
            ),
            _planner_tool(
                "ig_add_creative_space_members",
                "creative_space_member",
                "write",
                {
                    "result_selectors": {
                        "added_count": "$.added_count",
                    },
                    "input_bindings": {
                        "creative_space_id": "$steps.create_space.result.creative_space_id",
                        "reference_ids": "$steps.query_references.result.reference_ids",
                        "object_uris": [
                            "$steps.list_seeds.result.seed_object_uris",
                            "$steps.query_references.result.object_uris",
                        ],
                    },
                    "max_selector_fanout": 500,
                },
            ),
        ]


def _fixture_planner_tool(code, resource_kind, effect, *, idempotency="idempotency_key"):
    return {
        "pack_id": "fixture_pack",
        "tool_code": code,
        "canonical_tool_name": f"fixture_pack.{code}",
        "planner_contract": {
            "exposed": True,
            "resource_kind": resource_kind,
            "effect": effect,
            "workspace_scoped": True,
            "idempotency": "none" if effect == "read" else idempotency,
            "audit_fields": ["workspace_id"],
            "execution_hints": {
                "result_selectors": {"object_id": "$.object.id"},
                "max_selector_fanout": 50,
            },
        },
        "execution_hints": {
            "result_selectors": {"object_id": "$.object.id"},
            "max_selector_fanout": 50,
        },
        "manifest_path": "/tmp/fixture_pack/manifest.yaml",
    }


class DeclarativeRegistry(PlannerContractManifestRegistry):
    @staticmethod
    def active_pack_id(session_metadata):
        return "fixture_pack"

    def __init__(self, *, idempotency="idempotency_key"):
        self.idempotency = idempotency

    def load_planner_tools_for_pack(self, pack_id):
        assert pack_id == "fixture_pack"
        return [
            _fixture_planner_tool(
                "fixture_create_practice_sprint",
                "practice_sprint",
                "write",
                idempotency=self.idempotency,
            ),
            _fixture_planner_tool(
                "fixture_update_learning_ledger",
                "learning_ledger",
                "write",
                idempotency=self.idempotency,
            ),
        ]


class DeclarativeRoleProfileResolver:
    def resolve(self, *, session_metadata=None, request_contract=None):
        return SelectedMeetingRoleProfile(
            pack_id="fixture_pack",
            code="fixture_practice_plan",
            display_name="Fixture Practice Planning",
            match={
                "playbook_codes": ["fixture_daily_guided_practice"],
                "expected_outputs": ["practice_sprint"],
                "context_object_kinds": ["fixture_opportunity"],
            },
            slot_overrides={
                "planner": {"pack_role_name": "fixture_mentor"},
                "executor": {"pack_role_name": "fixture_dispatcher"},
            },
            planner_lane={
                "code": "fixture_practice_lane",
                "categories": [
                    {
                        "category_id": "active_opportunity",
                        "label_selector": "$context.primary.title",
                    }
                ],
                "steps": [
                    {
                        "step_code": "create_practice_sprint",
                        "resource_kind": "practice_sprint",
                        "effect": "write",
                        "slot": "planner",
                        "arguments": {
                            "title": "$category.label",
                            "brief_text": "$context.primary.brief_text",
                            "source_channel_kind": "$context.primary.source_channel_kind",
                            "required_skills": "$context.primary.required_skills",
                            "duration_days": "$context.primary.duration_days",
                            "score": "$context.primary.score",
                            "metadata": {
                                "source": "$context.primary.source_url",
                            },
                        },
                    },
                    {
                        "step_code": "update_learning_ledger",
                        "resource_kind": "learning_ledger",
                        "effect": "write",
                        "depends_on": ["create_practice_sprint"],
                        "slot": "executor",
                    },
                ],
            },
            manifest_path="/tmp/fixture_pack/manifest.yaml",
            selection_context={
                "context": {
                    "primary": {
                        "title": "Product render",
                        "brief_text": "Create one bounded product render.",
                        "source_channel_kind": "manual_note",
                        "source_url": "mindscape://fixture/opportunity/1",
                        "required_skills": ["lighting", "materials"],
                        "duration_days": 5,
                        "score": 0.74,
                    }
                }
            },
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


@pytest.mark.asyncio
async def test_execute_planner_tool_plan_merges_seed_and_reference_members(monkeypatch):
    from backend.app.services.tools.meeting_planner import tool_plan as tool_plan_module

    calls = []

    class FakeExecutionResult:
        def __init__(self, result):
            self.success = True
            self.result = result
            self.error = None

    class FakeUnifiedToolExecutor:
        async def execute_tool(self, tool_name, arguments):
            calls.append((tool_name, arguments))
            if tool_name.endswith("ig_list_seeds"):
                return FakeExecutionResult(
                    {
                        "seeds": [
                            {
                                "handle": "yoga_studio",
                                "object_uri": "mindscape://ig/seed/yoga_studio",
                            }
                        ]
                    }
                )
            if tool_name.endswith("ig_query_references"):
                return FakeExecutionResult(
                    {
                        "references": [
                            {
                                "reference_id": "ref_yoga",
                                "object_uri": "mindscape://ig/reference/ref_yoga",
                            }
                        ]
                    }
                )
            if tool_name.endswith("ig_create_creative_space"):
                return FakeExecutionResult(
                    {"creative_space": {"id": "space_yoga", "title": "瑜伽"}}
                )
            return FakeExecutionResult({"added_count": 2, "members": []})

    monkeypatch.setattr(
        tool_plan_module,
        "UnifiedToolExecutor",
        lambda: FakeUnifiedToolExecutor(),
    )
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
