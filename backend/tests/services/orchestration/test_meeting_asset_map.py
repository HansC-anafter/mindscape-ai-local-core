"""
Unit tests for workspace asset map context injection into meeting prompts.

Tests _build_asset_map_context() and its injection into _build_turn_prompt
as the === Workspace Asset Map === block.
"""

import pytest
from unittest.mock import MagicMock, patch

from backend.app.services.orchestration.meeting._prompts import MeetingPromptsMixin


class StubEngine(MeetingPromptsMixin):
    """Minimal stub mimicking MeetingEngine attributes used by prompts mixin."""

    def __init__(self):
        self.session = MagicMock()
        self.session.id = "sess-001"
        self.session.workspace_id = "ws-dispatch"
        self.session.agenda = ["Plan cross-workspace task"]
        self.session.success_criteria = []
        self.session.lens_id = None
        self.session.max_rounds = 5
        self.workspace = MagicMock()
        self.workspace.id = "ws-dispatch"
        self.workspace.group_id = None
        self.workspace.workspace_role = None
        self.project_id = "proj-001"
        self.profile_id = "user-001"
        self.store = MagicMock()
        self.session_store = MagicMock()
        self._effective_lens = None
        self._active_intent_ids = []
        self._lens_hash = None
        self._events = []
        self._turn_history = []
        self._project_context = None
        self._asset_map_context = None
        self._locale = "en"


