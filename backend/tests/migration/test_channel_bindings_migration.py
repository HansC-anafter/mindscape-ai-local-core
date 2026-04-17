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
        / "20260105000000_add_channel_bindings_table.py"
    )
    spec = spec_from_file_location("test_channel_bindings_migration", module_path)
    module = module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _FakeInspector:
    def get_table_names(self):
        return ["channel_bindings"]

    def get_indexes(self, table_name):
        assert table_name == "channel_bindings"
        return [
            {"name": "idx_workspace_runtime_channel"},
            {"name": "ix_channel_bindings_workspace_id"},
            {"name": "ix_channel_bindings_runtime_id"},
            {"name": "ix_channel_bindings_channel_id"},
            {"name": "ix_channel_bindings_agency"},
            {"name": "ix_channel_bindings_tenant"},
            {"name": "ix_channel_bindings_chainagent"},
        ]


def test_upgrade_skips_existing_channel_bindings_table_and_indexes(monkeypatch):
    module = _load_migration_module()
    create_table_calls = []
    create_index_calls = []

    monkeypatch.setattr(module.op, "get_bind", lambda: object())
    monkeypatch.setattr(module.op, "f", lambda name: name)
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
