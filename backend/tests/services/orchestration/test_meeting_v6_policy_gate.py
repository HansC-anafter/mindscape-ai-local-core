from unittest.mock import MagicMock

from meeting_v6_test_support import StubMixin


class TestPolicyGate:
    """dispatch_policy_gate blocks unknown playbooks."""

    def test_blocks_unknown_playbook(self):
        from backend.app.services.orchestration.meeting.dispatch_policy_gate import (
            check_dispatch_policy,
        )

        items = [
            {"title": "A", "playbook_code": "ig_analyze"},
            {"title": "B", "playbook_code": "unknown_pb"},
        ]
        check_dispatch_policy(
            items,
            workspace_id="ws-1",
            available_playbooks_cache="- ig_analyze: IG Analyzer\n- ig_report: IG Report",
        )
        assert items[0].get("landing_status") is None  # known → passes
        assert items[1]["landing_status"] == "policy_blocked"
        assert items[1]["policy_reason_code"] == "UNKNOWN_PLAYBOOK"

    def test_no_playbooks_cache_passes_all(self):
        from backend.app.services.orchestration.meeting.dispatch_policy_gate import (
            check_dispatch_policy,
        )

        items = [{"title": "A", "playbook_code": "any_code"}]
        check_dispatch_policy(items, workspace_id="ws-1", available_playbooks_cache="")
        # No cache → no enforcement → item passes
        assert items[0].get("landing_status") is None

    def test_reason_code_present(self):
        from backend.app.services.orchestration.meeting.dispatch_policy_gate import (
            check_dispatch_policy,
        )

        items = [{"title": "X", "playbook_code": "nonexistent"}]
        check_dispatch_policy(
            items, workspace_id="ws-1", available_playbooks_cache="- valid: Valid PB"
        )
        assert "policy_reason_code" in items[0]
        assert items[0]["policy_reason_code"] == "UNKNOWN_PLAYBOOK"

class TestBlockedByValidation:
    """blocked_by cycle and missing reference detection."""

    def _make_engine(self):
        from backend.app.services.orchestration.meeting.engine import MeetingEngine

        class Eng(StubMixin):
            pass

        Eng._resolve_blocked_by_order = MeetingEngine._resolve_blocked_by_order
        return Eng()

    def test_cycle_detection(self):
        engine = self._make_engine()
        items = [
            {"title": "A", "description": "A", "blocked_by": [1]},
            {"title": "B", "description": "B", "blocked_by": [0]},
        ]
        result = engine._resolve_blocked_by_order(items)
        assert items[0]["landing_status"] == "dispatch_error"
        assert "cycle" in items[0]["landing_error"]
        assert items[1]["landing_status"] == "dispatch_error"

    def test_missing_reference(self):
        engine = self._make_engine()
        items = [
            {"title": "A", "description": "A", "blocked_by": [5]},
        ]
        result = engine._resolve_blocked_by_order(items)
        assert items[0]["landing_status"] == "dispatch_error"
        assert "missing dependency" in items[0]["landing_error"]

    def test_valid_deps_pass(self):
        engine = self._make_engine()
        items = [
            {"title": "A", "description": "A"},
            {"title": "B", "description": "B", "blocked_by": [0]},
        ]
        result = engine._resolve_blocked_by_order(items)
        assert items[0].get("landing_status") is None
        assert items[1].get("landing_status") is None
        # Topological order: A before B
        assert result[0]["title"] == "A"
        assert result[1]["title"] == "B"

    def test_no_blocked_by_noop(self):
        engine = self._make_engine()
        items = [
            {"title": "A", "description": "A"},
            {"title": "B", "description": "B"},
        ]
        result = engine._resolve_blocked_by_order(items)
        assert items[0].get("landing_status") is None
        assert items[1].get("landing_status") is None
        assert len(result) == 2

class TestToolExecutionInputParams:
    """_create_action_task writes input_params + tool_name to execution_context."""

    def test_input_params_in_execution_context(self):
        from backend.app.services.orchestration.meeting._action_items import (
            MeetingActionItemsMixin,
        )

        class StubEngine(MeetingActionItemsMixin, StubMixin):
            pass

        engine = StubEngine()
        engine.tasks_store = MagicMock()
        engine.tasks_store.create_task = MagicMock()
        engine._events = [MagicMock(id="evt-001")]

        item = {
            "tool_name": "web_scraper",
            "input_params": {"url": "https://example.com", "depth": 2},
            "description": "Scrape it",
        }
        task_id = engine._create_action_task(item)
        assert task_id is not None

        task_obj = engine.tasks_store.create_task.call_args[0][0]
        assert task_obj.task_type == "tool_execution"
        assert task_obj.execution_context["tool_name"] == "web_scraper"
        assert task_obj.execution_context["inputs"] == {
            "url": "https://example.com",
            "depth": 2,
        }
        assert task_obj.params["tool_name"] == "web_scraper"
        assert task_obj.params["input_params"] == {
            "url": "https://example.com",
            "depth": 2,
        }

