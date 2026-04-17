from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def _load_migration_module():
    repo_root = Path(__file__).resolve().parents[3]
    module_path = (
        repo_root
        / "backend"
        / "alembic_migrations"
        / "postgres"
        / "versions"
        / "20260130000000_add_tasks_and_playbook_flows.py"
    )
    spec = spec_from_file_location(
        "test_tasks_and_playbook_flows_migration",
        module_path,
    )
    module = module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _FakeInspector:
    def get_table_names(self):
        return ["tasks", "playbook_flows"]

    def get_indexes(self, table_name):
        indexes = {
            "tasks": [
                {"name": "idx_tasks_workspace"},
                {"name": "idx_tasks_message"},
                {"name": "idx_tasks_status"},
                {"name": "idx_tasks_workspace_status"},
                {"name": "idx_tasks_created_at"},
                {"name": "idx_tasks_execution_id"},
                {"name": "idx_tasks_project"},
            ],
            "playbook_flows": [
                {"name": "idx_playbook_flows_name"},
                {"name": "idx_playbook_flows_created_at"},
            ],
        }
        return indexes[table_name]


def test_upgrade_skips_existing_task_and_playbook_flow_tables_and_indexes(monkeypatch):
    module = _load_migration_module()
    create_table_calls = []
    create_index_calls = []

    monkeypatch.setattr(module.op, "get_bind", lambda: object())
    monkeypatch.setattr(module.sa, "inspect", lambda _bind: _FakeInspector())
    monkeypatch.setattr(
        module.op,
        "create_table",
        lambda *args, **kwargs: create_table_calls.append((args, kwargs)),
    )
    monkeypatch.setattr(
        module.op,
        "create_index",
        lambda *args, **kwargs: create_index_calls.append((args, kwargs)),
    )

    module.upgrade()

    assert create_table_calls == []
    assert create_index_calls == []
