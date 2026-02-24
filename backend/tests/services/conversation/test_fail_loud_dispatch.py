"""
Tests for P0 Fail-Loud Dispatch.

Covers:
- dispatch_to_agent: unavailable/failed agent ± fallback_model
- dispatch_to_llm: no model configured => fail-loud
- plan_builder: _select_model_for_plan raises ValueError
- SSE events: is_fallback in chunk events
- Migration script metadata
"""

import json
import sys
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from types import SimpleNamespace

BACKEND_DIR = Path(__file__).parent.parent.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.append(str(BACKEND_DIR))
PROJECT_ROOT = BACKEND_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))


def _ws(fallback_model=None):
    ws = MagicMock()
    ws.fallback_model = fallback_model
    ws.executor_runtime = "gemini-cli"
    ws.metadata = {}
    return ws


def _result():
    return SimpleNamespace(
        success=True, error=None, full_text="", meeting_session_id=None
    )


# Patch targets (source modules, because lazy import inside function body)
_AGENT_EXEC_SRC = "backend.app.services.workspace_agent_executor.WorkspaceAgentExecutor"
_SETTINGS_SRC_DISPATCH = (
    "backend.app.services.system_settings_store.SystemSettingsStore"
)
_SETTINGS_SRC_PLAN = "backend.app.services.system_settings_store.SystemSettingsStore"


class TestAgentUnavailableFallback:

    @pytest.mark.asyncio
    async def test_no_fallback_fails_loud(self):
        from backend.app.services.conversation.pipeline_dispatch import (
            dispatch_to_agent,
        )

        ws = _ws(fallback_model=None)
        result = _result()

        with patch(_AGENT_EXEC_SRC) as MockExec:
            inst = AsyncMock()
            inst.check_agent_available = AsyncMock(return_value=False)
            MockExec.return_value = inst

            ret = await dispatch_to_agent(
                workspace_id="ws",
                profile_id="p",
                thread_id="t",
                project_id="pj",
                message="hi",
                user_event_id="ev",
                executor_runtime="gemini-cli",
                context_str="",
                store=MagicMock(),
                workspace=ws,
                result=result,
                emit_pipeline_stage=AsyncMock(),
            )
        assert ret.success is False
        assert "unavailable" in ret.error.lower()

    @pytest.mark.asyncio
    async def test_with_fallback_dispatches_llm(self):
        from backend.app.services.conversation.pipeline_dispatch import (
            dispatch_to_agent,
        )

        ws = _ws(fallback_model="gemini-1.5-flash")
        result = _result()

        with patch(_AGENT_EXEC_SRC) as MockExec:
            inst = AsyncMock()
            inst.check_agent_available = AsyncMock(return_value=False)
            MockExec.return_value = inst

            with patch(
                "backend.app.services.conversation.pipeline_dispatch.dispatch_to_llm",
                new_callable=AsyncMock,
            ) as mock_llm:
                mock_llm.return_value = result
                await dispatch_to_agent(
                    workspace_id="ws",
                    profile_id="p",
                    thread_id="t",
                    project_id="pj",
                    message="hi",
                    user_event_id="ev",
                    executor_runtime="gemini-cli",
                    context_str="",
                    store=MagicMock(),
                    workspace=ws,
                    result=result,
                    emit_pipeline_stage=AsyncMock(),
                )
                mock_llm.assert_called_once()
                kw = mock_llm.call_args.kwargs
                assert kw["model_name"] == "gemini-1.5-flash"
                assert kw["is_fallback"] is True


class TestAgentFailedFallback:

    @pytest.mark.asyncio
    async def test_no_fallback_fails_loud(self):
        from backend.app.services.conversation.pipeline_dispatch import (
            dispatch_to_agent,
        )

        ws = _ws(fallback_model=None)
        result = _result()
        resp = SimpleNamespace(
            success=False,
            error="timeout",
            output="",
            execution_time_seconds=0,
            trace_id=None,
        )

        with patch(_AGENT_EXEC_SRC) as MockExec:
            inst = AsyncMock()
            inst.check_agent_available = AsyncMock(return_value=True)
            inst.execute = AsyncMock(return_value=resp)
            MockExec.return_value = inst

            ret = await dispatch_to_agent(
                workspace_id="ws",
                profile_id="p",
                thread_id="t",
                project_id="pj",
                message="hi",
                user_event_id="ev",
                executor_runtime="gemini-cli",
                context_str="",
                store=MagicMock(),
                workspace=ws,
                result=result,
                emit_pipeline_stage=AsyncMock(),
            )
        assert ret.success is False
        assert "failed" in ret.error.lower()

    @pytest.mark.asyncio
    async def test_with_fallback_dispatches_llm(self):
        from backend.app.services.conversation.pipeline_dispatch import (
            dispatch_to_agent,
        )

        ws = _ws(fallback_model="gemini-1.5-flash")
        result = _result()
        resp = SimpleNamespace(
            success=False,
            error="crash",
            output="",
            execution_time_seconds=0,
            trace_id=None,
        )

        with patch(_AGENT_EXEC_SRC) as MockExec:
            inst = AsyncMock()
            inst.check_agent_available = AsyncMock(return_value=True)
            inst.execute = AsyncMock(return_value=resp)
            MockExec.return_value = inst

            with patch(
                "backend.app.services.conversation.pipeline_dispatch.dispatch_to_llm",
                new_callable=AsyncMock,
            ) as mock_llm:
                mock_llm.return_value = result
                await dispatch_to_agent(
                    workspace_id="ws",
                    profile_id="p",
                    thread_id="t",
                    project_id="pj",
                    message="hi",
                    user_event_id="ev",
                    executor_runtime="gemini-cli",
                    context_str="",
                    store=MagicMock(),
                    workspace=ws,
                    result=result,
                    emit_pipeline_stage=AsyncMock(),
                )
                mock_llm.assert_called_once()
                kw = mock_llm.call_args.kwargs
                assert kw["model_name"] == "gemini-1.5-flash"
                assert kw["is_fallback"] is True


