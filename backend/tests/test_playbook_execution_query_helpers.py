from contextlib import contextmanager
from types import SimpleNamespace

from backend.app.routes.core.execution_query_helpers import (
    build_status_payload_from_row,
    load_global_execution_rows,
    parse_execution_context,
    parse_status_filter,
    serialize_global_execution,
)


def test_parse_execution_context_returns_empty_dict_for_invalid_json():
    assert parse_execution_context("not-json") == {}


def test_build_status_payload_from_row_trims_heavy_execution_context_keys():
    row = SimpleNamespace(
        execution_id="exec-1",
        status="running",
        execution_context='{"status":"running","foo":1,"result":{"ok":true},"conversation_state":{"bar":2}}',
    )

    payload = build_status_payload_from_row(row, execution_id="exec-1")

    assert payload == {
        "execution_id": "exec-1",
        "task_status": "running",
        "execution_context": {
            "status": "running",
            "foo": 1,
        },
    }


def test_parse_status_filter_normalizes_values():
    assert parse_status_filter("running, pending ,completed") == [
        "running",
        "pending",
        "completed",
    ]


def test_load_global_execution_rows_applies_filters():
    captured = {}
    expected_rows = [SimpleNamespace(id="task-1")]

    class _Result:
        def fetchall(self):
            return expected_rows

    class _Conn:
        def execute(self, query, params):
            captured["query"] = str(query)
            captured["params"] = params
            return _Result()

    @contextmanager
    def _get_connection():
        yield _Conn()

    tasks_store = SimpleNamespace(get_connection=_get_connection)

    rows = load_global_execution_rows(
        tasks_store,
        limit=20,
        playbook_code_prefix="ig_",
        status_filter="running, pending",
    )

    assert rows == expected_rows
    assert "t.pack_id LIKE :pack_prefix" in captured["query"]
    assert "LOWER(t.status) = ANY(:statuses)" in captured["query"]
    assert captured["params"] == {
        "pack_prefix": "ig_%",
        "statuses": ["running", "pending"],
        "limit": 20,
    }


def test_serialize_global_execution_adds_queue_metadata():
    task = SimpleNamespace(
        model_dump=lambda: {
            "id": "task-1",
            "execution_id": None,
            "pack_id": None,
            "execution_context": {"playbook_code": "ig_demo"},
            "queue_shard": "browser",
        }
    )
    row = SimpleNamespace(workspace_name="Workspace A")
    queue_cache = SimpleNamespace(
        get_position=lambda tasks_store, task: 2,
        get_total=lambda queue_shard: 5,
    )

    payload = serialize_global_execution(
        SimpleNamespace(),
        task,
        row,
        queue_cache,
    )

    assert payload["playbook_code"] == "ig_demo"
    assert payload["execution_id"] == "task-1"
    assert payload["workspace_name"] == "Workspace A"
    assert payload["queue_position"] == 2
    assert payload["queue_total"] == 5
