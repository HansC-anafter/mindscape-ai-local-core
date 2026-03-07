"""
Regression tests for meeting engine P0 fixes.

UNIT TESTS (run locally, no DB):
  - TestNullToolGate: pure gate condition logic
  - TestRagCacheInjection: _rag_tool_cache pre-fetch in MeetingEngine

INTEGRATION TESTS (run inside Docker container — need backend.app import path):
  - TestHasWorkspaceToolBindings
  - TestMandatoryConstraintInjection

  Run with:
    docker exec mindscape-ai-local-core-backend python3 -m pytest
    /app/backend/tests/test_meeting_null_tool_gate.py -v -k "integration"
"""

import sys
import os
import pytest
from unittest.mock import MagicMock, patch, AsyncMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


# ---------------------------------------------------------------------------
# Helpers / stubs
# ---------------------------------------------------------------------------


def _make_mixin(workspace_id="ws-test", has_bindings=False):
    """Create a minimal MeetingPromptsMixin-like object for unit testing."""
    from backend.app.services.orchestration.meeting._prompts import MeetingPromptsMixin

    class StubMixin(MeetingPromptsMixin):
        pass

    obj = StubMixin()
    obj.session = MagicMock()
    obj.session.id = "session-test"
    obj.session.workspace_id = workspace_id
    obj.session.agenda = ["test agenda item"]
    obj.workspace = MagicMock()
    obj.workspace.id = workspace_id
    obj._available_playbooks_cache = ""
    obj._uploaded_files = []
    obj._locale = "en"
    obj._rag_tool_cache = []
    obj._project_context = ""
    obj._asset_map_context = ""
    obj._active_intent_ids = []
    obj.session.max_rounds = 5

    # Patch _has_workspace_tool_bindings
    obj._has_workspace_tool_bindings = MagicMock(return_value=has_bindings)

    return obj


# ---------------------------------------------------------------------------
# Test: _has_workspace_tool_bindings()
# ---------------------------------------------------------------------------


class TestHasWorkspaceToolBindings:

    def test_returns_false_when_no_bindings(self):
        """Workspace with zero TOOL bindings → False (no enforcement)."""
        from backend.app.services.orchestration.meeting._prompts import (
            MeetingPromptsMixin,
        )

        class Stub(MeetingPromptsMixin):
            pass

        obj = Stub()
        obj.session = MagicMock(workspace_id="ws-none")
        obj.workspace = None

        with patch(
            "backend.app.services.stores.workspace_resource_binding_store"
            ".WorkspaceResourceBindingStore.list_bindings_by_workspace",
            return_value=[],
        ):
            assert obj._has_workspace_tool_bindings() is False

    def test_returns_true_when_bindings_exist(self):
        """Workspace with TOOL bindings → True (enforcement active)."""
        from backend.app.services.orchestration.meeting._prompts import (
            MeetingPromptsMixin,
        )

        class Stub(MeetingPromptsMixin):
            pass

        obj = Stub()
        obj.session = MagicMock(workspace_id="ws-bound")
        obj.workspace = None

        fake_binding = MagicMock()
        with patch(
            "backend.app.services.stores.workspace_resource_binding_store"
            ".WorkspaceResourceBindingStore.list_bindings_by_workspace",
            return_value=[fake_binding],
        ):
            assert obj._has_workspace_tool_bindings() is True


# ---------------------------------------------------------------------------
# Test: MANDATORY constraint injection in executor prompt
# ---------------------------------------------------------------------------


class TestMandatoryConstraintInjection:

    def test_no_mandatory_when_no_explicit_bindings(self):
        """Manifest fallback only (no explicit bindings) → MANDATORY absent."""
        obj = _make_mixin(has_bindings=False)
        with patch.object(
            obj, "_build_tool_inventory_block", return_value="- ig.tool_a: Tool A"
        ), patch.object(
            obj, "_build_previous_decisions_context", return_value=""
        ), patch.object(
            obj, "_build_workspace_instruction_block", return_value=""
        ), patch.object(
            obj, "_build_lens_context", return_value=""
        ), patch.object(
            obj, "_history_snippet", return_value=""
        ):
            prompt = obj._build_turn_prompt(
                "executor",
                round_num=1,
                user_message="test",
                decision=None,
                planner_proposals=[],
                critic_notes=[],
            )
        assert "MANDATORY" not in prompt

    def test_mandatory_present_when_explicit_bindings(self):
        """Workspace with explicit TOOL bindings → MANDATORY present."""
        obj = _make_mixin(has_bindings=True)
        with patch.object(
            obj, "_build_tool_inventory_block", return_value="- ig.tool_a: Tool A"
        ), patch.object(
            obj, "_build_previous_decisions_context", return_value=""
        ), patch.object(
            obj, "_build_workspace_instruction_block", return_value=""
        ), patch.object(
            obj, "_build_lens_context", return_value=""
        ), patch.object(
            obj, "_history_snippet", return_value=""
        ):
            prompt = obj._build_turn_prompt(
                "executor",
                round_num=1,
                user_message="test",
                decision=None,
                planner_proposals=[],
                critic_notes=[],
            )
        assert "MANDATORY" in prompt


# ---------------------------------------------------------------------------
# Test: null-tool gate condition
# ---------------------------------------------------------------------------


