import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ROUTE_PATH = REPO_ROOT / "backend/app/routes/core/workspace/instruction.py"


def _parse_route() -> ast.Module:
    return ast.parse(ROUTE_PATH.read_text())


def _call_name(node: ast.AST) -> str | None:
    if not isinstance(node, ast.Call):
        return None
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def test_workspace_instruction_route_has_no_top_level_store_or_structured_llm_import():
    tree = _parse_route()

    top_level_import_modules = [
        node.module
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module
    ]
    top_level_call_names = [
        _call_name(node.value)
        for node in tree.body
        if isinstance(node, (ast.Assign, ast.AnnAssign))
    ]

    assert not any(
        module.endswith("capabilities.core_llm.services.structured")
        for module in top_level_import_modules
    )
    assert "MindscapeStore" not in top_level_call_names


def test_workspace_instruction_chat_keeps_on_demand_store_and_structured_llm_path():
    tree = _parse_route()
    chat_handler = next(
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == "chat_workspace_instruction"
    )

    handler_import_modules = [
        node.module
        for node in ast.walk(chat_handler)
        if isinstance(node, ast.ImportFrom) and node.module
    ]
    handler_call_names = [
        _call_name(node)
        for node in ast.walk(chat_handler)
        if isinstance(node, ast.Call)
    ]

    assert "_get_store" in handler_call_names
    assert "structured_extract" in handler_call_names
    assert any(
        module.endswith("capabilities.core_llm.services.structured")
        for module in handler_import_modules
    )
