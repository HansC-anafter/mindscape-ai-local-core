import asyncio

from backend.app.services import tool_embedding_service
from backend.app.services.tool_embedding_service import (
    RAG_HIT,
    ToolEmbeddingService,
    ToolMatch,
)


def test_index_all_tools_facade_delegates_include_playbooks(monkeypatch):
    calls = []

    async def fake_index_all_tools(service, *, include_playbooks=True):
        calls.append((service, include_playbooks))
        return 7

    monkeypatch.setattr(
        tool_embedding_service,
        "_index_all_tools",
        fake_index_all_tools,
    )

    service = ToolEmbeddingService(postgres_config={"database": "unused"})
    result = asyncio.run(service.index_all_tools(include_playbooks=False))

    assert result == 7
    assert calls == [(service, False)]


def test_search_rrf_uses_facade_methods_without_live_resources():
    service = ToolEmbeddingService(postgres_config={"database": "unused"})

    async def fake_generate_embedding(query, *, is_query=True):
        assert query == "render clip"
        assert is_query is True
        return [0.1, 0.2], "primary"

    async def fake_get_indexed_models():
        return ["primary", "secondary"]

    async def fake_generate_embedding_for_model(query, model_name, *, is_query=True):
        assert query == "render clip"
        assert model_name == "secondary"
        assert is_query is True
        return [0.3, 0.4], model_name

    async def fake_search_single_model(query_embedding, model_name, top_k, min_score=0.0):
        assert top_k == 4
        if model_name == "primary":
            return [
                ToolMatch(
                    tool_id="tool-alpha",
                    display_name="Alpha",
                    description="Primary vector match",
                    category="tool",
                    capability_code="alpha",
                    similarity=0.92,
                )
            ]
        return [
            ToolMatch(
                tool_id="tool-beta",
                display_name="Beta",
                description="Secondary vector match",
                category="tool",
                capability_code="beta",
                similarity=0.88,
            )
        ]

    async def fake_search_bm25(query, top_k=15):
        assert query == "render clip"
        assert top_k == 4
        return [
            ToolMatch(
                tool_id="tool-beta",
                display_name="Beta",
                description="BM25 match",
                category="tool",
                capability_code="beta",
                similarity=1.0,
            )
        ]

    service._generate_embedding = fake_generate_embedding
    service.get_indexed_models = fake_get_indexed_models
    service._generate_embedding_for_model = fake_generate_embedding_for_model
    service._search_single_model = fake_search_single_model
    service.search_bm25 = fake_search_bm25

    matches, status = asyncio.run(
        service.search_rrf("render clip", top_k=2, min_score=0.3)
    )

    assert status == RAG_HIT
    assert [match.tool_id for match in matches] == ["tool-beta", "tool-alpha"]
