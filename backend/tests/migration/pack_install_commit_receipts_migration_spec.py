from __future__ import annotations

import ast
from pathlib import Path


MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic_migrations"
    / "postgres"
    / "versions"
    / "20260716020000_create_pack_install_commit_receipts.py"
)


def _assignment(module: ast.Module, name: str):
    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.literal_eval(node.value)
    raise AssertionError(f"migration assignment missing: {name}")


def test_pack_install_commit_receipts_is_a_loadable_independent_branch():
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    module = ast.parse(source)

    assert _assignment(module, "revision") == "20260716020000"
    assert _assignment(module, "down_revision") is None
    assert _assignment(module, "branch_labels") == (
        "capability_pack_install_atomicity",
    )
    assert "20260715010000" not in source


def test_pack_install_commit_receipts_upgrade_only_creates_owned_ledger_objects():
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    module = ast.parse(source)
    upgrade = next(
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == "upgrade"
    )
    calls = [node for node in ast.walk(upgrade) if isinstance(node, ast.Call)]
    op_calls = {
        node.func.attr
        for node in calls
        if isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "op"
    }

    assert op_calls == {"create_table", "create_index"}
    assert source.count('op.create_table(\n        "pack_install_commit_receipts"') == 1
    assert source.count("op.create_index(") == 2
    assert "op.drop_" not in ast.get_source_segment(source, upgrade)
