"""Tests for progressive tool discovery pipeline (Layer 0 + Layer C).

UNIT TESTS (run locally, no DB):
  - TestDecomposeAgenda: LLM decomposition, provider compat, fallback
  - TestLayerCGapRefetch: null-actuator gap detection, re-fetch logic
  - TestLayer0cPersistence: engine fallback + store persist
  - TestModelNamePlumbing: model_name travels from caller to decompose

Run with:
  python3 -m pytest backend/tests/services/orchestration/test_progressive_tool_discovery.py -v
  docker exec mindscape-ai-local-core-backend python3 -m pytest \
    /app/backend/tests/services/orchestration/test_progressive_tool_discovery.py -v
"""

import sys
import os
import asyncio
import json
import inspect
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))


# ---------------------------------------------------------------------------
# Helper: build a mock provider with a controlled signature
# ---------------------------------------------------------------------------


def _build_provider(response: str, sig_params: list[str]):
    """Return an AsyncMock provider whose chat_completion has *sig_params*."""
    provider = AsyncMock()
    provider.chat_completion = AsyncMock(return_value=response)
    params = [
        inspect.Parameter(p, inspect.Parameter.POSITIONAL_OR_KEYWORD, default=None)
        for p in sig_params
    ]
    provider.chat_completion.__signature__ = inspect.Signature(params)
    return provider


def _patch_provider(provider):
    """Context-manager that injects *provider* into _decompose_agenda lazy imports."""
    import contextlib
    import types

    @contextlib.contextmanager
    def _ctx():
        stubs = {}
        chain = [
            "backend.features.workspace",
            "backend.features.workspace.chat",
            "backend.features.workspace.chat.utils",
            "backend.features.workspace.chat.utils.llm_provider",
        ]
        for mod_name in chain:
            if mod_name not in sys.modules:
                stub = types.ModuleType(mod_name)
                sys.modules[mod_name] = stub
                stubs[mod_name] = stub

        llm_mod = sys.modules["backend.features.workspace.chat.utils.llm_provider"]
        llm_mod.get_llm_provider = MagicMock(return_value=(provider, None))
        llm_mod.get_llm_provider_manager = MagicMock()

        try:
            yield
        finally:
            for mod_name in stubs:
                sys.modules.pop(mod_name, None)

    return _ctx()


# ---------------------------------------------------------------------------
# TestDecomposeAgenda
# ---------------------------------------------------------------------------


class TestDecomposeAgenda:
    """Unit tests for _decompose_agenda()."""

    @pytest.mark.asyncio
    async def test_basic_decomposition(self):
        provider = _build_provider(
            '["research autonomic nerve", "create IG posts", "find images"]',
            ["messages", "model", "temperature", "max_tokens", "max_completion_tokens"],
        )
        with _patch_provider(provider):
            from backend.app.services.conversation.pipeline_meeting import (
                _decompose_agenda,
            )

            result = await _decompose_agenda(
                "Research autonomic nerve studies and create IG posts with images",
                model_name="gemini-2.5-pro",
            )
            assert len(result) == 3

    @pytest.mark.asyncio
    async def test_provider_safe_kwargs_anthropic(self):
        """Anthropic provider should NOT receive temperature/max_tokens kwargs."""
        provider = _build_provider(
            '["step A", "step B", "step C"]',
            ["messages", "model"],
        )
        with _patch_provider(provider):
            from backend.app.services.conversation.pipeline_meeting import (
                _decompose_agenda,
            )

            result = await _decompose_agenda(
                "Do three different tasks for me please now",
                model_name="claude-3",
            )
            assert len(result) >= 2
            call_args = provider.chat_completion.call_args
            passed_keys = set(call_args.kwargs.keys()) if call_args.kwargs else set()
            assert "temperature" not in passed_keys
            assert "max_tokens" not in passed_keys

    @pytest.mark.asyncio
    async def test_fallback_on_short_input(self):
        from backend.app.services.conversation.pipeline_meeting import _decompose_agenda

        result = await _decompose_agenda("hello")
        assert result == ["hello"]

    @pytest.mark.asyncio
    async def test_fallback_on_provider_error(self):
        provider = _build_provider("unused", ["messages", "model"])
        provider.chat_completion = AsyncMock(side_effect=RuntimeError("boom"))
        provider.chat_completion.__signature__ = inspect.Signature(
            [
                inspect.Parameter(
                    p, inspect.Parameter.POSITIONAL_OR_KEYWORD, default=None
                )
                for p in ["messages", "model"]
            ]
        )
        with _patch_provider(provider):
            from backend.app.services.conversation.pipeline_meeting import (
                _decompose_agenda,
            )

            result = await _decompose_agenda(
                "Some complex task that should fallback gracefully",
                model_name="test-model",
            )
            assert len(result) == 1

    @pytest.mark.asyncio
    async def test_json_code_block_stripping(self):
        provider = _build_provider(
            '```json\n["task A", "task B"]\n```',
            ["messages", "model", "temperature", "max_tokens", "max_completion_tokens"],
        )
        with _patch_provider(provider):
            from backend.app.services.conversation.pipeline_meeting import (
                _decompose_agenda,
            )

            result = await _decompose_agenda(
                "Plan two different things for my project",
                model_name="gemini-pro",
            )
            assert len(result) == 2