class TestToolAllowlist:
    """Tool allowlist blocks tools not in workspace bindings."""

    def test_tool_not_in_allowlist(self):
        from backend.app.services.orchestration.meeting.dispatch_policy_gate import (
            check_dispatch_policy,
        )

        binding = MagicMock()
        binding.resource_id = "allowed_tool"
        binding_store = MagicMock()
        binding_store.list_bindings_by_workspace.return_value = [binding]

        items = [
            {"title": "A", "tool_name": "allowed_tool", "description": "ok"},
            {"title": "B", "tool_name": "blocked_tool", "description": "bad"},
        ]
        check_dispatch_policy(
            items,
            workspace_id="ws-1",
            binding_store=binding_store,
        )
        assert items[0].get("landing_status") is None  # allowed
        assert items[1]["landing_status"] == "policy_blocked"
        assert items[1]["policy_reason_code"] == "TOOL_NOT_ALLOWED"

    def test_tool_in_allowlist_passes(self):
        from backend.app.services.orchestration.meeting.dispatch_policy_gate import (
            check_dispatch_policy,
        )

        binding = MagicMock()
        binding.resource_id = "my_tool"
        binding_store = MagicMock()
        binding_store.list_bindings_by_workspace.return_value = [binding]

        items = [{"title": "OK", "tool_name": "my_tool", "description": "fine"}]
        check_dispatch_policy(items, workspace_id="ws-1", binding_store=binding_store)
        assert items[0].get("landing_status") is None

    def test_no_binding_store_passes_all(self):
        from backend.app.services.orchestration.meeting.dispatch_policy_gate import (
            check_dispatch_policy,
        )

        items = [{"title": "Any", "tool_name": "any_tool", "description": "ok"}]
        check_dispatch_policy(items, workspace_id="ws-1", binding_store=None)
        assert items[0].get("landing_status") is None  # no enforcement

    def test_per_item_target_workspace_allowlist(self):
        """5E: allowlist uses item's target_workspace_id, not session workspace."""
        from backend.app.services.orchestration.meeting.dispatch_policy_gate import (
            check_dispatch_policy,
        )

        # ws-target has tool_a allowed; session ws-session has tool_b allowed
        binding_a = MagicMock()
        binding_a.resource_id = "tool_a"
        binding_b = MagicMock()
        binding_b.resource_id = "tool_b"
        binding_store = MagicMock()

        def _list(ws_id, resource_type=None):
            if ws_id == "ws-target":
                return [binding_a]
            if ws_id == "ws-session":
                return [binding_b]
            return []

        binding_store.list_bindings_by_workspace.side_effect = _list

        items = [
            {"title": "A", "tool_name": "tool_a", "target_workspace_id": "ws-target"},
            {"title": "B", "tool_name": "tool_b"},  # falls back to session ws
        ]
        check_dispatch_policy(
            items, workspace_id="ws-session", binding_store=binding_store
        )
        # tool_a is allowed on ws-target → pass
        assert items[0].get("landing_status") is None
        # tool_b is allowed on ws-session (fallback) → pass
        assert items[1].get("landing_status") is None

    def test_suffix_tool_name_is_canonicalized_when_unique(self):
        """Bare tool name should be normalized to canonical allowlist ID."""
        from backend.app.services.orchestration.meeting.dispatch_policy_gate import (
            check_dispatch_policy,
        )

        binding = MagicMock()
        binding.resource_id = "ig.ig_fetch_posts"
        binding_store = MagicMock()
        binding_store.list_bindings_by_workspace.return_value = [binding]

        items = [{"title": "Sync", "tool_name": "ig_fetch_posts"}]
        check_dispatch_policy(items, workspace_id="ws-1", binding_store=binding_store)

        assert items[0].get("landing_status") is None
        assert items[0]["tool_name"] == "ig.ig_fetch_posts"
        assert items[0]["tool_name_original"] == "ig_fetch_posts"
        assert items[0]["tool_name_normalized"] is True

    def test_suffix_tool_name_ambiguous_still_blocked(self):
        """Ambiguous bare name should stay blocked for later repair phase."""
        from backend.app.services.orchestration.meeting.dispatch_policy_gate import (
            check_dispatch_policy,
        )

        binding_a = MagicMock()
        binding_a.resource_id = "ig.ig_fetch_posts"
        binding_b = MagicMock()
        binding_b.resource_id = "legacy.ig_fetch_posts"
        binding_store = MagicMock()
        binding_store.list_bindings_by_workspace.return_value = [binding_a, binding_b]

        items = [{"title": "Sync", "tool_name": "ig_fetch_posts"}]
        check_dispatch_policy(items, workspace_id="ws-1", binding_store=binding_store)

        assert items[0]["landing_status"] == "policy_blocked"
        assert items[0]["policy_reason_code"] == "TOOL_NOT_ALLOWED"

class TestVisibilityModel:
    """Tests for WorkspaceVisibility integration in models."""

    def test_workspace_defaults_to_private(self):
        """Workspace model defaults to PRIVATE when visibility not specified."""
        from backend.app.models.workspace import Workspace, WorkspaceVisibility

        ws = Workspace(
            id="ws-test",
            title="Test",
            owner_user_id="u1",
        )
        assert ws.visibility == WorkspaceVisibility.PRIVATE
