from contextlib import contextmanager

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.routes.core import host_resources
from backend.app.services.host_resources import schema_readiness


class _Result:
    def __init__(self, *, scalar_value=None, rows=None):
        self._scalar_value = scalar_value
        self._rows = rows or []

    def scalar(self):
        return self._scalar_value

    def fetchall(self):
        return self._rows


class _FakeConnection:
    def __init__(self, *, existing_objects, revisions):
        self.existing_objects = set(existing_objects)
        self.revisions = list(revisions)

    def execute(self, statement, params=None):
        sql = str(statement)
        params = params or {}
        if "to_regclass" in sql:
            object_name = str(params.get("object_name") or "").replace("public.", "")
            return _Result(scalar_value=object_name in self.existing_objects)
        if "FROM alembic_version" in sql:
            return _Result(
                rows=[
                    {"version_num": version}
                    for version in self.revisions
                ]
            )
        if "information_schema.columns" in sql:
            table_name = str(params.get("table_name") or "")
            return _Result(
                rows=[
                    (column_name,)
                    for column_name in schema_readiness.REQUIRED_COLUMNS.get(
                        table_name,
                        (),
                    )
                ]
            )
        raise AssertionError(f"unexpected query: {sql}")


class _FakeStore:
    def __init__(self, *, existing_objects, revisions):
        self.connection = _FakeConnection(
            existing_objects=existing_objects,
            revisions=revisions,
        )

    @contextmanager
    def get_connection(self):
        yield self.connection


def test_schema_readiness_passes_when_required_revision_tables_and_indexes_exist():
    store = _FakeStore(
        existing_objects=[
            "alembic_version",
            *schema_readiness.REQUIRED_TABLES,
            *schema_readiness.REQUIRED_INDEXES,
        ],
        revisions=[schema_readiness.REQUIRED_REVISION],
    )

    report = schema_readiness.check_host_resource_schema_readiness(store)

    assert report["ready"] is True
    assert report["connectable"] is True
    assert report["required_revision"] == schema_readiness.REQUIRED_REVISION
    assert report["migration_applied"] is True
    assert report["missing_tables"] == []
    assert report["missing_indexes"] == []
    assert report["scope"] == "host-resource-only"
    assert report["upgrade_command"] == "alembic -c backend/alembic.postgres.ini upgrade heads"


def test_schema_readiness_reports_missing_ledger_objects_for_new_environment():
    store = _FakeStore(
        existing_objects=["alembic_version"],
        revisions=["20260513203000"],
    )

    report = schema_readiness.check_host_resource_schema_readiness(store)

    assert report["ready"] is False
    assert report["migration_applied"] is False
    assert report["missing_tables"] == list(schema_readiness.REQUIRED_TABLES)
    assert report["missing_indexes"] == list(schema_readiness.REQUIRED_INDEXES)


def test_schema_readiness_endpoint_returns_read_only_contract(monkeypatch):
    monkeypatch.setattr(
        host_resources,
        "check_host_resource_schema_readiness",
        lambda: {
              "ready": True,
              "connectable": True,
              "required_revision": schema_readiness.REQUIRED_REVISION,
              "migration_applied": True,
              "applied_revisions": ["20260514123000"],
              "tables": {
                  "host_resource_reservations": True,
                  "host_resource_events": True,
                  "host_resource_lanes": True,
              },
            "indexes": {},
            "missing_tables": [],
            "missing_indexes": [],
            "scope": "host-resource-only",
            "upgrade_command": "alembic -c backend/alembic.postgres.ini upgrade heads",
            "error": None,
        },
    )
    app = FastAPI()
    app.include_router(host_resources.router)

    response = TestClient(app).get("/api/v1/host-resources/schema-readiness")

    assert response.status_code == 200
    assert response.json()["ready"] is True
    assert response.json()["required_revision"] == schema_readiness.REQUIRED_REVISION
