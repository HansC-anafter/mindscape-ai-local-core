import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.tests.services.orchestration.progressive_tool_discovery_test_support import (
    make_engine_stub,
)


@pytest.mark.asyncio
async def test_enriches_cache_and_binds_without_retry():
    items = [
        {
            "title": "Research papers",
            "tool_name": "frontier.fetch",
            "playbook_code": None,
        },
        {"title": "Create posts", "tool_name": None, "playbook_code": None},
    ]
    engine = make_engine_stub(
        rag_cache=[{"tool_id": "t-existing"}],
        has_bindings=True,
    )

    mock_hits = AsyncMock(
        return_value=[
            {"tool_id": "content.gen"},
            {"tool_id": "t-existing"},
        ]
    )

    with patch(
        "backend.app.services.tool_rag.retrieve_relevant_tools",
        mock_hits,
    ):
        result = await engine._gap_refetch_for_null_actuators(items)

    assert len(engine._rag_tool_cache) == 2
    assert result[1]["tool_name"] == "content.gen"
    assert result[1]["binding_source"] == "layer_c_tool_gap_fill"
    engine._build_action_items.assert_not_awaited()


@pytest.mark.asyncio
async def test_skips_when_no_gaps():
    items = [
        {"title": "A", "tool_name": "t1", "playbook_code": None},
        {"title": "B", "tool_name": None, "playbook_code": "pb1"},
    ]
    engine = make_engine_stub(
        rag_cache=[{"tool_id": "t1"}],
        has_bindings=True,
    )

    result = await engine._gap_refetch_for_null_actuators(items)

    assert result is items
    engine._build_action_items.assert_not_awaited()


@pytest.mark.asyncio
async def test_skips_when_no_tool_context():
    items = [
        {"title": "A", "tool_name": None, "playbook_code": None},
    ]
    engine = make_engine_stub(
        rag_cache=[],
        has_bindings=False,
    )

    result = await engine._gap_refetch_for_null_actuators(items)

    assert result is items
    engine._build_action_items.assert_not_awaited()


@pytest.mark.asyncio
async def test_keeps_original_if_gap_search_finds_no_binding():
    items = [
        {"title": "A", "tool_name": "t1", "playbook_code": None},
        {"title": "B", "tool_name": None, "playbook_code": None},
    ]
    engine = make_engine_stub(
        rag_cache=[{"tool_id": "t1"}],
        has_bindings=True,
    )

    mock_hits = AsyncMock(return_value=[])

    with patch(
        "backend.app.services.tool_rag.retrieve_relevant_tools",
        mock_hits,
    ):
        result = await engine._gap_refetch_for_null_actuators(items)

    assert result is items


@pytest.mark.asyncio
async def test_deduplicates_rag_cache():
    items = [
        {"title": "Draft content", "tool_name": None, "playbook_code": None},
    ]
    engine = make_engine_stub(
        rag_cache=[{"tool_id": "t1"}, {"tool_id": "t2"}],
        has_bindings=True,
        retry_items=[],
    )

    mock_hits = AsyncMock(
        return_value=[
            {"tool_id": "t2"},
            {"tool_id": "t3"},
        ]
    )

    with patch(
        "backend.app.services.tool_rag.retrieve_relevant_tools",
        mock_hits,
    ):
        await engine._gap_refetch_for_null_actuators(items)

    cache_ids = [tool["tool_id"] for tool in engine._rag_tool_cache]
    assert cache_ids.count("t2") == 1
    assert "t3" in cache_ids
    assert len(engine._rag_tool_cache) == 3


@pytest.mark.asyncio
async def test_binds_playbook_without_executor_retry():
    items = [
        {"title": "Storyboard preview", "tool_name": None, "playbook_code": None},
    ]
    engine = make_engine_stub(
        rag_cache=[{"tool_id": "t-existing"}],
        has_bindings=True,
    )

    fake_embedding_service = MagicMock()
    fake_embedding_service.search_rrf = AsyncMock(
        return_value=(
            [
                SimpleNamespace(
                    category="playbook",
                    tool_id="pd_execute_storyboard_preview",
                    display_name="Storyboard Preview Run",
                    description="Run storyboard preview through MMS",
                )
            ],
            None,
        )
    )
    stub_module = types.ModuleType("app.services.tool_embedding_service")
    stub_module.ToolEmbeddingService = MagicMock(return_value=fake_embedding_service)

    with (
        patch(
            "backend.app.services.tool_rag.retrieve_relevant_tools",
            AsyncMock(return_value=[]),
        ),
        patch.dict(
            sys.modules,
            {"app.services.tool_embedding_service": stub_module},
        ),
    ):
        result = await engine._gap_refetch_for_null_actuators(items)

    assert result[0]["playbook_code"] == "pd_execute_storyboard_preview"
    assert result[0]["engine"] == "playbook:pd_execute_storyboard_preview"
    assert result[0]["binding_source"] == "layer_c_playbook_gap_fill"
    engine._build_action_items.assert_not_awaited()
