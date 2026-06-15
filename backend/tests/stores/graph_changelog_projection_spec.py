from datetime import datetime, timezone

from app.services.stores.graph_changelog_models import (
    ChangelogEntry,
    decode_json_state,
    row_to_changelog_entry,
    rows_to_changelog_entries,
)
from app.services.stores.graph_changelog_store import GraphChangelogStore


def _row(change_id="change-1"):
    now = datetime(2026, 6, 16, tzinfo=timezone.utc)
    return (
        change_id,
        "workspace-1",
        7,
        "create_node",
        "node",
        "node-1",
        '{"label": "old"}',
        '{"label": "new"}',
        "system",
        "task_creation",
        "pending",
        now,
        None,
        None,
    )


def test_changelog_entry_to_dict_serializes_timestamps():
    now = datetime(2026, 6, 16, tzinfo=timezone.utc)
    entry = ChangelogEntry(
        id="change-1",
        workspace_id="workspace-1",
        version=1,
        operation="create_node",
        target_type="node",
        target_id="node-1",
        before_state=None,
        after_state={"label": "new"},
        actor="system",
        created_at=now,
    )

    assert entry.to_dict()["created_at"] == "2026-06-16T00:00:00+00:00"
    assert entry.to_dict()["after_state"] == {"label": "new"}


def test_row_to_changelog_entry_decodes_json_state():
    entry = row_to_changelog_entry(_row())

    assert entry.id == "change-1"
    assert entry.before_state == {"label": "old"}
    assert entry.after_state == {"label": "new"}
    assert entry.actor_context == "task_creation"


def test_rows_to_changelog_entries_preserves_order():
    entries = rows_to_changelog_entries([_row("change-1"), _row("change-2")])

    assert [entry.id for entry in entries] == ["change-1", "change-2"]


def test_decode_json_state_and_reverse_operation_fallback():
    assert decode_json_state(None, {}) == {}
    assert decode_json_state({"label": "raw"}) == {"label": "raw"}
    assert GraphChangelogStore()._get_reverse_operation("create_node") == "delete_node"
    assert GraphChangelogStore()._get_reverse_operation("custom_op") == "custom_op"