class TestBuildAssetMapContext:
    """Tests for _build_asset_map_context method."""

    def test_returns_empty_when_no_workspace(self):
        engine = StubEngine()
        engine.workspace = None
        assert engine._build_asset_map_context() == ""

    @patch(
        "backend.app.services.stores.postgres.workspaces_store"
        ".PostgresWorkspacesStore"
    )
    @patch(
        "backend.app.services.stores.workspace_resource_binding_store"
        ".WorkspaceResourceBindingStore"
    )
    def test_returns_empty_when_no_group_and_no_discoverable(
        self, mock_binding_cls, mock_ws_cls
    ):
        """No group_id and no discoverable workspaces -> empty string."""
        engine = StubEngine()
        engine.workspace.group_id = None
        mock_ws_cls.return_value.list_discoverable_workspaces.return_value = []
        assert engine._build_asset_map_context() == ""

    def test_discoverable_runs_without_group_id(self):
        """5D-3: Discoverable workspaces found even when group_id is None."""
        engine = StubEngine()
        engine.workspace.group_id = None
        engine.workspace.id = "ws-dispatch"

        disco_ws = MagicMock()
        disco_ws.id = "ws-shared-db"
        disco_ws.title = "Shared Database"

        disco_binding = MagicMock()
        disco_binding.resource_id = "shared-pg"
        disco_binding.overrides = {
            "display_name": "Shared PostgreSQL",
            "asset_type": "database",
        }

        with patch(
            "backend.app.services.stores.postgres.workspaces_store"
            ".PostgresWorkspacesStore"
        ) as ws_cls, patch(
            "backend.app.services.stores.workspace_resource_binding_store"
            ".WorkspaceResourceBindingStore"
        ) as bs_cls:
            ws_cls.return_value.list_discoverable_workspaces.return_value = [disco_ws]

            def list_bindings(ws_id, resource_type=None):
                if ws_id == "ws-shared-db":
                    return [disco_binding]
                return []

            bs_cls.return_value.list_bindings_by_workspace.side_effect = list_bindings

            result = engine._build_asset_map_context()

        # No group header (no group_id)
        assert "Workspace Group:" not in result
        # But discoverable workspace IS present
        assert "Discoverable Workspaces (outside group):" in result
        assert "ws-shared-db" in result
        assert "Shared Database" in result
        assert "Shared PostgreSQL" in result
        assert "[discoverable]" in result

    @patch(
        "backend.app.services.stores.postgres.workspace_group_store"
        ".PostgresWorkspaceGroupStore"
    )
    @patch(
        "backend.app.services.stores.workspace_resource_binding_store"
        ".WorkspaceResourceBindingStore"
    )
    def test_returns_empty_when_group_not_found(self, mock_binding_cls, mock_group_cls):
        engine = StubEngine()
        engine.workspace.group_id = "grp-001"
        mock_group_cls.return_value.get.return_value = None
        assert engine._build_asset_map_context() == ""

    def test_builds_context_with_assets(self):
        engine = StubEngine()
        engine.workspace.group_id = "grp-001"
        engine.workspace.workspace_role = "dispatch"

        # Mock workspace group
        mock_group = MagicMock()
        mock_group.id = "grp-001"
        mock_group.display_name = "My Project Group"
        mock_group.role_map = {
            "ws-dispatch": "dispatch",
            "ws-data": "cell",
        }

        with patch(
            "backend.app.services.stores.postgres.workspace_group_store"
            ".PostgresWorkspaceGroupStore"
        ) as pg_cls, patch(
            "backend.app.services.stores.workspace_resource_binding_store"
            ".WorkspaceResourceBindingStore"
        ) as bs_cls, patch(
            "backend.app.services.stores.postgres.workspaces_store"
            ".PostgresWorkspacesStore"
        ) as ws_cls:
            pg_cls.return_value.get.return_value = mock_group
            ws_cls.return_value.list_discoverable_workspaces.return_value = []

            # Mock bindings: ws-data has 2 assets, ws-dispatch has none
            binding_1 = MagicMock()
            binding_1.resource_id = "ig-followers-db"
            binding_1.overrides = {
                "display_name": "IG Followers DB",
                "asset_type": "database",
            }

            binding_2 = MagicMock()
            binding_2.resource_id = "content-library"
            binding_2.overrides = {
                "display_name": "Content Library",
                "asset_type": "storage",
            }

            def list_bindings(ws_id, resource_type=None):
                if ws_id == "ws-data":
                    return [binding_1, binding_2]
                return []

            bs_cls.return_value.list_bindings_by_workspace.side_effect = list_bindings

            result = engine._build_asset_map_context()

        assert "My Project Group" in result
        assert "dispatch" in result
        assert "ws-dispatch" in result
        assert "(current)" in result
        assert "ws-data" in result
        assert "IG Followers DB" in result
        assert "Content Library" in result
        assert "database" in result
        assert "(no assets registered)" in result

    def test_returns_empty_on_exception(self):
        engine = StubEngine()
        engine.workspace.group_id = "grp-001"
        # Importing will trigger an exception in the try block
        # since we're not patching the stores; this tests graceful degradation
        result = engine._build_asset_map_context()
        assert result == ""

    def test_empty_group_no_error(self):
        engine = StubEngine()
        engine.workspace.group_id = "grp-001"

        mock_group = MagicMock()
        mock_group.id = "grp-001"
        mock_group.display_name = "Empty Group"
        mock_group.role_map = {}

        with patch(
            "backend.app.services.stores.postgres.workspace_group_store"
            ".PostgresWorkspaceGroupStore"
        ) as pg_cls, patch(
            "backend.app.services.stores.workspace_resource_binding_store"
            ".WorkspaceResourceBindingStore"
        ) as bs_cls, patch(
            "backend.app.services.stores.postgres.workspaces_store"
            ".PostgresWorkspacesStore"
        ) as ws_cls:
            pg_cls.return_value.get.return_value = mock_group
            bs_cls.return_value.list_bindings_by_workspace.return_value = []
            ws_cls.return_value.list_discoverable_workspaces.return_value = []

            result = engine._build_asset_map_context()

        assert "Empty Group" in result
        assert result.count("(no assets registered)") == 0

    def test_discoverable_workspaces_injected(self):
        """5D-3: Discoverable workspaces outside group appear in asset map."""
        engine = StubEngine()
        engine.workspace.group_id = "grp-001"

        mock_group = MagicMock()
        mock_group.id = "grp-001"
        mock_group.display_name = "Test Group"
        mock_group.role_map = {"ws-dispatch": "dispatch"}

        # Discoverable workspace outside the group
        disco_ws = MagicMock()
        disco_ws.id = "ws-shared-db"
        disco_ws.title = "Shared Database"

        disco_binding = MagicMock()
        disco_binding.resource_id = "shared-pg"
        disco_binding.overrides = {
            "display_name": "Shared PostgreSQL",
            "asset_type": "database",
        }

        with patch(
            "backend.app.services.stores.postgres.workspace_group_store"
            ".PostgresWorkspaceGroupStore"
        ) as pg_cls, patch(
            "backend.app.services.stores.workspace_resource_binding_store"
            ".WorkspaceResourceBindingStore"
        ) as bs_cls, patch(
            "backend.app.services.stores.postgres.workspaces_store"
            ".PostgresWorkspacesStore"
        ) as ws_cls:
            pg_cls.return_value.get.return_value = mock_group
            ws_cls.return_value.list_discoverable_workspaces.return_value = [disco_ws]

            def list_bindings(ws_id, resource_type=None):
                if ws_id == "ws-shared-db":
                    return [disco_binding]
                return []

            bs_cls.return_value.list_bindings_by_workspace.side_effect = list_bindings

            result = engine._build_asset_map_context()

        assert "Discoverable Workspaces (outside group):" in result
        assert "ws-shared-db" in result
        assert "Shared Database" in result
        assert "Shared PostgreSQL" in result
        assert "[discoverable]" in result

    def test_discoverable_skips_in_group(self):
        """5D-3: Discoverable workspace already in group is NOT duplicated."""
        engine = StubEngine()
        engine.workspace.group_id = "grp-001"

        mock_group = MagicMock()
        mock_group.id = "grp-001"
        mock_group.display_name = "Test"
        mock_group.role_map = {"ws-dispatch": "dispatch", "ws-data": "cell"}

        # ws-data is both in the group AND discoverable — should NOT be duplicated
        disco_ws = MagicMock()
        disco_ws.id = "ws-data"
        disco_ws.title = "Data WS"

        with patch(
            "backend.app.services.stores.postgres.workspace_group_store"
            ".PostgresWorkspaceGroupStore"
        ) as pg_cls, patch(
            "backend.app.services.stores.workspace_resource_binding_store"
            ".WorkspaceResourceBindingStore"
        ) as bs_cls, patch(
            "backend.app.services.stores.postgres.workspaces_store"
            ".PostgresWorkspacesStore"
        ) as ws_cls:
            pg_cls.return_value.get.return_value = mock_group
            ws_cls.return_value.list_discoverable_workspaces.return_value = [disco_ws]
            bs_cls.return_value.list_bindings_by_workspace.return_value = []

            result = engine._build_asset_map_context()

        assert "Discoverable Workspaces (outside group):" not in result


