from pathlib import Path

import pytest

from backend.app.services.vector_search import VectorSearchService
from backend.app.services.vector_search_db import (
    save_external_doc,
    search_vectors,
    update_last_used_at_records,
)


class FakeCursor:
    def __init__(self, rows=None, execute_error=None, fetchone_value=("row-1",)):
        self.rows = rows or [{"id": "row-1", "similarity": 0.91}]
        self.execute_error = execute_error
        self.fetchone_value = fetchone_value
        self.query = None
        self.params = None

    def execute(self, query, params=None):
        self.query = query
        self.params = params
        if self.execute_error:
            raise self.execute_error

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.fetchone_value


class FakeConnection:
    def __init__(self, cursor):
        self.cursor_obj = cursor
        self.closed = False
        self.committed = False
        self.rolled_back = False
        self.cursor_kwargs = None

    def cursor(self, **kwargs):
        self.cursor_kwargs = kwargs
        return self.cursor_obj

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def test_legacy_vector_search_service_import_remains_available():
    service = VectorSearchService(postgres_config={"dbname": "unused"})

    assert service.__class__.__name__ == "VectorSearchService"
    assert hasattr(service, "vector_search")
    assert hasattr(service, "search_external_docs")


@pytest.mark.asyncio
async def test_search_vectors_preserves_filters_limit_and_close():
    cursor = FakeCursor(rows=[{"id": "result-1", "similarity": 0.88}])
    connection = FakeConnection(cursor)

    results = await search_vectors(
        get_connection=lambda: connection,
        table="playbook_knowledge",
        query_embedding=[0.1, 0.2],
        filters={"playbook_code": "weekly_review"},
        top_k=7,
        require_model_match=False,
    )

    assert results == [{"id": "result-1", "similarity": 0.88}]
    assert "FROM playbook_knowledge" in cursor.query
    assert "playbook_code = %s" in cursor.query
    assert "LIMIT %s" in cursor.query
    assert cursor.params == ["[0.1, 0.2]", "weekly_review", "[0.1, 0.2]", 7]
    assert connection.closed is True


@pytest.mark.asyncio
async def test_update_last_used_at_records_skips_empty_ids_without_connection():
    calls = {"connections": 0}

    def get_connection():
        calls["connections"] += 1
        return FakeConnection(FakeCursor())

    await update_last_used_at_records(get_connection, [])

    assert calls["connections"] == 0


@pytest.mark.asyncio
async def test_save_external_doc_commits_and_closes_on_success():
    cursor = FakeCursor(fetchone_value=("doc-1",))
    connection = FakeConnection(cursor)

    result = await save_external_doc(
        get_connection=lambda: connection,
        doc={
            "user_id": "user-1",
            "source_app": "local_folder",
            "source_id": "chunk-1",
            "title": "Chunk 1",
            "content": "hello",
            "embedding": [0.3, 0.4],
            "metadata": {"path": "note.md"},
        },
    )

    assert result is True
    assert "INSERT INTO external_docs" in cursor.query
    assert "ON CONFLICT (user_id, source_app, source_id)" in cursor.query
    assert cursor.params[0:6] == (
        "user-1",
        "local_folder",
        "chunk-1",
        "Chunk 1",
        "hello",
        "[0.3, 0.4]",
    )
    assert connection.committed is True
    assert connection.rolled_back is False
    assert connection.closed is True


@pytest.mark.asyncio
async def test_save_external_doc_rolls_back_and_closes_on_execute_failure():
    cursor = FakeCursor(execute_error=RuntimeError("write failed"))
    connection = FakeConnection(cursor)

    result = await save_external_doc(
        get_connection=lambda: connection,
        doc={
            "title": "Broken",
            "content": "hello",
            "embedding": [0.3, 0.4],
        },
    )

    assert result is False
    assert connection.committed is False
    assert connection.rolled_back is True
    assert connection.closed is True


@pytest.mark.asyncio
async def test_embedding_wrapper_delegates_to_internal_generator():
    class FakeEmbeddingGenerator:
        async def generate_embedding(self, text):
            return [float(len(text))]

    service = VectorSearchService(postgres_config={"dbname": "unused"})
    service.embedding_generator = FakeEmbeddingGenerator()

    assert await service._generate_embedding("hello") == [5.0]


def test_helper_modules_do_not_define_duplicate_resource_surfaces():
    repo_root = Path(__file__).resolve().parents[3]
    helper_paths = [
        repo_root / "backend/app/services/vector_search_embeddings.py",
        repo_root / "backend/app/services/vector_search_db.py",
    ]
    forbidden_tokens = [
        "APIRouter",
        "router =",
        "router=",
        "@router",
        "create_engine",
        "sessionmaker",
        "PgBouncer",
        "poll_interval",
        "setInterval",
        "class VectorSearchService",
        "def get_vector_search_service",
        "psycopg2.connect",
        "migration",
    ]

    for helper_path in helper_paths:
        source = helper_path.read_text(encoding="utf-8")
        for token in forbidden_tokens:
            assert token not in source, f"{token} unexpectedly found in {helper_path}"