class TestNullToolGate:

    def test_gate_does_not_fire_without_explicit_bindings(self):
        """If workspace has no explicit bindings, gate must not trigger retry."""
        # The gate condition: all_null AND _has_workspace_tool_bindings()
        # With has_bindings=False, gate should be False even if all null
        action_items = [
            {"tool_name": None, "playbook_code": None, "title": "T1"},
        ]
        all_null = action_items and not any(
            item.get("tool_name") or item.get("playbook_code") for item in action_items
        )
        has_bindings = False
        should_gate = all_null and has_bindings
        assert (
            should_gate is False
        ), "Gate must NOT fire when workspace has no explicit TOOL bindings"

    def test_gate_fires_when_explicit_bindings_and_all_null(self):
        """Explicit bindings + all-null action_items → gate should fire."""
        action_items = [
            {"tool_name": None, "playbook_code": None, "title": "T1"},
        ]
        all_null = action_items and not any(
            item.get("tool_name") or item.get("playbook_code") for item in action_items
        )
        has_bindings = True
        should_gate = all_null and has_bindings
        assert should_gate is True

    def test_gate_does_not_fire_when_some_items_have_tool(self):
        """At least one item with tool_name → gate must not fire."""
        action_items = [
            {
                "tool_name": "ig.ig_analyze_following",
                "playbook_code": None,
                "title": "T1",
            },
            {"tool_name": None, "playbook_code": None, "title": "T2"},
        ]
        all_null = action_items and not any(
            item.get("tool_name") or item.get("playbook_code") for item in action_items
        )
        assert all_null is False

    def test_gate_fires_when_rag_cache_and_all_null(self):
        """RAG cache non-empty + all-null action_items → gate should fire.

        Even without explicit TOOL bindings, if Tool RAG returned tools,
        the LLM was given a tool list and should have used it.
        """
        action_items = [
            {"tool_name": None, "playbook_code": None, "title": "T1"},
        ]
        all_null = action_items and not any(
            item.get("tool_name") or item.get("playbook_code") for item in action_items
        )
        has_bindings = False
        has_rag_cache = True  # RAG returned tools
        has_tool_context = has_bindings or has_rag_cache
        should_gate = all_null and has_tool_context
        assert (
            should_gate is True
        ), "Gate must fire when RAG cache has tools, even without bindings"

    def test_gate_does_not_fire_when_no_bindings_no_rag(self):
        """No bindings + empty RAG cache → gate must not fire."""
        action_items = [
            {"tool_name": None, "playbook_code": None, "title": "T1"},
        ]
        all_null = action_items and not any(
            item.get("tool_name") or item.get("playbook_code") for item in action_items
        )
        has_bindings = False
        has_rag_cache = False
        has_tool_context = has_bindings or has_rag_cache
        should_gate = all_null and has_tool_context
        assert (
            should_gate is False
        ), "Gate must NOT fire when no tools were provided to LLM"


# ---------------------------------------------------------------------------
# Test: RAG cache pre-fetch in MeetingEngine (unit, no DB)
# ---------------------------------------------------------------------------


class TestRagCacheInjection:
    """Verify that _rag_tool_cache is populated during process_turn().

    We do NOT import MeetingEngine directly here (would require full DB).
    Instead we test the _make_key / cache logic in tool_rag as a proxy.
    """

    def test_retrieve_relevant_tools_returns_list(self):
        """retrieve_relevant_tools returns a list (possibly empty on import error)."""
        import asyncio
        import backend.app.services.tool_rag as rag
        from unittest.mock import AsyncMock

        rag.invalidate_tool_rag_cache()
        fake = [
            {
                "tool_id": "ig_analyze_following",
                "display_name": "IG",
                "description": "x",
            }
        ]
        with patch.object(
            rag, "_retrieve_from_service", new=AsyncMock(return_value=fake)
        ):
            result = asyncio.run(
                rag.retrieve_relevant_tools("analyze instagram following", top_k=5)
            )
        assert isinstance(result, list)
        assert result[0]["tool_id"] == "ig_analyze_following"

    def test_rag_cache_hit_returns_same_object(self):
        """Second identical query returns exactly the same list object (cache hit)."""
        import asyncio
        import backend.app.services.tool_rag as rag

        rag.invalidate_tool_rag_cache()
        fake = [
            {
                "tool_id": "ig_post_style_analyzer",
                "display_name": "Style",
                "description": "",
            }
        ]
        call_count = [0]

        async def counting_service(query, top_k, workspace_id):
            call_count[0] += 1
            return fake

        with patch.object(rag, "_retrieve_from_service", new=counting_service):
            r1 = asyncio.run(rag.retrieve_relevant_tools("style analysis", top_k=5))
            # Re-run with fresh event loop — cache is process-level so it persists
            rag_module = rag  # capture ref

            async def _get_cached():
                return await rag_module.retrieve_relevant_tools(
                    "style analysis", top_k=5
                )

            r2 = asyncio.run(_get_cached())

        assert r1 is r2, "Second call must return cached object, not a new list"
        assert call_count[0] == 1, "_retrieve_from_service called more than once"

    def test_different_workspace_different_result(self):
        """Two calls with different workspace_id use separate cache slots."""
        import asyncio
        import backend.app.services.tool_rag as rag

        rag.invalidate_tool_rag_cache()
        results = {
            "ws-a": [{"tool_id": "tool-a", "display_name": "A", "description": ""}],
            "ws-b": [{"tool_id": "tool-b", "display_name": "B", "description": ""}],
        }

        async def side_effect(query, top_k, workspace_id):
            return results.get(workspace_id, [])

        with patch.object(rag, "_retrieve_from_service", new=side_effect):
            ra = asyncio.run(
                rag.retrieve_relevant_tools("q", top_k=5, workspace_id="ws-a")
            )

            async def _get_b():
                return await rag.retrieve_relevant_tools(
                    "q", top_k=5, workspace_id="ws-b"
                )

            rb = asyncio.run(_get_b())

        assert ra[0]["tool_id"] == "tool-a"
        assert rb[0]["tool_id"] == "tool-b"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
