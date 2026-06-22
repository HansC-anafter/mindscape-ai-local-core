from backend.app.services.orchestration.meeting.planner_contract_execution.manifest_registry import (
    PlannerContractManifestRegistry,
)
from backend.app.services.orchestration.meeting.planner_contract_execution.tool_plan_models import (
    PlannerToolPlan,
    PlannerToolPlanCategory,
    PlannerToolPlanStep,
)
from backend.app.services.orchestration.meeting.role_profiles.resolver import (
    SelectedMeetingRoleProfile,
)


def planner_tool(code, resource_kind, effect, execution_hints):
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
            planner_tool(
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
            planner_tool(
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
            planner_tool(
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
            planner_tool(
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


def fixture_planner_tool(code, resource_kind, effect, *, idempotency="idempotency_key"):
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
            fixture_planner_tool(
                "fixture_create_practice_sprint",
                "practice_sprint",
                "write",
                idempotency=self.idempotency,
            ),
            fixture_planner_tool(
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


class FakeExecutionResult:
    def __init__(self, result):
        self.success = True
        self.result = result
        self.error = None


def install_fake_executor(monkeypatch, tool_plan_module, result_for_tool):
    calls = []

    class FakeUnifiedToolExecutor:
        async def execute_tool(self, tool_name, arguments):
            calls.append((tool_name, arguments))
            return FakeExecutionResult(result_for_tool(tool_name))

    monkeypatch.setattr(
        tool_plan_module,
        "UnifiedToolExecutor",
        lambda: FakeUnifiedToolExecutor(),
    )
    return calls


def build_legacy_binding_plan():
    return PlannerToolPlan(
        plan_id="legacy-binding-plan",
        workspace_id="ws_legacy",
        meeting_id="mtg_legacy",
        pack_id="blender_freelance_coach",
        categories=[
            PlannerToolPlanCategory(
                category_id="active_opportunity",
                label="Active opportunity",
                description="",
                idempotency_key="idemp-1",
            )
        ],
        steps=[
            PlannerToolPlanStep(
                step_id="build_opportunity_sprint_active_opportunity",
                role="build_opportunity_sprint",
                category_id="active_opportunity",
                category_label="Active opportunity",
                tool_name="blender_freelance_coach.bfc_build_opportunity_sprint",
                resource_kind="practice_sprint",
                effect="write",
                arguments={},
                input_bindings={},
                result_selectors={
                    "opportunity_brief_id": "$.objects.opportunity_brief.opportunity_brief_id",
                    "practice_sprint_id": "$.objects.practice_sprint.practice_sprint_id",
                    "delivery_rubric_id": "$.objects.delivery_rubric.delivery_rubric_id",
                },
                depends_on=[],
            ),
            PlannerToolPlanStep(
                step_id="review_artifact_attempt_active_opportunity",
                role="review_artifact_attempt",
                category_id="active_opportunity",
                category_label="Active opportunity",
                tool_name="blender_freelance_coach.bfc_review_artifact_attempt",
                resource_kind="artifact_qa_report",
                effect="write",
                arguments={"artifact_summary": "summary"},
                input_bindings={
                    "practice_sprint_id": "$steps.build_opportunity_sprint.result.practice_sprint_id",
                    "opportunity_brief_id": "$steps.build_opportunity_sprint.result.opportunity_brief_id",
                    "delivery_rubric_id": "$steps.build_opportunity_sprint.result.delivery_rubric_id",
                },
                result_selectors={
                    "artifact_attempt_id": "$.objects.artifact_attempt.artifact_attempt_id",
                    "artifact_qa_report_id": "$.objects.artifact_qa_report.artifact_qa_report_id",
                },
                depends_on=["build_opportunity_sprint_active_opportunity"],
            ),
            PlannerToolPlanStep(
                step_id="draft_application_package_active_opportunity",
                role="draft_application_package",
                category_id="active_opportunity",
                category_label="Active opportunity",
                tool_name="blender_freelance_coach.bfc_draft_application_package",
                resource_kind="proposal_draft",
                effect="write",
                arguments={"title": "Active opportunity"},
                input_bindings={
                    "opportunity_brief_id": "$steps.build_opportunity_sprint.result.opportunity_brief_id",
                    "artifact_attempt_id": "$steps.review_artifact_attempt.result.artifact_attempt_id",
                    "artifact_qa_report_id": "$steps.review_artifact_attempt.result.artifact_qa_report_id",
                },
                result_selectors={
                    "portfolio_case_id": "$.objects.portfolio_case.portfolio_case_id",
                },
                depends_on=[
                    "build_opportunity_sprint_active_opportunity",
                    "review_artifact_attempt_active_opportunity",
                ],
            ),
        ],
    )


def bfc_session_metadata():
    return {
        "active_capability_code": "blender_freelance_coach",
        "meeting_role_profile_code": "bfc_practice_delivery",
        "playbook_code": "bfc_daily_guided_practice",
        "context": {
            "primary": {
                "title": "Blender Practice Scenario",
                "brief_text": "Create a stylized still life in Blender.",
                "source_channel_kind": "manual_note",
                "commerciality": "commercial",
                "source_terms_risk": "low",
                "required_skills": ["modeling", "texturing"],
                "deliverable_types": ["portfolio_render"],
                "budget_summary": "N/A",
                "deadline_summary": "2 days",
                "duration_days": 7,
                "goal": "Produce a client-ready portfolio render",
                "acceptance_criteria": ["Topology count <= 30k"],
                "artifact_summary": "Initial test viewport pass",
                "change_summary": "N/A",
                "findings": ["geometry alignment"],
                "next_fix_tasks": ["Bake normals"],
                "qa_score": 0.8,
                "public_summary": "Stylized still life",
                "pitch_text": "Manual practice piece.",
                "delivery_plan": ["model", "texture", "lighting"],
            }
        },
    }
