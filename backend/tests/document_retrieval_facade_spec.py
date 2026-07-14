import json

import pytest

from backend.app.services.conversation.context_builder.memory_retriever import (
    _format_document_hit,
)
from backend.app.services.document_retrieval_facade import DocumentRetrievalFacade


def _row(identifier="row-1"):
    return {
        "id": identifier,
        "source_id": "doc-1:rev-1:chunk-1",
        "content": "A cited architecture statement.",
        "metadata": {
            "workspace_id": "workspace-1",
            "document_id": "doc-1",
            "revision_id": "rev-1",
            "chunk_id": "chunk-1",
            "node_ids": ["node-1"],
            "source_locations": [
                {
                    "page_or_slide": 2,
                    "bounds": {"x": 1, "y": 2, "width": 3, "height": 4},
                }
            ],
            "schema_version": "document_schema.v1",
            "index_version": "document-index.v1",
            "file_name": "architecture.pdf",
            "heading_path": ["System", "Data plane"],
        },
    }


class FakeVectorService:
    def __init__(self, error=None):
        self.error = error

    async def _generate_embedding_with_model(self, _text, *, is_query):
        assert is_query is True
        if self.error:
            raise self.error
        return [0.1, 0.2], "bge-m3"


class FakeCursor:
    def __init__(self, vector_rows, keyword_rows):
        self.vector_rows = vector_rows
        self.keyword_rows = keyword_rows
        self.current = []
        self.calls = []

    def execute(self, query, params=None):
        self.calls.append((query, params))
        self.current = self.vector_rows if "vector_score" in query else self.keyword_rows

    def fetchall(self):
        return self.current


class FakeConnection:
    def __init__(self, cursor):
        self.cursor_obj = cursor
        self.closed = False

    def cursor(self, **_kwargs):
        return self.cursor_obj

    def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_hybrid_retrieval_prefilters_workspace_before_both_limits():
    cursor = FakeCursor([_row()], [_row()])
    connection = FakeConnection(cursor)
    facade = DocumentRetrievalFacade(
        vector_service=FakeVectorService(),
        connection_factory=lambda: connection,
    )

    hits = await facade.search(
        query="architecture",
        user_id="user-1",
        workspace_id="workspace-1",
        top_k=5,
    )

    assert len(cursor.calls) == 2
    for query, params in cursor.calls:
        assert "source_app = %s" in query
        assert "metadata @> %s::jsonb" in query
        assert query.index("metadata @> %s::jsonb") < query.index("LIMIT %s")
        metadata_param = next(
            value
            for value in params
            if isinstance(value, str) and value.startswith("{")
        )
        assert json.loads(metadata_param) == {
            "workspace_id": "workspace-1",
            "active": True,
        }
    assert connection.closed is True
    assert hits[0]["channels"] == ["text_vector", "keyword"]
    assert hits[0]["citation"]["chunk_id"] == "chunk-1"
    assert hits[0]["source_label"] == "architecture.pdf"


@pytest.mark.asyncio
async def test_keyword_retrieval_survives_embedding_outage():
    cursor = FakeCursor([], [_row()])
    connection = FakeConnection(cursor)
    facade = DocumentRetrievalFacade(
        vector_service=FakeVectorService(error=RuntimeError("offline")),
        connection_factory=lambda: connection,
    )

    hits = await facade.search(
        query="architecture",
        user_id="user-1",
        workspace_id="workspace-1",
        top_k=3,
    )

    assert len(cursor.calls) == 1
    assert "keyword_score" in cursor.calls[0][0]
    assert hits[0]["channels"] == ["keyword"]


def test_memory_context_formatter_preserves_exact_citation_location():
    hit = {
        "source_label": "architecture.pdf",
        "heading_path": ["System", "Data plane"],
        "retrievable_text": "A cited architecture statement.",
        "citation": {
            "document_id": "doc-1",
            "chunk_id": "chunk-1",
            "source_locations": _row()["metadata"]["source_locations"],
        },
    }

    formatted = _format_document_hit(hit)

    assert "architecture.pdf" in formatted
    assert "System > Data plane" in formatted
    assert "page/slide 2" in formatted
    assert "bbox(1,2,3,4)" in formatted
    assert "chunk chunk-1" in formatted
