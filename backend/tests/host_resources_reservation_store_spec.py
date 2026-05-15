from pathlib import Path

from backend.app.services.host_resources.reservation_store import (
    HostResourceReservationStore,
)


def test_reservation_store_params_keep_route_metadata_out_of_task_hot_rows():
    store = object.__new__(HostResourceReservationStore)

    params = store._reservation_params(
        {
            "reservation_id": "res-1",
            "state": "reserved_waiting",
            "created_at": "2026-05-14T00:00:00+00:00",
            "expires_at": "2026-05-14T01:00:00+00:00",
            "route_request": {
                "target_lane": "comfyui_runtime:flux2_klein_true_v2_q6_local",
                "priority_class": "interactive_high",
                "drain_policy": "drain_after_current",
                "requested_by": "test",
            },
        }
    )

    assert params["reservation_id"] == "res-1"
    assert params["target_lane"] == "comfyui_runtime:flux2_klein_true_v2_q6_local"
    assert params["priority_class"] == "interactive_high"
    assert params["drain_policy"] == "drain_after_current"
    assert params["requested_by"] == "test"
    assert "execution_context" not in params


def test_host_resource_ledger_migration_tracks_postgres_runtime_head():
    migration = (
        Path(__file__).resolve().parents[1]
        / "alembic_migrations/postgres/versions/"
        / "20260514010000_add_host_resource_ledger.py"
    ).read_text(encoding="utf-8")

    assert 'revision = "20260514010000"' in migration
    assert 'down_revision = "20260513203000"' in migration
    assert "host_resource_reservations" in migration
    assert "host_resource_events" in migration
    assert "backend/migrations" not in migration


def test_startup_schedules_nonblocking_host_resource_projection_rehydrate():
    lifecycle = (
        Path(__file__).resolve().parents[1]
        / "app/app_bootstrap/lifecycle.py"
    ).read_text(encoding="utf-8")

    assert "_rehydrate_host_resource_projection_post_ready" in lifecycle
    assert "asyncio.create_task" in lifecycle
    assert "asyncio.to_thread" in lifecycle
    assert "rehydrate_route_reservation_projection" in lifecycle
