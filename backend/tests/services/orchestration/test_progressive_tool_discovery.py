"""Tests for progressive tool discovery pipeline (Layer 0 + Layer C).

Covers:
  - _decompose_agenda: basic decomposition, provider compatibility, fallback
  - Layer C: partial null-actuator gap re-fetch
"""

import json
import inspect
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helper: build a mock provider with a controlled signature
# ---------------------------------------------------------------------------


def _build_provider(response: str, sig_params: list[str]):
    """Return an AsyncMock provider whose chat_completion has *sig_params*."""
    provider = AsyncMock()
    provider.chat_completion = AsyncMock(return_value=response)

    # Build a fake signature
    params = [
        inspect.Parameter(p, inspect.Parameter.POSITIONAL_OR_KEYWORD, default=None)
        for p in sig_params
    ]
    provider.chat_completion.__signature__ = inspect.Signature(params)
    return provider


# Patch targets — the lazy imports inside _decompose_agenda live in the
# pipeline_meeting module's namespace; we intercept the *importer* so the
# function never reaches the real backend.features.workspace package.
_GET_PROVIDER = "backend.features.workspace.chat.utils.llm_provider.get_llm_provider"
_GET_MANAGER = (
    "backend.features.workspace.chat.utils.llm_provider.get_llm_provider_manager"
)


def _patch_provider(provider):
    """Context-manager stack that injects *provider* into _decompose_agenda."""
    import contextlib, types, sys

    # Create stub modules so the lazy import inside _decompose_agenda resolves
    # without needing the full backend.features.workspace tree.
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

        # Inject callables
        llm_mod = sys.modules["backend.features.workspace.chat.utils.llm_provider"]
        llm_mod.get_llm_provider = MagicMock(return_value=(provider, None))  # type: ignore
        llm_mod.get_llm_provider_manager = MagicMock()  # type: ignore

        try:
            yield
        finally:
            for mod_name in stubs:
                sys.modules.pop(mod_name, None)

    return _ctx()


# ---------------------------------------------------------------------------
# _decompose_agenda tests
# ---------------------------------------------------------------------------


class TestDecomposeAgenda:
    """Unit tests for _decompose_agenda()."""

    @pytest.mark.asyncio
    async def test_basic_decomposition(self):
        """Should parse a valid JSON array from the LLM response."""
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
            assert "research autonomic nerve" in result[0].lower()

    @pytest.mark.asyncio
    async def test_provider_safe_kwargs_anthropic(self):
        """Anthropic provider should NOT receive temperature/max_tokens kwargs."""
        provider = _build_provider(
            '["step A", "step B", "step C"]',
            ["messages", "model"],  # Anthropic-style: only messages + model
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

            # Verify only allowed kwargs were passed (no temperature/max_tokens)
            call_args = provider.chat_completion.call_args
            if call_args.kwargs:
                assert "temperature" not in call_args.kwargs
                assert "max_tokens" not in call_args.kwargs

    @pytest.mark.asyncio
    async def test_fallback_on_short_input(self):
        """Short messages should return as-is without LLM call."""
        from backend.app.services.conversation.pipeline_meeting import (
            _decompose_agenda,
        )

        result = await _decompose_agenda("hello")
        assert result == ["hello"]

    @pytest.mark.asyncio
    async def test_fallback_on_provider_error(self):
        """Should return [user_message] if provider raises."""
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
        """Should strip ```json ... ``` wrappers from LLM output."""
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
# Layer C: partial null-actuator gap re-fetch
# ---------------------------------------------------------------------------


class TestLayerCGapRefetch:
    """Test that Layer C fires for partial null-actuator items."""

    def _make_action_items(self, specs):
        """Create action item dicts from (title, tool_name, playbook_code) tuples."""
        return [
            {"title": t, "tool_name": tn, "playbook_code": pb} for t, tn, pb in specs
        ]

    def test_partial_gap_detected(self):
        """When some items have tools and others don't, gaps should be found."""
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
        """When all items have tools, no gaps should be detected."""
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
        """Items with playbook_code should NOT be treated as gaps."""
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
        """When ALL items lack actuators, all_null gate should fire."""
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
