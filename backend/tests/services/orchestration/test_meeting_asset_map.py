"""Workspace Group asset-map admission and prompt tests."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from backend.app.services.orchestration.meeting._prompts import MeetingPromptsMixin


def _workspace_card(ws_id, title, *, persona=None, goals=None, data_sources=None):
    blueprint = SimpleNamespace(
        instruction=SimpleNamespace(persona=persona or "", goals=list(goals or []))
    )
    return SimpleNamespace(
        id=ws_id,
        title=title,
        workspace_blueprint=blueprint,
        suggestion_history=[],
        data_sources=data_sources or {},
    )


def _snapshot(members):
    return {
        "id": "snapshot-1",
        "group_id": "grp-001",
        "display_name": "My Project Group",
        "group_revision": 7,
        "content_hash": "a" * 64,
        "members": [
            {"workspace_id": member.workspace_id, "role": member.role}
            for member in members
        ],
        "dispatch_workspace_id": "ws-dispatch",
        "cell_workspace_ids": ["ws-data"],
        "created_by_user_id": "user-001",
    }


class StubEngine(MeetingPromptsMixin):
    def __init__(self):
        self.session = MagicMock()
        self.session.id = "sess-001"
        self.session.workspace_id = "ws-dispatch"
        self.session.agenda = ["Plan cross-workspace task"]
        self.session.success_criteria = []
        self.session.lens_id = None
        self.session.max_rounds = 5
        self.session.metadata = {}
        self.workspace = MagicMock()
        self.workspace.id = "ws-dispatch"
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
    def test_returns_empty_without_workspace(self):
        engine = StubEngine()
        engine.workspace = None
        assert engine._build_asset_map_context() == ""

    def test_no_explicit_group_is_single_workspace(self):
        engine = StubEngine()
        assert engine._build_asset_map_context() == ""

    def test_builds_context_only_from_admission_group(self):
        engine = StubEngine()
        members = [
            SimpleNamespace(workspace_id="ws-dispatch", role="dispatch"),
            SimpleNamespace(workspace_id="ws-data", role="cell"),
        ]
        engine.session.metadata = {"workspace_group_snapshot": _snapshot(members)}
        workspaces = {
            "ws-dispatch": _workspace_card(
                "ws-dispatch", "Dispatch", persona="Dispatch coordinator"
            ),
            "ws-data": _workspace_card(
                "ws-data",
                "Data",
                persona="Data operations workspace",
                data_sources={
                    "ig": {
                        "total_runs": 4,
                        "last_run": "2026-07-15T08:30:00Z",
                        "produces": [{"label": "IG Followers DB"}],
                    }
                },
            ),
        }
        running_loop = MagicMock()
        running_loop.is_running.return_value = True

        with patch(
            "backend.app.services.stores.postgres.workspaces_store.PostgresWorkspacesStore"
        ) as workspaces_cls, patch("asyncio.get_event_loop", return_value=running_loop):
            workspaces_cls.return_value.get_workspace_sync.side_effect = workspaces.get
            result = engine._build_asset_map_context()

        assert "My Project Group (grp-001, revision 7, snapshot snapshot-1)" in result
        assert "[dispatch] ws-dispatch (current)" in result
        assert "[cell] ws-data" in result
        assert "IG Followers DB" in result
        assert "Discoverable Workspaces" not in result

    def test_invalid_snapshot_does_not_fall_back_to_legacy_group(self):
        engine = StubEngine()
        engine.session.metadata = {"workspace_group_snapshot": {"id": "broken"}}
        engine.workspace.group_id = "legacy-group"
        assert engine._build_asset_map_context() == ""


class TestAssetMapPromptInjection:
    def test_asset_map_block_injected_when_context_exists(self):
        engine = StubEngine()
        engine._asset_map_context = (
            "Workspace Group: Test Group (grp-001)\n"
            "  [dispatch] ws-dispatch (current)\n"
            "  [cell] ws-data"
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
        assert "target_workspace_id" in prompt

    def test_no_asset_map_block_without_group_context(self):
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
