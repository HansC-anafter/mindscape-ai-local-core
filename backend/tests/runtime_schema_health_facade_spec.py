from backend.app.services.runtime_schema_health.readiness import (
    RuntimeSchemaHealthFacade,
)


def test_runtime_schema_health_requires_catalog_access_and_host_resources() -> None:
    facade = RuntimeSchemaHealthFacade(
        host_resource_reporter=lambda: {
            "ready": True,
            "scope": "host-resource-only",
        },
        migration_reporter=lambda: {"status": "success"},
        access_reporter=lambda: {
            "access_principals": True,
            "access_identity_bindings": True,
            "access_grants": False,
        },
        ttl_seconds=0,
    )

    report = facade.inspect()

    assert report["ready"] is False
    assert report["catalog_ready"] is True
    assert report["access_ready"] is False
    assert report["host_resources_ready"] is True


def test_runtime_schema_health_cache_bounds_database_work() -> None:
    calls = {"migration": 0}
    clock = [10.0]

    def migration_report():
        calls["migration"] += 1
        return {"status": "success"}

    facade = RuntimeSchemaHealthFacade(
        host_resource_reporter=lambda: {"ready": True},
        migration_reporter=migration_report,
        access_reporter=lambda: {
            "access_principals": True,
            "access_identity_bindings": True,
            "access_grants": True,
        },
        ttl_seconds=30,
        clock=lambda: clock[0],
    )

    assert facade.inspect()["ready"] is True
    assert facade.inspect()["ready"] is True
    assert calls["migration"] == 1
    clock[0] = 41.0
    assert facade.inspect()["ready"] is True
    assert calls["migration"] == 2
