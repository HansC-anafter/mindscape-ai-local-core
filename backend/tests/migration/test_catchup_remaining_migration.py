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
        / "20260129000000_catchup_remaining.py"
    )
    spec = spec_from_file_location("test_catchup_remaining_migration", module_path)
    module = module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _FakeInspector:
    TABLES = {
        "commands": {"idx_commands_workspace", "idx_commands_thread"},
        "conversation_threads": {
            "idx_conv_threads_workspace",
            "idx_conv_threads_updated",
        },
        "playbook_executions": {
            "idx_pb_exec_workspace",
            "idx_pb_exec_intent",
            "idx_pb_exec_thread",
        },
        "lens_compositions": {"idx_lens_comp_workspace"},
        "surface_events": {"idx_surface_events_workspace"},
        "user_playbook_meta": {"idx_upm_profile_playbook"},
        "thread_references": {"idx_thread_refs_thread"},
    }

    def get_table_names(self):
        return list(self.TABLES)

    def get_indexes(self, table_name):
        return [{"name": index_name} for index_name in self.TABLES.get(table_name, set())]


def test_upgrade_skips_existing_catchup_remaining_tables_and_indexes(monkeypatch):
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
