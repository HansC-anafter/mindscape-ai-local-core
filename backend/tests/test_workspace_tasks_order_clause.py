from backend.app.services.workspace_execution_activity import (
    WorkspaceExecutionActivityStore,
)


def _load_workspace_execution_order_clause():
    store = WorkspaceExecutionActivityStore()

    def build_clause(order_by: str, order: str) -> str:
        return store._order_clause(order_by=order_by, order=order)

    return build_clause


def test_workspace_execution_order_clause_uses_plain_column_sort_for_history_feed():
    build_clause = _load_workspace_execution_order_clause()

    clause = build_clause("created_at", "desc")

    assert clause == "ORDER BY created_at DESC NULLS LAST, task_id DESC"
    assert "CASE LOWER(status)" not in clause


def test_workspace_execution_order_clause_keeps_status_priority_when_requested():
    build_clause = _load_workspace_execution_order_clause()

    clause = build_clause("status", "asc")

    assert "CASE LOWER(status)" in clause
    assert "WHEN 'paused' THEN 2" in clause
    assert "status ASC" in clause


def test_workspace_execution_order_clause_falls_back_to_created_at_for_unknown_column():
    build_clause = _load_workspace_execution_order_clause()

    clause = build_clause("last_seen_at", "asc")

    assert clause == "ORDER BY created_at ASC NULLS LAST, task_id DESC"
