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
        / "20251227174800_init_mindscape_tables.py"
    )
    spec = spec_from_file_location("test_init_mindscape_tables_migration", module_path)
    module = module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _FakeScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


class _FakeBind:
    def __init__(self, udt_names):
        self._udt_names = udt_names

    def execute(self, statement, params=None):
        sql = str(statement)
        if "FROM information_schema.columns" not in sql:
            raise AssertionError(f"Unexpected bind.execute SQL: {sql}")
        key = (params["table_name"], params["column_name"])
        return _FakeScalarResult(self._udt_names.get(key))


class _FakeInspector:
    def __init__(self, columns, existing_tables=None):
        self._columns = columns
        self._existing_tables = existing_tables or {"mindscape_personal"}

    def has_table(self, table_name):
        return table_name in self._existing_tables

    def get_columns(self, _table_name):
        return [{"name": column_name} for column_name in self._columns]


def _normalize_sql(sql):
    return " ".join(str(sql).split())


def test_upgrade_existing_mindscape_personal_table_repairs_legacy_shape(monkeypatch):
    module = _load_migration_module()
    legacy_columns = [
        "id",
        "user_id",
        "seed_type",
        "seed_text",
        "source_type",
        "source_id",
        "confidence",
        "weight",
        "embedding",
        "metadata",
        "created_at",
        "updated_at",
    ]
    fake_bind = _FakeBind({("mindscape_personal", "metadata"): "text"})
    fake_inspector = _FakeInspector(legacy_columns, {"mindscape_personal"})
    added_columns = []
    executed_sql = []

    monkeypatch.setattr(module.op, "get_bind", lambda: fake_bind)
    monkeypatch.setattr(module.sa, "inspect", lambda _bind: fake_inspector)
    monkeypatch.setattr(
        module.op,
        "add_column",
        lambda table_name, column: added_columns.append((table_name, column.name)),
    )
    monkeypatch.setattr(
        module.op,
        "execute",
        lambda sql: executed_sql.append(_normalize_sql(sql)),
    )

    module._upgrade_existing_mindscape_personal_table()

    assert added_columns == [
        ("mindscape_personal", "content"),
        ("mindscape_personal", "source_context"),
    ]
    assert any(
        "UPDATE mindscape_personal SET content = COALESCE(NULLIF(content, ''), seed_text, '')"
        in sql
        for sql in executed_sql
    )
    assert any(
        "ALTER TABLE mindscape_personal ALTER COLUMN content SET NOT NULL" in sql
        for sql in executed_sql
    )
    assert any(
        "ALTER TABLE mindscape_personal ALTER COLUMN metadata TYPE JSONB USING _mindscape_try_parse_jsonb(metadata)"
        in sql
        for sql in executed_sql
    )
    assert any(
        "DROP FUNCTION IF EXISTS _mindscape_try_parse_jsonb(TEXT)" in sql
        for sql in executed_sql
    )


def test_upgrade_existing_external_docs_table_repairs_legacy_shape(monkeypatch):
    module = _load_migration_module()
    legacy_columns = [
        "id",
        "user_id",
        "source_app",
        "title",
        "content",
        "metadata",
        "created_at",
        "updated_at",
        "embedding",
    ]
    fake_bind = _FakeBind({})
    fake_inspector = _FakeInspector(legacy_columns, {"external_docs"})
    added_columns = []
    executed_sql = []

    monkeypatch.setattr(module.op, "get_bind", lambda: fake_bind)
    monkeypatch.setattr(module.sa, "inspect", lambda _bind: fake_inspector)
    monkeypatch.setattr(
        module.op,
        "add_column",
        lambda table_name, column: added_columns.append((table_name, column.name)),
    )
    monkeypatch.setattr(
        module.op,
        "execute",
        lambda sql: executed_sql.append(_normalize_sql(sql)),
    )

    module._upgrade_existing_external_docs_table()

    assert added_columns == [
        ("external_docs", "source_id"),
        ("external_docs", "doc_type"),
        ("external_docs", "last_synced_at"),
    ]
    assert any(
        "UPDATE external_docs SET source_id = COALESCE( NULLIF(source_id, ''), NULLIF(title, ''), source_app || ':' || id::text )"
        in sql
        for sql in executed_sql
    )
    assert any(
        "ALTER TABLE external_docs ALTER COLUMN source_id SET NOT NULL" in sql
        for sql in executed_sql
    )
