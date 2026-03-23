import os
import sys
from types import SimpleNamespace

import pytest

repo_root = os.path.join(os.path.dirname(__file__), "..", "..")
backend_root = os.path.join(repo_root, "backend")
sys.path.insert(0, repo_root)
sys.path.insert(0, backend_root)

from backend.app.services.conversation import plan_builder as plan_builder_module
from backend.app.services.conversation.plan_builder_core import (
    pack_policy,
    rule_based,
    runtime,
)
from backend.app.models.workspace import SideEffectLevel


class _FakeRegistry:
    def __init__(self, capabilities=None, playbooks=None):
        self.capabilities = capabilities or {}
        self._playbooks = playbooks or {}

    def list_capabilities(self):
        return list(self.capabilities.keys())

    def get_capability(self, capability_code):
        return self.capabilities.get(capability_code)

    def get_capability_playbooks(self, capability_code):
        return self._playbooks.get(capability_code, [])


def test_pack_policy_prefers_installed_metadata(monkeypatch):
    class _Store:
        def get_pack(self, pack_id):
            assert pack_id == "content_drafting"
            return {"metadata": {"side_effect_level": "soft_write"}}

    monkeypatch.setattr(pack_policy, "InstalledPacksStore", lambda: _Store())
    monkeypatch.setattr(
        pack_policy,
        "get_registry",
        lambda: _FakeRegistry({"content_drafting": {"manifest": {}}}),
    )

    assert (
        pack_policy.determine_side_effect_level("content_drafting")
        == SideEffectLevel.SOFT_WRITE
    )


def test_pack_policy_can_resolve_pack_from_playbook_scan(monkeypatch):
    registry = _FakeRegistry(
        capabilities={"ig": {"manifest": {}}, "writing": {"manifest": {}}},
        playbooks={"writing": ["article_draft.yaml"]},
    )
    monkeypatch.setattr(pack_policy, "get_registry", lambda: registry)

    assert pack_policy.get_pack_id_from_playbook_code("article_draft") == "writing"
    assert pack_policy.get_pack_id_from_playbook_code("ig.ig_complete_workflow") == "ig"


def test_rule_based_builder_creates_expected_tasks():
    class _Builder:
        def is_pack_available(self, pack_id):
            return True

        def check_pack_tools_configured(self, pack_id):
            return True

        def determine_side_effect_level(self, pack_id):
            levels = {
                "semantic_seeds": SideEffectLevel.READONLY,
                "daily_planning": SideEffectLevel.SOFT_WRITE,
                "content_drafting": SideEffectLevel.EXTERNAL_WRITE,
            }
            return levels[pack_id]

    plans = rule_based.build_rule_based_task_plans(
        builder=_Builder(),
        message="請幫我摘要這份內容並做 task plan",
        files=["file-1"],
    )

    assert [plan.pack_id for plan in plans] == [
        "semantic_seeds",
        "daily_planning",
        "content_drafting",
    ]
    assert plans[0].auto_execute is True
    assert plans[1].requires_cta is True
    assert plans[2].task_type == "generate_summary"


@pytest.mark.asyncio
async def test_runtime_finalize_execution_plan_attaches_metadata(monkeypatch):
    called = {}

    async def fake_create_or_link_phase(
        builder,
        execution_plan,
        project_id,
        message_id,
        project_assignment_decision=None,
    ):
        called["project_id"] = project_id
        called["message_id"] = message_id

    monkeypatch.setattr(runtime, "create_or_link_phase", fake_create_or_link_phase)

    execution_plan = SimpleNamespace(
        id="plan-1",
        message_id="msg-1",
        workspace_id="ws-1",
    )
    builder = SimpleNamespace()
    result = await runtime.finalize_execution_plan(
        builder,
        execution_plan=execution_plan,
        project_id="project-1",
        message_id="msg-1",
        project_assignment_decision={"relation": "same_project"},
        playbooks_to_use=[{"playbook_code": "article_draft"}],
    )

    assert result is execution_plan
    assert execution_plan._metadata["effective_playbooks_count"] == 1
    assert called == {"project_id": "project-1", "message_id": "msg-1"}


def test_runtime_model_selection_short_circuits_on_direct_model():
    builder = SimpleNamespace(model_name="gpt-5.4", stage_router=None, capability_profile=None)
    assert runtime.select_model_for_plan(builder) == "gpt-5.4"


def test_plan_builder_facade_delegates_to_extracted_helpers(monkeypatch):
    builder = object.__new__(plan_builder_module.PlanBuilder)

    monkeypatch.setattr(
        plan_builder_module,
        "is_pack_available_helper",
        lambda pack_id: pack_id == "artifact_pack",
    )
    monkeypatch.setattr(
        plan_builder_module,
        "get_pack_id_from_playbook_code_helper",
        lambda playbook_code: f"resolved:{playbook_code}",
    )
    monkeypatch.setattr(
        plan_builder_module,
        "select_model_for_plan_helper",
        lambda _builder, risk_level="read", profile_id=None: f"{risk_level}:{profile_id}",
    )

    assert builder.is_pack_available("artifact_pack") is True
    assert builder._get_pack_id_from_playbook_code("article_draft") == "resolved:article_draft"
    assert builder._select_model_for_plan("write", "user-1") == "write:user-1"
