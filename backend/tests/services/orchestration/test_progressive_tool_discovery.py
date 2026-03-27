"""Tests for progressive tool discovery pipeline (Layer 0 + Layer C).

UNIT TESTS (run locally AND in container):
  - TestDecomposeAgenda: LLM decomposition, provider compat, fallback
  - TestModelNamePlumbing: model_name travels from caller to decompose
  - TestLayer0cProduction: calls MeetingEngine._ensure_agenda_decomposed()
  - TestLayerCProduction: calls MeetingEngine._gap_refetch_for_null_actuators()

Run with:
  python3 -m pytest backend/tests/services/orchestration/test_progressive_tool_discovery.py -v
"""

import sys
import os
import asyncio
import json
import inspect
from types import SimpleNamespace
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call

# 4 levels up: orchestration/ -> services/ -> tests/ -> backend/ -> repo root
_REPO_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
sys.path.insert(0, os.path.abspath(_REPO_ROOT))
# Also add backend/ so `from app.*` imports work (mirrors Docker PYTHONPATH)
sys.path.insert(0, os.path.abspath(os.path.join(_REPO_ROOT, "backend")))


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


def _make_engine_stub(**overrides):
    """Build a minimal MeetingEngine-shaped object for method testing.

    Returns an object with the right attributes for _ensure_agenda_decomposed()
    and _gap_refetch_for_null_actuators() to work.
    """
    from backend.app.services.orchestration.meeting.engine import MeetingEngine

    session = MagicMock()
    session.id = overrides.get("session_id", "test-session")
    session.workspace_id = overrides.get("workspace_id", "ws-test")
    session.agenda = overrides.get("agenda", ["single item"])

    store = MagicMock()
    store.update = MagicMock()

    engine = object.__new__(MeetingEngine)
    engine.session = session
    engine.session_store = store
    engine.model_name = overrides.get("model_name", "test-model")
    engine.executor_runtime = overrides.get("executor_runtime")
    engine._rag_tool_cache = overrides.get("rag_cache", [])
    engine._has_workspace_tool_bindings = MagicMock(
        return_value=overrides.get("has_bindings", False)
    )
    # Stub _verb_augment and _build_action_items
    engine._verb_augment = MagicMock(return_value="search find")
    engine._build_action_items = AsyncMock(
        return_value=overrides.get("retry_items", [])
    )
    return engine


def _mock_tool_embedding_service(matches=None):
    service = MagicMock()
    service.search_rrf = AsyncMock(return_value=(matches or [], None))
    return service


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

    @pytest.mark.asyncio
    async def test_executor_runtime_skips_provider_initialization(self):
        from backend.app.services.conversation.pipeline_meeting import _decompose_agenda

        result = await _decompose_agenda(
            "Research autonomic nervous system studies and create IG posts",
            model_name="gemini-2.5-pro",
            executor_runtime="gemini_cli",
        )

        assert result == [
            "Research autonomic nervous system studies and create IG posts"
        ]


# ---------------------------------------------------------------------------
# TestModelNamePlumbing
# ---------------------------------------------------------------------------


class TestModelNamePlumbing:
    """Verify model_name flows through ensure_meeting_session."""

    @pytest.mark.asyncio
    async def test_model_name_forwarded_on_new_session(self):
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
            _, kwargs = mock_decompose.call_args
            assert kwargs["model_name"] == "gemini-2.5-pro"
            assert kwargs["executor_runtime"] is None

    @pytest.mark.asyncio
    async def test_model_name_forwarded_on_reuse(self):
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
            _, kwargs = mock_decompose.call_args
            assert kwargs["model_name"] == "claude-3-5-sonnet"
            assert kwargs["executor_runtime"] is None


# ---------------------------------------------------------------------------
# TestLayer0cProduction — calls real MeetingEngine._ensure_agenda_decomposed()
# ---------------------------------------------------------------------------


