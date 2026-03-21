"""
Unit tests for workspace asset map context injection into meeting prompts.

Tests _build_asset_map_context() and its injection into _build_turn_prompt
as the === Workspace Asset Map === block.
"""

from types import SimpleNamespace
import pytest
from unittest.mock import MagicMock, patch

from backend.app.services.orchestration.meeting._prompts import MeetingPromptsMixin


def _make_workspace_card(
    ws_id,
    title,
    *,
    persona=None,
    goals=None,
    suggestion_titles=None,
    data_sources=None,
):
    blueprint = None
    if persona or goals:
        blueprint = SimpleNamespace(
            instruction=SimpleNamespace(
                persona=persona or "",
                goals=list(goals or []),
            )
        )

    suggestion_history = []
    if suggestion_titles:
        suggestion_history = [
            {"suggestions": [{"title": item} for item in suggestion_titles]}
        ]

    return SimpleNamespace(
        id=ws_id,
        title=title,
        workspace_blueprint=blueprint,
        suggestion_history=suggestion_history,
        data_sources=data_sources or {},
    )


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

        disco_ws = _make_workspace_card(
            "ws-shared-db",
            "Shared Database",
            persona="Shared data workspace",
            goals=["Serve shared warehouse access"],
            data_sources={
                "postgres_sync": {
                    "total_runs": 3,
                    "last_run": "2026-03-19T12:00:00Z",
                    "produces": [{"label": "Shared PostgreSQL"}],
                }
            },
        )

        with patch(
            "backend.app.services.stores.postgres.workspaces_store"
            ".PostgresWorkspacesStore"
        ) as ws_cls:
            ws_cls.return_value.list_discoverable_workspaces.return_value = [disco_ws]

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
        "backend.app.services.stores.postgres.workspaces_store"
        ".PostgresWorkspacesStore"
    )
    def test_returns_empty_when_group_not_found(self, mock_ws_cls, mock_group_cls):
        engine = StubEngine()
        engine.workspace.group_id = "grp-001"
        mock_group_cls.return_value.get.return_value = None
        mock_ws_cls.return_value.list_discoverable_workspaces.return_value = []
        assert engine._build_asset_map_context() == ""

    def test_builds_context_with_assets(self):
        engine = StubEngine()
        engine.workspace.group_id = "grp-001"
        engine.workspace.workspace_role = "dispatch"

        mock_group = SimpleNamespace(
            id="grp-001",
            display_name="My Project Group",
            role_map={
                "ws-dispatch": "dispatch",
                "ws-data": "cell",
            },
        )
        ws_lookup = {
            "ws-dispatch": _make_workspace_card(
                "ws-dispatch",
                "Dispatch Workspace",
                persona="Dispatch coordinator",
                goals=["Route work across workspaces"],
            ),
            "ws-data": _make_workspace_card(
                "ws-data",
                "Data Workspace",
                persona="Data operations workspace",
                goals=["Maintain reusable datasets"],
                data_sources={
                    "ig_followers": {
                        "total_runs": 4,
                        "last_run": "2026-03-19T08:30:00Z",
                        "produces": [
                            {"label": "IG Followers DB"},
                            {"label": "Content Library"},
                        ],
                    }
                },
            ),
        }
        running_loop = MagicMock()
        running_loop.is_running.return_value = True

        with patch(
            "backend.app.services.stores.postgres.workspace_group_store"
            ".PostgresWorkspaceGroupStore"
        ) as pg_cls, patch(
            "backend.app.services.stores.postgres.workspaces_store"
            ".PostgresWorkspacesStore"
        ) as ws_cls, patch(
            "asyncio.get_event_loop", return_value=running_loop
        ):
            pg_cls.return_value.get.return_value = mock_group
            ws_cls.return_value.list_discoverable_workspaces.return_value = []
            ws_cls.return_value.get_workspace_sync.side_effect = (
                lambda ws_id: ws_lookup[ws_id]
            )

            result = engine._build_asset_map_context()

        assert "My Project Group" in result
        assert "dispatch" in result
        assert "ws-dispatch" in result
        assert "(current)" in result
        assert "ws-data" in result
        assert "Identity: Dispatch coordinator" in result
        assert "Identity: Data operations workspace" in result
        assert "Data assets (completed):" in result
        assert "IG Followers DB" in result
        assert "Content Library" in result
        assert "(identity lookup unavailable)" not in result

    def test_returns_empty_on_exception(self):
        engine = StubEngine()
        engine.workspace.group_id = "grp-001"
        with patch(
            "backend.app.services.stores.postgres.workspaces_store"
            ".PostgresWorkspacesStore",
            side_effect=RuntimeError("boom"),
        ):
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

        mock_group = SimpleNamespace(
            id="grp-001",
            display_name="Test Group",
            role_map={"ws-dispatch": "dispatch"},
        )

        disco_ws = _make_workspace_card(
            "ws-shared-db",
            "Shared Database",
            persona="Shared data workspace",
            data_sources={
                "shared_pg": {
                    "total_runs": 2,
                    "last_run": "2026-03-18T09:00:00Z",
                    "produces": [{"label": "Shared PostgreSQL"}],
                }
            },
        )

        with patch(
            "backend.app.services.stores.postgres.workspace_group_store"
            ".PostgresWorkspaceGroupStore"
        ) as pg_cls, patch(
            "backend.app.services.stores.postgres.workspaces_store"
            ".PostgresWorkspacesStore"
        ) as ws_cls:
            pg_cls.return_value.get.return_value = mock_group
            ws_cls.return_value.list_discoverable_workspaces.return_value = [disco_ws]

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
