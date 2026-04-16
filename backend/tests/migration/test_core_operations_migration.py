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
        / "20260128000000_core_operations.py"
    )
    spec = spec_from_file_location("test_core_operations_migration", module_path)
    module = module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _FakeInspector:
    def has_table(self, table_name):
        return table_name in {"intents", "agent_executions", "mind_events"}


def _normalize_sql(sql):
    return " ".join(str(sql).split())


def test_upgrade_skips_existing_core_operations_tables(monkeypatch):
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
        "CREATE INDEX IF NOT EXISTS ix_intents_profile ON intents (profile_id)",
        "CREATE INDEX IF NOT EXISTS ix_intents_status ON intents (status)",
        "CREATE INDEX IF NOT EXISTS ix_intents_parent ON intents (parent_intent_id)",
        "CREATE INDEX IF NOT EXISTS ix_agent_executions_profile ON agent_executions (profile_id)",
        "CREATE INDEX IF NOT EXISTS ix_agent_executions_status ON agent_executions (status)",
        "CREATE INDEX IF NOT EXISTS ix_agent_executions_start ON agent_executions (started_at)",
        "CREATE INDEX IF NOT EXISTS ix_mind_events_profile ON mind_events (profile_id)",
        "CREATE INDEX IF NOT EXISTS ix_mind_events_time ON mind_events (timestamp)",
        "CREATE INDEX IF NOT EXISTS ix_mind_events_thread ON mind_events (thread_id)",
        "CREATE INDEX IF NOT EXISTS ix_mind_events_type ON mind_events (event_type)",
        "CREATE INDEX IF NOT EXISTS ix_mind_events_project ON mind_events (project_id)",
        "CREATE INDEX IF NOT EXISTS ix_mind_events_workspace ON mind_events (workspace_id)",
    ]
