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
        / "20260103000000_add_runtime_environments_table.py"
    )
    spec = spec_from_file_location("test_runtime_environments_migration", module_path)
    module = module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _FakeInspector:
    def has_table(self, table_name):
        return table_name == "runtime_environments"


def _normalize_sql(sql):
    return " ".join(str(sql).split())


def test_upgrade_skips_existing_runtime_environments_table(monkeypatch):
    module = _load_migration_module()
    create_table_calls = []
    executed_sql = []

    monkeypatch.setattr(module.op, "get_bind", lambda: object())
    monkeypatch.setattr(module.sa, "inspect", lambda _bind: _FakeInspector())
    monkeypatch.setattr(
        module.op,
        "create_table",
        lambda *args, **kwargs: create_table_calls.append((args, kwargs)),
    )
    monkeypatch.setattr(
        module.op,
        "execute",
        lambda sql: executed_sql.append(_normalize_sql(sql)),
    )

    module.upgrade()

    assert create_table_calls == []
    assert executed_sql == [
        "CREATE INDEX IF NOT EXISTS ix_runtime_environments_user_id ON runtime_environments (user_id)",
        "CREATE INDEX IF NOT EXISTS ix_runtime_environments_status ON runtime_environments (status)",
    ]