class TestLayer0cProduction:
    """Test Layer 0c by calling the real engine method."""

    @pytest.mark.asyncio
    async def test_decomposes_single_item_agenda(self):
        """Single-item agenda should be decomposed and persisted."""
        engine = _make_engine_stub(agenda=["single item"])

        with patch(
            "backend.app.services.conversation.pipeline_meeting._decompose_agenda",
            new_callable=AsyncMock,
            return_value=["sub A", "sub B", "sub C"],
        ) as mock_decompose:
            result = await engine._ensure_agenda_decomposed(
                "A message long enough to decompose into sub-tasks"
            )

        assert result is True
        assert engine.session.agenda == ["sub A", "sub B", "sub C"]
        engine.session_store.update.assert_called_once_with(engine.session)
        _, kwargs = mock_decompose.call_args
        assert kwargs["model_name"] == "test-model"
        assert kwargs["executor_runtime"] is None

    @pytest.mark.asyncio
    async def test_skips_multi_item_agenda(self):
        """Already-decomposed agenda (>1 items) should be left alone."""
        engine = _make_engine_stub(agenda=["item 1", "item 2", "item 3"])

        result = await engine._ensure_agenda_decomposed(
            "Some long message that would normally trigger decomposition"
        )

        assert result is False
        assert engine.session.agenda == ["item 1", "item 2", "item 3"]
        engine.session_store.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_short_message(self):
        """Short messages should not trigger decomposition."""
        engine = _make_engine_stub(agenda=["single"])

        result = await engine._ensure_agenda_decomposed("hi")

        assert result is False
        engine.session_store.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_passes_model_name(self):
        """Should forward engine.model_name to _decompose_agenda."""
        engine = _make_engine_stub(
            agenda=["single"],
            model_name="gemini-2.5-pro",
        )

        with patch(
            "backend.app.services.conversation.pipeline_meeting._decompose_agenda",
            new_callable=AsyncMock,
            return_value=["x", "y"],
        ) as mock_decompose:
            await engine._ensure_agenda_decomposed(
                "A sufficiently long message for decomposition"
            )

        mock_decompose.assert_awaited_once()
        _, kwargs = mock_decompose.call_args
        assert kwargs["model_name"] == "gemini-2.5-pro"

    @pytest.mark.asyncio
    async def test_passes_executor_runtime(self):
        """Should forward executor_runtime to _decompose_agenda."""
        engine = _make_engine_stub(
            agenda=["single"],
            model_name="gemini-2.5-pro",
            executor_runtime="gemini_cli",
        )

        with patch(
            "backend.app.services.conversation.pipeline_meeting._decompose_agenda",
            new_callable=AsyncMock,
            return_value=["x", "y"],
        ) as mock_decompose:
            await engine._ensure_agenda_decomposed(
                "A sufficiently long message for decomposition"
            )

        _, kwargs = mock_decompose.call_args
        assert kwargs["executor_runtime"] == "gemini_cli"

    @pytest.mark.asyncio
    async def test_fallback_single_item_returns_false(self):
        """If decomposition returns <=1 items, nothing should change."""
        engine = _make_engine_stub(agenda=["single item"])

        with patch(
            "backend.app.services.conversation.pipeline_meeting._decompose_agenda",
            new_callable=AsyncMock,
            return_value=["single item"],
        ):
            result = await engine._ensure_agenda_decomposed(
                "A message that decompose fails to split"
            )

        assert result is False
        engine.session_store.update.assert_not_called()


# ---------------------------------------------------------------------------
# TestLayerCProduction — calls real MeetingEngine._gap_refetch_for_null_actuators()
# ---------------------------------------------------------------------------