class TestDispatchToLLMNoModel:

    @pytest.mark.asyncio
    async def test_no_model_configured_fails_loud(self):
        from backend.app.services.conversation.pipeline_dispatch import dispatch_to_llm

        with patch(_SETTINGS_SRC_DISPATCH) as MockSettings:
            inst = MagicMock()
            inst.get_setting.return_value = None
            MockSettings.return_value = inst

            ret = await dispatch_to_llm(
                workspace_id="ws",
                profile_id="p",
                thread_id="t",
                project_id="pj",
                message="hi",
                user_event_id="ev",
                execution_mode="qa",
                model_name=None,
                context_str="",
                store=MagicMock(),
                workspace=_ws(),
                profile=None,
                result=_result(),
            )
        assert ret.success is False
        assert "no chat model" in ret.error.lower()


class TestPlanBuilderFailLoud:

    def test_select_model_raises_when_none_configured(self):
        from backend.app.services.conversation.plan_builder import PlanBuilder

        builder = PlanBuilder.__new__(PlanBuilder)
        builder.model_name = None
        builder.stage_router = None
        builder.capability_profile = None
        builder.store = MagicMock()
        builder.config_store = MagicMock()
        builder.external_backend = None
        builder._external_backend = None
        builder._external_backend_loaded = False
        builder._llm_manager_cache = {}
        builder.default_locale = "en"

        with patch(_SETTINGS_SRC_PLAN) as MockSettings:
            inst = MagicMock()
            inst.get_setting.return_value = None
            MockSettings.return_value = inst

            with pytest.raises(ValueError, match="No chat model configured"):
                builder._select_model_for_plan()


class TestIsFallbackSSEEvents:

    @pytest.mark.asyncio
    async def test_chunk_is_fallback_true(self):
        from backend.features.workspace.chat.streaming.llm_streaming import (
            stream_openai_response,
        )

        provider = AsyncMock()

        async def fake(**kw):
            yield "hello"

        provider.chat_completion_stream = fake

        chunks = []
        async for ev in stream_openai_response(
            provider=provider,
            messages=[{"role": "user", "content": "t"}],
            model_name="m",
            openai_key=None,
            is_fallback=True,
        ):
            chunks.append(ev)

        for c in chunks:
            if c.startswith("data: "):
                d = json.loads(c[6:].strip())
                if d.get("type") == "chunk":
                    assert d["is_fallback"] is True

    @pytest.mark.asyncio
    async def test_chunk_is_fallback_false_default(self):
        from backend.features.workspace.chat.streaming.llm_streaming import (
            stream_openai_response,
        )

        provider = AsyncMock()

        async def fake(**kw):
            yield "hi"

        provider.chat_completion_stream = fake

        chunks = []
        async for ev in stream_openai_response(
            provider=provider,
            messages=[{"role": "user", "content": "t"}],
            model_name="m",
        ):
            chunks.append(ev)

        for c in chunks:
            if c.startswith("data: "):
                d = json.loads(c[6:].strip())
                if d.get("type") == "chunk":
                    assert d["is_fallback"] is False


class TestMigrationSchema:

    def test_migration_file_correct(self):
        p = (
            Path(__file__).parent.parent.parent.parent
            / "alembic_migrations"
            / "postgres"
            / "versions"
            / "20260225000000_doer_fallback_to_fallback_model.py"
        )
        assert p.exists()
        content = p.read_text()
        assert "20260225000000" in content
        assert "fallback_model" in content
        assert "doer_fallback_to_mindscape" in content
        assert "def downgrade" in content
