from backend.app.database import ha_readiness


def _primary_row(**overrides):
    row = {
        "postgres_in_recovery": False,
        "transaction_read_only": "off",
        "wal_archive_mode": "on",
        "wal_level": "replica",
        "app_idle_in_transaction_count": 0,
    }
    row.update(overrides)
    return row


def test_primary_recovery_and_readonly_fields_are_independent(monkeypatch):
    monkeypatch.setattr(
        ha_readiness,
        "get_postgres_url_core",
        lambda required=True: "postgresql://u:p@pgbouncer/core",
    )
    monkeypatch.setattr(
        ha_readiness,
        "get_postgres_url_core_readonly",
        lambda required=False: "",
    )

    report = ha_readiness.build_ha_readiness_report(
        include_pgbouncer=False,
        query_one=lambda _url, _sql, _app: _primary_row(
            postgres_in_recovery=True,
            transaction_read_only="off",
        ),
    )

    assert report["postgres_in_recovery"] is True
    assert report["transaction_read_only"] == "off"
    assert report["wal_archive_mode"] == "on"
    assert report["replica"]["reason"] == "readonly_probe_disabled"


def test_pgbouncer_waiting_clients_do_not_change_primary_status(monkeypatch):
    monkeypatch.setattr(
        ha_readiness,
        "get_postgres_url_core",
        lambda required=True: "postgresql://u:p@pgbouncer/core",
    )
    monkeypatch.setattr(
        ha_readiness,
        "get_pgbouncer_admin_url",
        lambda required=False: "postgresql://u:p@pgbouncer/pgbouncer",
    )
    monkeypatch.setattr(
        ha_readiness,
        "get_postgres_url_core_readonly",
        lambda required=False: "",
    )

    report = ha_readiness.build_ha_readiness_report(
        query_one=lambda _url, _sql, _app: _primary_row(),
        query_all=lambda _url, _sql, _app: [
            {"database": "mindscape_core", "cl_waiting": "4"},
            {"database": "mindscape_vectors", "cl_waiting": "0"},
        ],
    )

    assert report["postgres_in_recovery"] is False
    assert report["transaction_read_only"] == "off"
    assert report["pgbouncer_core_waiting"] == 4
    assert report["pgbouncer_vector_waiting"] == 0
    assert report["pgbouncer"]["core_pool_present"] is True
    assert report["resource_pool_readiness"]["status"] == "paused"
    assert (
        "pgbouncer_client_waiting"
        in report["resource_pool_readiness"]["reasons"]
    )


def test_missing_readonly_replica_reports_disabled_state(monkeypatch):
    monkeypatch.setattr(
        ha_readiness,
        "get_postgres_url_core",
        lambda required=True: "postgresql://u:p@pgbouncer/core",
    )
    monkeypatch.setattr(
        ha_readiness,
        "get_pgbouncer_admin_url",
        lambda required=False: "",
    )
    monkeypatch.setattr(
        ha_readiness,
        "get_postgres_url_core_readonly",
        lambda required=False: "",
    )

    report = ha_readiness.build_ha_readiness_report(
        use_readonly_probe=True,
        query_one=lambda _url, _sql, _app: _primary_row(),
    )

    assert report["replica"]["probe_enabled"] is True
    assert report["replica"]["configured"] is False
    assert report["replica_available"] is False
    assert report["replica"]["reason"] == "readonly_url_missing"


def test_readonly_probe_requires_standby_and_readonly_transaction(monkeypatch):
    monkeypatch.setattr(
        ha_readiness,
        "get_postgres_url_core",
        lambda required=True: "postgresql://u:p@pgbouncer/core",
    )
    monkeypatch.setattr(
        ha_readiness,
        "get_pgbouncer_admin_url",
        lambda required=False: "postgresql://u:p@pgbouncer/pgbouncer",
    )
    monkeypatch.setattr(
        ha_readiness,
        "get_postgres_url_core_readonly",
        lambda required=False: "postgresql://u:p@pgbouncer/core_readonly",
    )

    def fake_one(_url, sql, _app):
        if "pg_last_wal_receive_lsn" in sql:
            return {
                "postgres_in_recovery": True,
                "transaction_read_only": "on",
                "receive_lsn": "0/20",
                "replay_lsn": "0/20",
                "replay_lag_bytes": 0,
            }
        return _primary_row()

    report = ha_readiness.build_ha_readiness_report(
        use_readonly_probe=True,
        query_one=fake_one,
        query_all=lambda _url, _sql, _app: [
            {"database": "mindscape_core", "cl_waiting": "0"},
            {"database": "mindscape_vectors", "cl_waiting": "0"},
            {"database": "mindscape_core_readonly", "cl_waiting": "0"},
            {"database": "mindscape_vectors_readonly", "cl_waiting": "0"},
        ],
    )

    assert report["replica_available"] is True
    assert report["replica_replay_lag_bytes"] == 0
    assert report["pgbouncer"]["readonly_core_pool_present"] is True
    assert report["resource_pool_readiness"]["status"] == "open"