class TestLayerCProduction:
    """Test Layer C by calling the real engine method."""

    @pytest.mark.asyncio
    async def test_enriches_cache_and_retries(self):
        """Null-actuator items should trigger RAG re-fetch and retry."""
        items = [
            {
                "title": "Research papers",
                "tool_name": "frontier.fetch",
                "playbook_code": None,
            },
            {"title": "Create posts", "tool_name": None, "playbook_code": None},
        ]
        # Retry returns improved items
        retry_items = [
            {
                "title": "Research papers",
                "tool_name": "frontier.fetch",
                "playbook_code": None,
            },
            {
                "title": "Create posts",
                "tool_name": "content.gen",
                "playbook_code": None,
            },
        ]
        engine = _make_engine_stub(
            rag_cache=[{"tool_id": "t-existing"}],
            has_bindings=True,
            retry_items=retry_items,
        )

        mock_hits = AsyncMock(
            return_value=[
                {"tool_id": "t-new1"},
                {"tool_id": "t-existing"},  # duplicate, should be skipped
            ]
        )

        with (
            patch(
                "backend.app.services.tool_rag.retrieve_relevant_tools",
                mock_hits,
            ),
            patch(
                "app.services.tool_embedding_service.ToolEmbeddingService",
                return_value=_mock_tool_embedding_service(),
            ),
        ):
            result = await engine._gap_refetch_for_null_actuators(items)

        # Should have enriched cache with 1 new tool (deduped)
        assert len(engine._rag_tool_cache) == 2  # existing + t-new1
        # Result should be the improved retry list
        assert result[1]["tool_name"] == "content.gen"
        assert engine._build_action_items.await_count == 1

    @pytest.mark.asyncio
    async def test_skips_when_no_gaps(self):
        """All-bound items should skip re-fetch entirely."""
        items = [
            {"title": "A", "tool_name": "t1", "playbook_code": None},
            {"title": "B", "tool_name": None, "playbook_code": "pb1"},
        ]
        engine = _make_engine_stub(
            rag_cache=[{"tool_id": "t1"}],
            has_bindings=True,
        )

        result = await engine._gap_refetch_for_null_actuators(items)

        assert result is items  # unchanged, same object
        engine._build_action_items.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skips_when_no_tool_context(self):
        """Without RAG cache or bindings, should skip even with gaps."""
        items = [
            {"title": "A", "tool_name": None, "playbook_code": None},
        ]
        engine = _make_engine_stub(
            rag_cache=[],
            has_bindings=False,
        )

        result = await engine._gap_refetch_for_null_actuators(items)

        assert result is items
        engine._build_action_items.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_keeps_original_if_retry_not_better(self):
        """If retry doesn't improve binding, keep original items."""
        items = [
            {"title": "A", "tool_name": "t1", "playbook_code": None},
            {"title": "B", "tool_name": None, "playbook_code": None},
        ]
        # Retry returns same quality (no improvement)
        retry_items = [
            {"title": "A", "tool_name": "t1", "playbook_code": None},
            {"title": "B", "tool_name": None, "playbook_code": None},
        ]
        engine = _make_engine_stub(
            rag_cache=[{"tool_id": "t1"}],
            has_bindings=True,
            retry_items=retry_items,
        )

        mock_hits = AsyncMock(return_value=[{"tool_id": "t-new"}])

        with (
            patch(
                "backend.app.services.tool_rag.retrieve_relevant_tools",
                mock_hits,
            ),
            patch(
                "app.services.tool_embedding_service.ToolEmbeddingService",
                return_value=_mock_tool_embedding_service(),
            ),
        ):
            result = await engine._gap_refetch_for_null_actuators(items)

        # Result should be original items since retry didn't improve
        assert result is items

    @pytest.mark.asyncio
    async def test_deduplicates_rag_cache(self):
        """New hits with existing tool_ids should not be added to cache."""
        items = [
            {"title": "Draft content", "tool_name": None, "playbook_code": None},
        ]
        engine = _make_engine_stub(
            rag_cache=[{"tool_id": "t1"}, {"tool_id": "t2"}],
            has_bindings=True,
            retry_items=[],
        )

        mock_hits = AsyncMock(
            return_value=[
                {"tool_id": "t2"},  # already in cache
                {"tool_id": "t3"},  # new
            ]
        )

        with (
            patch(
                "backend.app.services.tool_rag.retrieve_relevant_tools",
                mock_hits,
            ),
            patch(
                "app.services.tool_embedding_service.ToolEmbeddingService",
                return_value=_mock_tool_embedding_service(),
            ),
        ):
            await engine._gap_refetch_for_null_actuators(items)

        cache_ids = [t["tool_id"] for t in engine._rag_tool_cache]
        assert cache_ids.count("t2") == 1  # not duplicated
        assert "t3" in cache_ids
        assert len(engine._rag_tool_cache) == 3

    @pytest.mark.asyncio
    async def test_timeout_keeps_original_without_retry(self):
        """Layer-C timeout should not block the pipeline or force a retry."""
        items = [
            {
                "title": "Draft partner brief",
                "tool_name": None,
                "playbook_code": None,
            }
        ]
        engine = _make_engine_stub(
            rag_cache=[{"tool_id": "t-existing"}],
            has_bindings=True,
            retry_items=[],
        )
        engine.LAYER_C_TOOL_QUERY_TIMEOUT_S = 0.01
        engine.LAYER_C_TOOL_TOTAL_BUDGET_S = 0.02

        async def _slow_hits(*args, **kwargs):
            await asyncio.sleep(0.05)
            return [{"tool_id": "t-late"}]

        with (
            patch(
                "backend.app.services.tool_rag.retrieve_relevant_tools",
                AsyncMock(side_effect=_slow_hits),
            ) as mock_hits,
            patch(
                "app.services.tool_embedding_service.ToolEmbeddingService",
                return_value=_mock_tool_embedding_service(),
            ),
        ):
            result = await engine._gap_refetch_for_null_actuators(items)

        assert result is items
        assert mock_hits.await_count == 1
        engine._build_action_items.assert_not_awaited()
        assert engine._rag_tool_cache == [{"tool_id": "t-existing"}]

    @pytest.mark.asyncio
    async def test_playbook_gap_fill_skips_items_with_tool_binding(self):
        """Playbook gap-fill should skip items that already have a tool binding."""
        items = [
            {
                "title": "Fetch partner facts",
                "tool_name": "frontier.fetch",
                "playbook_code": None,
            },
            {
                "title": "Save partner brief",
                "tool_name": None,
                "playbook_code": None,
            },
        ]
        retry_items = [
            {
                "title": "Fetch partner facts",
                "tool_name": "frontier.fetch",
                "playbook_code": None,
            },
            {
                "title": "Save partner brief",
                "tool_name": None,
                "playbook_code": "pb.write_markdown",
            },
        ]
        engine = _make_engine_stub(
            rag_cache=[{"tool_id": "t-existing"}],
            has_bindings=True,
            retry_items=retry_items,
        )
        embedding_service = _mock_tool_embedding_service(
            [
                SimpleNamespace(
                    category="playbook",
                    tool_id="pb.write_markdown",
                    display_name="Write Markdown",
                    description="Save markdown output",
                )
            ]
        )

        with (
            patch(
                "backend.app.services.tool_rag.retrieve_relevant_tools",
                AsyncMock(return_value=[]),
            ),
            patch(
                "app.services.tool_embedding_service.ToolEmbeddingService",
                return_value=embedding_service,
            ),
        ):
            result = await engine._gap_refetch_for_null_actuators(items)

        assert result[1]["playbook_code"] == "pb.write_markdown"
        embedding_service.search_rrf.assert_awaited_once()
        _, kwargs = embedding_service.search_rrf.call_args
        assert kwargs["query"] == "Save partner brief"
        assert engine._build_action_items.await_count == 1


