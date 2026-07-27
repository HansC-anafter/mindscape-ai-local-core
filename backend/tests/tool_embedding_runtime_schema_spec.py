from __future__ import annotations

import pytest

from backend.app.services.tool_embedding_schema import ensure_table


REQUIRED_COLUMNS = [
    "id",
    "tool_id",
    "display_name",
    "description",
    "category",
    "capability_code",
    "embedding",
    "embedding_model",
    "embedding_dim",
    "affordance",
    "created_at",
    "updated_at",
    "text_vector",
]


class _Cursor:
    def __init__(self, *, columns=None, index_exists=True):
        self.columns = columns or REQUIRED_COLUMNS
        self.index_exists = index_exists
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, query):
        normalized = " ".join(str(query).split())
        self.calls.append(normalized)

    def fetchall(self):
        return [(column,) for column in self.columns]

    def fetchone(self):
        return (self.index_exists,)


class _Connection:
    def __init__(self, cursor):
        self.cursor_value = cursor
        self.closed = False

    def cursor(self):
        return self.cursor_value

    def close(self):
        self.closed = True


class _Service:
    def __init__(self, connection):
        self.connection = connection

    def _get_connection(self):
        return self.connection


@pytest.mark.asyncio
async def test_runtime_schema_check_is_read_only():
    cursor = _Cursor()
    connection = _Connection(cursor)

    await ensure_table(_Service(connection))

    sql = " ".join(cursor.calls).upper()
    assert "SELECT COLUMN_NAME" in sql
    assert "TO_REGCLASS" in sql
    assert "CREATE " not in sql
    assert "ALTER " not in sql
    assert connection.closed is True


@pytest.mark.asyncio
async def test_runtime_schema_check_fails_when_migration_is_missing():
    cursor = _Cursor(columns=["id"], index_exists=False)
    connection = _Connection(cursor)

    with pytest.raises(
        RuntimeError,
        match="tool_embeddings_schema_not_migrated",
    ):
        await ensure_table(_Service(connection))

    assert connection.closed is True