class TestAssetMapPromptInjection:
    """Tests that asset map context is injected into _build_turn_prompt."""

    def test_asset_map_block_injected_when_context_exists(self):
        engine = StubEngine()
        engine._asset_map_context = (
            "Workspace Group: Test Group (grp-001)\n"
            "  [dispatch] ws-dispatch (current)\n"
            "  [cell] ws-data\n"
            "    - IG DB (database)"
        )
        prompt = engine._build_turn_prompt(
            role_id="planner",
            round_num=1,
            user_message="Plan data analysis",
            decision=None,
            planner_proposals=[],
            critic_notes=[],
        )
        assert "=== Workspace Asset Map ===" in prompt
        assert "=== End Asset Map ===" in prompt
        assert "Test Group" in prompt
        assert "target_workspace_id" in prompt

    def test_no_asset_map_block_when_empty(self):
        engine = StubEngine()
        engine._asset_map_context = ""
        prompt = engine._build_turn_prompt(
            role_id="planner",
            round_num=1,
            user_message="Plan something",
            decision=None,
            planner_proposals=[],
            critic_notes=[],
        )
        assert "=== Workspace Asset Map ===" not in prompt

    def test_no_asset_map_block_when_none(self):
        engine = StubEngine()
        engine._asset_map_context = None
        prompt = engine._build_turn_prompt(
            role_id="facilitator",
            round_num=1,
            user_message="Hello",
            decision=None,
            planner_proposals=[],
            critic_notes=[],
        )
        assert "=== Workspace Asset Map ===" not in prompt
