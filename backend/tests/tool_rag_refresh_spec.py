import asyncio

from backend.app.services import tool_embedding_service
from backend.app.services.tool_rag_refresh import refresh_tool_rag_corpus


def test_refresh_tool_rag_corpus_can_skip_playbook_indexing(monkeypatch):
    calls = []

    class FakeToolEmbeddingService:
        async def ensure_table(self):
            calls.append(("ensure_table", None))

        async def has_existing_index(self):
            calls.append(("has_existing_index", None))
            return False

        async def ensure_indexed(self, *, include_playbooks=True):
            calls.append(("ensure_indexed", include_playbooks))
            return 3

    monkeypatch.setattr(
        tool_embedding_service,
        "ToolEmbeddingService",
        FakeToolEmbeddingService,
    )

    service, indexed_count, mode = asyncio.run(
        refresh_tool_rag_corpus(include_playbooks=False)
    )

    assert isinstance(service, FakeToolEmbeddingService)
    assert indexed_count == 3
    assert mode == "ensure_indexed"
    assert calls == [
        ("ensure_table", None),
        ("ensure_indexed", False),
    ]


def test_refresh_tool_rag_corpus_skips_existing_post_ready_index(monkeypatch):
    calls = []

    class FakeToolEmbeddingService:
        async def ensure_table(self):
            calls.append(("ensure_table", None))

        async def has_existing_index(self):
            calls.append(("has_existing_index", None))
            return True

        async def ensure_indexed(self, *, include_playbooks=True):
            calls.append(("ensure_indexed", include_playbooks))
            return 3

    monkeypatch.setattr(
        tool_embedding_service,
        "ToolEmbeddingService",
        FakeToolEmbeddingService,
    )

    service, indexed_count, mode = asyncio.run(
        refresh_tool_rag_corpus(
            include_playbooks=False,
            skip_when_index_exists=True,
        )
    )

    assert isinstance(service, FakeToolEmbeddingService)
    assert indexed_count == 0
    assert mode == "existing_index_skip"
    assert calls == [
        ("ensure_table", None),
        ("has_existing_index", None),
    ]
