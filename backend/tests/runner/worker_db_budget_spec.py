from backend.app.runner.db_pool_pressure import DbPoolPressureDecision
from backend.app.runner.worker_db_budget import decide_worker_db_budget


def test_open_pressure_allows_full_budget():
    decision = decide_worker_db_budget(
        DbPoolPressureDecision.open(),
        profile_code="default",
        inflight=0,
        max_inflight=2,
    )

    assert decision.allow_claim_scan is True
    assert decision.apply_claim_scan_limit(8) == 8
    assert decision.allow_release_maintenance is True
    assert decision.allow_postgres_heartbeat is True


def test_waiting_clients_pause_claim_and_maintenance():
    decision = decide_worker_db_budget(
        DbPoolPressureDecision.paused_for("pgbouncer_client_waiting"),
        profile_code="default",
        inflight=0,
        max_inflight=2,
    )

    assert decision.allow_claim_scan is False
    assert decision.apply_claim_scan_limit(8) == 0
    assert decision.allow_release_maintenance is False
    assert decision.allow_postgres_heartbeat is True


def test_high_client_active_reduces_claim_scan_and_allows_idle_release(monkeypatch):
    monkeypatch.setenv("LOCAL_CORE_DB_BUDGET_HIGH_CLIENT_ACTIVE_THRESHOLD", "10")
    monkeypatch.setenv("LOCAL_CORE_DB_BUDGET_HIGH_CLIENT_SCAN_MULTIPLIER", "0.5")
    pressure = DbPoolPressureDecision.open(
        pools=[
            {
                "database": "mindscape_core",
                "cl_active": 12,
                "cl_waiting": 0,
                "sv_active": 2,
                "sv_idle": 6,
            }
        ]
    )

    decision = decide_worker_db_budget(
        pressure,
        profile_code="default",
        inflight=0,
        max_inflight=4,
    )

    assert decision.allow_claim_scan is True
    assert decision.apply_claim_scan_limit(8) == 4
    assert decision.allow_release_maintenance is True
    assert decision.reason == "pgbouncer_client_active_budget"


def test_high_client_active_keeps_release_off_when_runner_saturated(monkeypatch):
    monkeypatch.setenv("LOCAL_CORE_DB_BUDGET_HIGH_CLIENT_ACTIVE_THRESHOLD", "10")
    pressure = DbPoolPressureDecision.open(
        pools=[
            {
                "database": "mindscape_core",
                "cl_active": 12,
                "cl_waiting": 0,
                "sv_active": 2,
                "sv_idle": 6,
            }
        ]
    )

    decision = decide_worker_db_budget(
        pressure,
        profile_code="browser_local",
        inflight=3,
        max_inflight=3,
    )

    assert decision.allow_claim_scan is True
    assert decision.allow_release_maintenance is False
    assert decision.reason == "pgbouncer_client_active_budget"
