from backend.app.services.stores.tasks_store._query_cold_release import (
    TasksStoreColdReleaseQueryMixin,
)


class _EmptyRows:
    @staticmethod
    def fetchall():
        return []


class _RecordingConnection:
    def __init__(self):
        self.sql = ""
        self.params = {}

    def execute(self, statement, params):
        self.sql = str(statement)
        self.params = dict(params)
        return _EmptyRows()


class _ConnectionContext:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, exc_type, exc, traceback):
        return False


class _QueryStore(TasksStoreColdReleaseQueryMixin):
    def __init__(self):
        self.connection = _RecordingConnection()

    def get_connection(self):
        return _ConnectionContext(self.connection)


def _normalized_sql(store: _QueryStore) -> str:
    return " ".join(store.connection.sql.split())


def test_concurrency_locked_candidates_rank_by_distinct_lock_key():
    store = _QueryStore()

    assert store.list_due_concurrency_locked_tasks(
        queue_shard="browser_local",
        limit=4,
    ) == []

    sql = _normalized_sql(store)
    assert (
        "COALESCE(NULLIF(concurrency_key, ''), pack_id) AS release_group" in sql
    )
    assert "PARTITION BY release_group" in sql
    assert store.connection.params["blocked_reason"] == "concurrency_locked"


def test_resource_wait_candidates_keep_pack_level_ranking():
    store = _QueryStore()

    assert store.list_due_resource_wait_tasks(
        queue_shard="browser_local",
        limit=4,
    ) == []

    sql = _normalized_sql(store)
    assert "pack_id AS release_group" in sql
    assert "COALESCE(NULLIF(concurrency_key, ''), pack_id)" not in sql
    assert "PARTITION BY release_group" in sql
