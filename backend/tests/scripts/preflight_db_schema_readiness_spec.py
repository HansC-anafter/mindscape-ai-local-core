import sys
from pathlib import Path
from types import ModuleType

from backend.scripts import preflight_db
from backend.scripts.preflight_db_core import (
    BASE_REQUIRED_RELATIONS,
    DatabaseProbeState,
    EXECUTION_ADMISSION_RELATIONS,
    find_missing_public_relations,
    required_relations_for_backend_role,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
PREFLIGHT_ENTRY = REPO_ROOT / "backend" / "scripts" / "preflight_db.py"


class CatalogCursor:
    def __init__(self, missing_relations=()):
        self.missing_relations = tuple(missing_relations)
        self.calls = []

    def execute(self, query, params):
        self.calls.append((query, params))

    def fetchall(self):
        return [(relation_name,) for relation_name in self.missing_relations]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class CatalogConnection:
    def __init__(self, missing_relations=()):
        self.cursor_instance = CatalogCursor(missing_relations)
        self.closed = False

    def cursor(self):
        return self.cursor_instance

    def close(self):
        self.closed = True


def test_execution_roles_include_host_admission_relations():
    expected = BASE_REQUIRED_RELATIONS + EXECUTION_ADMISSION_RELATIONS

    assert required_relations_for_backend_role("execution") == expected
    assert required_relations_for_backend_role(" STABLE ") == expected
    assert len(expected) == len(set(expected)) == 8


def test_non_execution_roles_keep_the_base_failure_domain():
    assert required_relations_for_backend_role("control") == BASE_REQUIRED_RELATIONS
    assert required_relations_for_backend_role("development") == BASE_REQUIRED_RELATIONS
    assert required_relations_for_backend_role("") == BASE_REQUIRED_RELATIONS


def test_catalog_probe_uses_one_parameterized_statement_and_preserves_order():
    missing = ("host_runtime_bindings", "workspace_host_grants")
    cursor = CatalogCursor(missing)
    required = required_relations_for_backend_role("execution")

    assert find_missing_public_relations(cursor, required) == missing
    assert len(cursor.calls) == 1
    query, params = cursor.calls[0]
    assert "unnest(%s::text[])" in query
    assert "to_regclass" in query
    assert "format('%%I.%%I'" in query
    assert params == (list(required),)
    assert all(relation_name not in query for relation_name in required)


def test_empty_catalog_contract_does_not_query():
    cursor = CatalogCursor()

    assert find_missing_public_relations(cursor, ()) == ()
    assert cursor.calls == []


def test_preflight_entry_delegates_schema_policy_to_the_core_facade():
    source = PREFLIGHT_ENTRY.read_text(encoding="utf-8")

    assert "required_relations_for_backend_role" in source
    assert "find_missing_public_relations" in source
    assert "information_schema.tables" not in source
    assert "critical_tables =" not in source


def test_preflight_entry_returns_typed_missing_execution_schema(monkeypatch):
    connection = CatalogConnection(("host_runtime_bindings",))
    psycopg2_module = ModuleType("psycopg2")
    psycopg2_module.connect = lambda **_kwargs: connection
    monkeypatch.setitem(sys.modules, "psycopg2", psycopg2_module)
    monkeypatch.setenv("MINDSCAPE_BACKEND_ROLE", "execution")

    result = preflight_db.verify_critical_tables_state()

    assert result.state is DatabaseProbeState.SCHEMA_MISSING
    assert result.attempts == 1
    assert result.missing_tables == ("host_runtime_bindings",)
    assert connection.closed is True
