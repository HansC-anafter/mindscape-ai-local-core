from backend.app.runner.db_pool_pressure import (
    DbPoolPressureDecision,
    should_write_postgres_heartbeat,
)


def test_postgres_heartbeat_writes_when_pressure_open():
    assert should_write_postgres_heartbeat(
        DbPoolPressureDecision.open(),
        now_epoch=100.0,
        last_write_epoch=99.0,
    )


def test_postgres_heartbeat_throttles_when_pressure_paused(monkeypatch):
    monkeypatch.setenv("LOCAL_CORE_DB_PRESSURE_HEARTBEAT_MIN_INTERVAL_SECONDS", "30")
    paused = DbPoolPressureDecision.paused_for("pgbouncer_client_waiting")

    assert not should_write_postgres_heartbeat(
        paused,
        now_epoch=100.0,
        last_write_epoch=90.0,
    )
    assert should_write_postgres_heartbeat(
        paused,
        now_epoch=121.0,
        last_write_epoch=90.0,
    )
