import ast
from pathlib import Path

from backend.tests.test_execution_order_clause import build_execution_order_clause


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "app" / "routes" / "core" / "workspace" / "tasks.py"


def _load_workspace_execution_order_clause():
    source = MODULE_PATH.read_text(encoding="utf-8")
    parsed = ast.parse(source, filename=str(MODULE_PATH))
    helper_node = next(
        node
        for node in parsed.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_build_workspace_execution_order_clause"
    )
    helper_module = ast.Module(body=[helper_node], type_ignores=[])
    ast.fix_missing_locations(helper_module)
    namespace = {}
    exec(
        compile(helper_module, str(MODULE_PATH), "exec"),
        {"build_execution_order_clause": build_execution_order_clause},
        namespace,
    )
    return namespace["_build_workspace_execution_order_clause"]


def test_workspace_execution_order_clause_uses_plain_column_sort_for_history_feed():
    build_clause = _load_workspace_execution_order_clause()

    clause = build_clause("created_at", "desc")

    assert clause == "ORDER BY created_at DESC"
    assert "CASE LOWER(status)" not in clause


def test_workspace_execution_order_clause_keeps_status_priority_when_requested():
    build_clause = _load_workspace_execution_order_clause()

    clause = build_clause("status", "asc")

    assert clause == build_execution_order_clause("status", "asc")


def test_workspace_execution_order_clause_falls_back_to_created_at_for_unknown_column():
    build_clause = _load_workspace_execution_order_clause()

    clause = build_clause("last_seen_at", "asc")

    assert clause == "ORDER BY created_at ASC"
