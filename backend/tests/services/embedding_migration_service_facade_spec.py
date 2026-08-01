import pytest

from backend.app.models.embedding_migration import (
    EmbeddingMigration,
    EmbeddingMigrationItem,
    MigrationStrategy,
)
from backend.app.services.embedding_migration_service import EmbeddingMigrationService


class FakeCursor:
    def __init__(self, fetchone_result=None, fetchall_result=None):
        self.fetchone_result = fetchone_result
        self.fetchall_result = fetchall_result or []
        self.executed = []
        self.closed = False

    def execute(self, query, params=None):
        self.executed.append((query, params))

    def fetchone(self):
        return self.fetchone_result

    def fetchall(self):
        return self.fetchall_result

    def close(self):
        self.closed = True


class FakeConnection:
    def __init__(self, cursor):
        self.cursor_obj = cursor
        self.cursor_kwargs = []
        self.closed = False
        self.committed = False

    def cursor(self, *args, **kwargs):
        self.cursor_kwargs.append(kwargs)
        return self.cursor_obj

    def commit(self):
        self.committed = True

    def close(self):
        assert self.cursor_obj.closed is True
        self.closed = True


class FakeStore:
    def __init__(self):
        self.updated_items = []

    def update_migration_item(self, item):
        self.updated_items.append(item)
        return item


@pytest.mark.asyncio
async def test_count_embeddings_wrapper_preserves_filter_params():
    cursor = FakeCursor(fetchone_result=(7,))
    conn = FakeConnection(cursor)
    service = EmbeddingMigrationService(store=FakeStore())
    service._get_connection = lambda: conn

    count = await service._count_embeddings_to_migrate(
        source_model="text-embedding-3-small",
        source_provider="openai",
        workspace_id="workspace-1",
        intent_id="intent-1",
        scope="workspace",
    )

    query, params = cursor.executed[0]
    assert count == 7
    assert "FROM mindscape_personal" in query
    assert "workspace_id = %s" in query
    assert "intent_id = %s" in query
    assert "scope = %s" in query
    assert params == [
        "text-embedding-3-small",
        "openai",
        "workspace-1",
        "intent-1",
        "workspace",
    ]
    assert cursor.closed is True
    assert conn.closed is True


@pytest.mark.asyncio
async def test_fetch_embeddings_wrapper_uses_real_dict_cursor_and_ordering():
    cursor = FakeCursor(
        fetchall_result=[
            {"id": "embedding-1", "content": "first"},
            {"id": "embedding-2", "content": "second"},
        ]
    )
    conn = FakeConnection(cursor)
    service = EmbeddingMigrationService(store=FakeStore())
    service._get_connection = lambda: conn
    migration = EmbeddingMigration(
        source_model="old-model",
        target_model="new-model",
        source_provider="openai",
        target_provider="openai",
        user_id="user-1",
    )

    result = await service._fetch_embeddings_to_migrate(migration)

    query, params = cursor.executed[0]
    assert result == [
        {"id": "embedding-1", "content": "first"},
        {"id": "embedding-2", "content": "second"},
    ]
    assert "ORDER BY created_at" in query
    assert params == ["old-model", "openai"]
    assert conn.cursor_kwargs[0]["cursor_factory"].__name__ == "RealDictCursor"
    assert cursor.closed is True
    assert conn.closed is True


def test_extract_source_text_facade_keeps_direct_and_metadata_paths():
    service = EmbeddingMigrationService(store=FakeStore())

    assert service._extract_source_text({"content": "direct text"}) == "direct text"
    assert (
        service._extract_source_text({"metadata": '{"seed_text": "seed text"}'})
        == "seed text"
    )
    assert service._extract_source_text({"metadata": "{not-json"}) is None


@pytest.mark.asyncio
async def test_replace_strategy_wrapper_updates_existing_embedding_and_item():
    cursor = FakeCursor()
    conn = FakeConnection(cursor)
    store = FakeStore()
    service = EmbeddingMigrationService(store=store)
    service._get_connection = lambda: conn
    migration = EmbeddingMigration(
        source_model="old-model",
        target_model="new-model",
        source_provider="openai",
        target_provider="openai",
        user_id="user-1",
        strategy=MigrationStrategy.REPLACE,
    )
    item = EmbeddingMigrationItem(
        migration_id=migration.id,
        source_embedding_id="embedding-1",
        source_table="mindscape_personal",
    )

    await service._apply_migration_strategy(
        migration=migration,
        embedding_record={"id": "embedding-1", "metadata": {"keep": "yes"}},
        new_embedding=[0.1, 0.2],
        migration_item=item,
    )

    query, params = cursor.executed[0]
    metadata = params[1].adapted
    assert "UPDATE mindscape_personal" in query
    assert params[0] == [0.1, 0.2]
    assert params[2] == "embedding-1"
    assert metadata["keep"] == "yes"
    assert metadata["embedding_model"] == "new-model"
    assert metadata["embedding_provider"] == "openai"
    assert metadata["embedding_dimension"] == 2
    assert metadata["migrated_from"] == "old-model"
    assert item.target_embedding_id == "embedding-1"
    assert store.updated_items == [item]
    assert conn.committed is True
    assert cursor.closed is True
    assert conn.closed is True