class TestAgendaRagProduction:
    """Test agenda/tool prefetch guardrails in the real engine stage."""

    @pytest.mark.asyncio
    async def test_stage_agenda_and_rag_timeout_continues_pipeline(self):
        engine = _make_engine_stub(
            agenda=["整理合作方向", "列出立即下一步", "輸出 markdown brief"],
        )
        engine.AGENDA_RAG_QUERY_TIMEOUT_S = 0.01
        engine.AGENDA_RAG_TOTAL_BUDGET_S = 0.03
        engine._emit_meeting_stage = AsyncMock()
        engine._ensure_agenda_decomposed = AsyncMock(return_value=False)
        engine._build_tool_query_from_context = MagicMock(
            return_value="context query"
        )

        async def _slow_hits(*args, **kwargs):
            await asyncio.sleep(0.05)
            return [{"tool_id": "t-late"}]

        with patch(
            "backend.app.services.tool_rag.retrieve_relevant_tools",
            AsyncMock(side_effect=_slow_hits),
        ) as mock_hits:
            await engine._stage_agenda_and_rag("請產出 partner brief")

        assert mock_hits.await_count >= 1
        assert engine._rag_tool_cache == []
        engine._emit_meeting_stage.assert_has_awaits(
            [
                call("agenda", "Analyzing agenda..."),
                call("tool_discovery", "Discovering available tools..."),
            ]
        )
        engine._ensure_agenda_decomposed.assert_awaited_once_with(
            "請產出 partner brief"
        )

    @pytest.mark.asyncio
    async def test_stage_agenda_and_rag_respects_total_budget(self):
        engine = _make_engine_stub(
            agenda=["A", "B", "C"],
        )
        engine.AGENDA_RAG_QUERY_TIMEOUT_S = 1.0
        engine.AGENDA_RAG_TOTAL_BUDGET_S = 10.0
        engine._emit_meeting_stage = AsyncMock()
        engine._ensure_agenda_decomposed = AsyncMock(return_value=False)
        engine._build_tool_query_from_context = MagicMock(
            return_value="context query"
        )
        engine._layer_c_remaining_budget = MagicMock(
            side_effect=[1.0, 0.0, 0.0, 0.0]
        )

        with patch(
            "backend.app.services.tool_rag.retrieve_relevant_tools",
            AsyncMock(return_value=[]),
        ) as mock_hits:
            await engine._stage_agenda_and_rag("user message")

        assert mock_hits.await_count == 1
        assert engine._rag_tool_cache == []