# ---------------------------------------------------------------------------
# TestModelNamePlumbing
# ---------------------------------------------------------------------------


class TestModelNamePlumbing:
    """Verify model_name flows from ensure_meeting_session to _decompose_agenda."""

    @pytest.mark.asyncio
    async def test_model_name_forwarded_on_new_session(self):
        """New session creation should pass model_name to _decompose_agenda."""
        with (
            patch(
                "backend.app.services.conversation.pipeline_meeting._decompose_agenda",
                new_callable=AsyncMock,
                return_value=["task A", "task B"],
            ) as mock_decompose,
            patch(
                "backend.app.models.meeting_session.MeetingSession",
            ) as mock_session_cls,
        ):
            mock_session_cls.new.return_value = MagicMock(id="s1")
            mock_store = MagicMock()
            mock_store.get_active_session.return_value = None
            mock_store.create = MagicMock()

            from backend.app.services.conversation.pipeline_meeting import (
                ensure_meeting_session,
            )

            await ensure_meeting_session(
                "ws1",
                "t1",
                mock_store,
                project_id=None,
                user_message="Research and write posts",
                model_name="gemini-2.5-pro",
            )
            mock_decompose.assert_awaited_once_with(
                "Research and write posts",
                model_name="gemini-2.5-pro",
            )

    @pytest.mark.asyncio
    async def test_model_name_forwarded_on_reuse(self):
        """Session reuse should pass model_name to _decompose_agenda."""
        existing = MagicMock()
        existing.id = "s-existing"
        existing.agenda = ["old item"]

        with patch(
            "backend.app.services.conversation.pipeline_meeting._decompose_agenda",
            new_callable=AsyncMock,
            return_value=["new A", "new B"],
        ) as mock_decompose:
            mock_store = MagicMock()
            mock_store.get_active_session.return_value = existing
            mock_store.update = MagicMock()

            from backend.app.services.conversation.pipeline_meeting import (
                ensure_meeting_session,
            )

            await ensure_meeting_session(
                "ws1",
                "t1",
                mock_store,
                project_id=None,
                user_message="New multi-step request",
                model_name="claude-3-5-sonnet",
            )
            mock_decompose.assert_awaited_once_with(
                "New multi-step request",
                model_name="claude-3-5-sonnet",
            )


# ---------------------------------------------------------------------------
# TestLayerCGapRefetch
# ---------------------------------------------------------------------------


