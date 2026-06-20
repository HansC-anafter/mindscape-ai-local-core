from pathlib import Path

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


def _planner_tool(
    code,
    resource_kind,
    effect,
    *,
    idempotency="idempotency_key",
    execution_hints=None,
    polling=False,
):
    hints = dict(execution_hints or {})
    if polling:
        hints["polling_interval_ms"] = 1000
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
            "execution_hints": hints,
        },
        "execution_hints": hints,
        "manifest_path": "/tmp/fixture_pack/manifest.yaml",
    }


class GuardrailRegistry(PlannerContractManifestRegistry):
    def __init__(self, *, idempotency="idempotency_key", polling=False):
        self.idempotency = idempotency
        self.polling = polling

    @staticmethod
    def active_pack_id(session_metadata):
        return "fixture_pack"

    def load_planner_tools_for_pack(self, pack_id):
        assert pack_id == "fixture_pack"
        return [
            _planner_tool(
                "fixture_create_practice_sprint",
                "practice_sprint",
                "write",
                idempotency=self.idempotency,
                polling=self.polling,
                execution_hints={
                    "result_selectors": {"object_id": "$.object.id"},
                    "max_selector_fanout": 50,
                },
            ),
            _planner_tool(
                "fixture_review_artifact",
                "artifact_review",
                "write",
                execution_hints={
                    "input_bindings": {
                        "practice_sprint_id": (
                            "$steps.create_practice_sprint.result.object_id"
                        ),
                    },
                    "result_selectors": {"object_id": "$.object.id"},
                    "max_selector_fanout": 50,
                },
            ),
        ]


class GuardrailRoleProfileResolver:
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
                        "category_id": "active",
                        "label": "Active opportunity",
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
                        },
                    },
                    {
                        "step_code": "review_artifact",
                        "resource_kind": "artifact_review",
                        "effect": "write",
                        "depends_on": ["create_practice_sprint"],
                        "slot": "executor",
                    },
                ],
            },
            manifest_path="/tmp/fixture_pack/manifest.yaml",
            selection_context={"context": {"primary": {"title": "Active opportunity"}}},
        )


def _enable_declarative_lane(monkeypatch):
    monkeypatch.setenv("MEETING_ROLE_PROFILES_ENABLED", "true")
    monkeypatch.setenv("DECLARATIVE_PLANNER_LANE_ENABLED", "true")
    monkeypatch.delenv("MEETING_ROLE_PROFILES_ENABLED_PACK_CODES", raising=False)


def test_legacy_import_path_exposes_planner_tool_plan_compiler():
    assert PlannerToolPlanCompiler.__module__.endswith(".tool_plan_compiler")


def test_declarative_lane_rejects_polling_hints(monkeypatch):
    _enable_declarative_lane(monkeypatch)

    with pytest.raises(ValueError, match="must not declare polling"):
        PlannerToolPlanCompiler(
            GuardrailRegistry(polling=True),
            GuardrailRoleProfileResolver(),
        ).compile(
            request_contract={"source_message": "fixture practice"},
            session_metadata={"active_capability_code": "fixture_pack"},
            workspace_id="ws_demo",
            meeting_id="mtg_demo",
        )


def test_declarative_lane_rejects_mutating_step_without_idempotency(monkeypatch):
    _enable_declarative_lane(monkeypatch)

    with pytest.raises(ValueError, match="needs idempotency"):
        PlannerToolPlanCompiler(
            GuardrailRegistry(idempotency="none"),
            GuardrailRoleProfileResolver(),
        ).compile(
            request_contract={"source_message": "fixture practice"},
            session_metadata={"active_capability_code": "fixture_pack"},
            workspace_id="ws_demo",
            meeting_id="mtg_demo",
        )


def test_declarative_lane_scopes_role_bindings_to_step_ids(monkeypatch):
    _enable_declarative_lane(monkeypatch)

    plan = PlannerToolPlanCompiler(
        GuardrailRegistry(),
        GuardrailRoleProfileResolver(),
    ).compile(
        request_contract={"source_message": "fixture practice"},
        session_metadata={"active_capability_code": "fixture_pack"},
        workspace_id="ws_demo",
        meeting_id="mtg_demo",
    )

    assert plan is not None
    review_step = next(step for step in plan.steps if step.role == "review_artifact")
    assert review_step.depends_on == ["create_practice_sprint_active"]
    assert review_step.input_bindings["practice_sprint_id"] == (
        "$steps.create_practice_sprint_active.result.object_id"
    )


def test_helper_modules_do_not_define_new_resource_paths():
    repo_root = Path(__file__).resolve().parents[4]
    source_paths = [
        "backend/app/services/orchestration/meeting/planner_contract_execution/tool_plan_compiler.py",
        "backend/app/services/orchestration/meeting/planner_contract_execution/tool_plan_compiler_common.py",
        "backend/app/services/orchestration/meeting/planner_contract_execution/tool_plan_declarative_lane.py",
        "backend/app/services/orchestration/meeting/planner_contract_execution/tool_plan_creative_space_lane.py",
    ]
    helper_paths = source_paths[1:]
    disallowed_markers = [
        "APIRouter",
        "router =",
        "@router",
        "create_engine",
        "sessionmaker",
        "psycopg2",
        "PgBouncer",
        "subprocess",
        "httpx",
        "requests",
        "setInterval",
        "asyncio.create_task",
        "Thread(",
        "Process(",
    ]

    for relative_path in source_paths:
        text = (repo_root / relative_path).read_text(encoding="utf-8")
        for marker in disallowed_markers:
            assert marker not in text

    for relative_path in helper_paths:
        text = (repo_root / relative_path).read_text(encoding="utf-8")
        assert "class PlannerToolPlanCompiler" not in text
