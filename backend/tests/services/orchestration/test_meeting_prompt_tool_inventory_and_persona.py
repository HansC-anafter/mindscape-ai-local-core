from pathlib import Path
from unittest.mock import MagicMock, patch

from meeting_prompt_injection_test_support import StubEngine


class TestToolInventoryCanonicalIds:
    """Fallback tool inventory should surface canonical pack-prefixed IDs."""

    def test_manifest_fallback_uses_pack_prefixed_tool_id(self, monkeypatch):
        engine = StubEngine()
        repo_root = Path(__file__).resolve().parents[4]
        monkeypatch.setenv("APP_DIR", str(repo_root))

        fake_binding_store = MagicMock()
        fake_binding_store.list_bindings_by_workspace.return_value = []

        fake_packs_store = MagicMock()
        fake_packs_store.list_enabled_pack_ids.return_value = ["ig"]

        with patch(
            "backend.app.services.stores.workspace_resource_binding_store.WorkspaceResourceBindingStore",
            return_value=fake_binding_store,
        ), patch(
            "backend.app.services.stores.installed_packs_store.InstalledPacksStore",
            return_value=fake_packs_store,
        ):
            block = engine._build_tool_inventory_block()

        assert "- ig.ig_capture_account_snapshot:" in block
        assert "- ig.ig_fetch_posts:" in block
        assert "- ig_capture_account_snapshot:" not in block


class TestPersonaInjection:
    """Tests for _assemble_system_message persona block."""

    def test_includes_critical_rules(self):
        engine = StubEngine()
        from backend.app.models.playbook import AgentDefinition

        role_def = AgentDefinition(
            agent_id="critic",
            agent_name="Critic",
            role="critic",
            system_prompt="You identify risks.",
            critical_rules=["NEVER approve without concerns."],
        )
        result = engine._assemble_system_message(role_def)
        assert "NEVER approve without concerns" in result
        assert "Critical rules" in result

    def test_includes_responsibility_boundary(self):
        engine = StubEngine()
        from backend.app.models.playbook import AgentDefinition

        role_def = AgentDefinition(
            agent_id="exec",
            agent_name="Executor",
            role="executor",
            system_prompt="You convert decisions.",
            responsibility_boundary="execution_only",
        )
        result = engine._assemble_system_message(role_def)
        assert "execution_only" in result
        assert "Stay strictly within" in result

    def test_minimal_role_no_extras(self):
        engine = StubEngine()
        from backend.app.models.playbook import AgentDefinition

        role_def = AgentDefinition(
            agent_id="test",
            agent_name="Test",
            system_prompt="Basic prompt.",
        )
        result = engine._assemble_system_message(role_def)
        assert result == "Basic prompt."

    def test_full_persona_block_assembly(self):
        engine = StubEngine()
        from backend.app.models.playbook import AgentDefinition

        role_def = AgentDefinition(
            agent_id="planner",
            agent_name="Planner",
            role="planner",
            system_prompt="You propose plans.",
            responsibility_boundary="proposal_and_planning",
            critical_rules=["Rule 1", "Rule 2"],
            communication_style="Structured planner.",
            success_metrics=["Metric A"],
        )
        result = engine._assemble_system_message(role_def)
        assert "You propose plans." in result
        assert "proposal_and_planning" in result
        assert "Rule 1" in result
        assert "Rule 2" in result
        assert "Structured planner." in result
        assert "Metric A" in result