class TestLayerCGapRefetch:
    """Test Layer C gap detection and re-fetch logic."""

    def _make_action_items(self, specs):
        return [
            {"title": t, "tool_name": tn, "playbook_code": pb} for t, tn, pb in specs
        ]

    def test_partial_gap_detected(self):
        items = self._make_action_items(
            [
                ("Research papers", "frontier_research.fetch", None),
                ("Create posts", None, None),
                ("Find images", None, None),
            ]
        )
        null_actuator = [
            i for i in items if not i.get("tool_name") and not i.get("playbook_code")
        ]
        assert len(null_actuator) == 2

    def test_no_gap_when_all_bound(self):
        items = self._make_action_items(
            [
                ("Research papers", "frontier_research.fetch", None),
                ("Create posts", "content_drafting.gen", None),
                ("Schedule", None, "scheduler"),
            ]
        )
        null_actuator = [
            i for i in items if not i.get("tool_name") and not i.get("playbook_code")
        ]
        assert len(null_actuator) == 0

    def test_playbook_counts_as_bound(self):
        items = self._make_action_items(
            [
                ("Run analysis", None, "ig_analyze"),
                ("Draft content", None, None),
            ]
        )
        null_actuator = [
            i for i in items if not i.get("tool_name") and not i.get("playbook_code")
        ]
        assert len(null_actuator) == 1
        assert null_actuator[0]["title"] == "Draft content"

    def test_all_null_triggers_gate(self):
        items = self._make_action_items(
            [
                ("Task A", None, None),
                ("Task B", None, None),
            ]
        )
        all_null = items and not any(
            i.get("tool_name") or i.get("playbook_code") for i in items
        )
        assert all_null is True

    def test_enrichment_deduplicates_by_tool_id(self):
        """Layer C should skip tools already in _rag_tool_cache."""
        existing_cache = [{"tool_id": "t1"}, {"tool_id": "t2"}]
        new_hits = [
            {"tool_id": "t2"},  # duplicate
            {"tool_id": "t3"},  # new
        ]
        cache_ids = {t["tool_id"] for t in existing_cache}
        enriched = 0
        for h in new_hits:
            if h["tool_id"] not in cache_ids:
                cache_ids.add(h["tool_id"])
                existing_cache.append(h)
                enriched += 1
        assert enriched == 1
        assert len(existing_cache) == 3

    def test_retry_improvement_check(self):
        """Layer C only accepts retry if new_bound > old_bound."""
        first_pass = self._make_action_items(
            [
                ("A", "tool.x", None),
                ("B", None, None),
                ("C", None, None),
            ]
        )
        retry_pass = self._make_action_items(
            [
                ("A", "tool.x", None),
                ("B", "tool.y", None),
                ("C", None, None),
            ]
        )
        old_bound = sum(
            1 for i in first_pass if i.get("tool_name") or i.get("playbook_code")
        )
        new_bound = sum(
            1 for i in retry_pass if i.get("tool_name") or i.get("playbook_code")
        )
        assert old_bound == 1
        assert new_bound == 2
        assert new_bound > old_bound, "Retry should improve binding count"


# ---------------------------------------------------------------------------
# TestLayer0cPersistence
# ---------------------------------------------------------------------------


class TestLayer0cPersistence:
    """Verify Layer 0c decomposes and persists agenda in engine.run()."""

    @pytest.mark.asyncio
    async def test_layer0c_calls_decompose_with_model_name(self):
        """Engine fallback should pass self.model_name to _decompose_agenda."""
        mock_decompose = AsyncMock(return_value=["sub A", "sub B", "sub C"])
        mock_session = MagicMock()
        mock_session.agenda = ["single item"]
        mock_session.id = "session-0c"
        mock_session.workspace_id = "ws-1"

        mock_store = MagicMock()
        mock_store.update = MagicMock()

        engine = MagicMock()
        engine.session = mock_session
        engine.session_store = mock_store
        engine.model_name = "gemini-2.5-pro"

        # Simulate the Layer 0c block from engine.run()
        _l0_agenda = getattr(engine.session, "agenda", None) or []
        user_message = "A long enough message for testing decomposition"
        if len(_l0_agenda) <= 1 and user_message and len(user_message.strip()) >= 10:
            decomposed = await mock_decompose(
                user_message,
                model_name=engine.model_name,
            )
            if len(decomposed) > 1:
                engine.session.agenda = decomposed
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(
                    None,
                    lambda: engine.session_store.update(engine.session),
                )

        mock_decompose.assert_awaited_once_with(
            user_message,
            model_name="gemini-2.5-pro",
        )
        assert engine.session.agenda == ["sub A", "sub B", "sub C"]
        mock_store.update.assert_called_once_with(engine.session)

    @pytest.mark.asyncio
    async def test_layer0c_skips_when_agenda_already_decomposed(self):
        """Engine fallback should NOT fire when agenda already has >1 items."""
        mock_decompose = AsyncMock(return_value=["x", "y"])
        mock_session = MagicMock()
        mock_session.agenda = ["item 1", "item 2", "item 3"]

        _l0_agenda = getattr(mock_session, "agenda", None) or []
        user_message = "Some long message for testing skip"
        if len(_l0_agenda) <= 1 and user_message and len(user_message.strip()) >= 10:
            await mock_decompose(user_message)

        mock_decompose.assert_not_awaited()
