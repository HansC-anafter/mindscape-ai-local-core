from backend.app.database.resource_pool_readiness import (
    build_resource_pool_readiness_summary,
)


def test_resource_pool_readiness_pauses_on_pgbouncer_waiting_clients():
    summary = build_resource_pool_readiness_summary(
        primary={
            "available": True,
            "app_idle_in_transaction_count": 0,
        },
        pgbouncer={
            "enabled": True,
            "available": True,
            "core_waiting": 3,
            "vector_waiting": 0,
            "readonly_core_waiting": 0,
            "readonly_vector_waiting": 0,
        },
    )

    assert summary["status"] == "paused"
    assert summary["pgbouncer_waiting_total"] == 3
    assert "pgbouncer_client_waiting" in summary["reasons"]
    assert summary["recommendation"].startswith("hold new worker claims")


def test_resource_pool_readiness_watches_idle_transactions_without_pool_waiting():
    summary = build_resource_pool_readiness_summary(
        primary={
            "available": True,
            "app_idle_in_transaction_count": 1,
        },
        pgbouncer={
            "enabled": True,
            "available": True,
            "core_waiting": 0,
            "vector_waiting": 0,
            "readonly_core_waiting": 0,
            "readonly_vector_waiting": 0,
        },
    )

    assert summary["status"] == "watch"
    assert summary["app_idle_in_transaction_count"] == 1
    assert summary["reasons"] == ["app_idle_in_transaction"]
