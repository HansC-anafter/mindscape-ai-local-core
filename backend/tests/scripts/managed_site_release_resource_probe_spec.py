"""Contract tests for the managed site release resource probe."""

from __future__ import annotations

import json

import pytest

from scripts.managed_site_release_resource_probe_core import (
    ManagedSiteReleaseResourceProbeFacade,
)
from scripts.managed_site_release_resource_probe_core import (
    collectors as collectors_module,
)
from scripts.managed_site_release_resource_probe_core.collectors import (
    RuntimeResourceCollectors,
)


class _Collectors:
    def __init__(self) -> None:
        self.database_count = 0
        self.worker_count = 0

    def database(self):
        self.database_count += 1
        return {
            "connections": 4 + self.database_count - 1,
            "active": 1,
            "idle_transaction": 0,
            "waiting_locks": 0,
            "long_transactions": 0,
        }

    def pgbouncer(self, *, include_samples):
        value = {"config_sha256": "a" * 64}
        if include_samples:
            value.update(
                {
                    "sample_count": 3,
                    "client_waiting_max": 0,
                    "max_wait_seconds": 0,
                }
            )
        return value

    def worker(self):
        self.worker_count += 1
        return {
            "process_count": 7,
            "queue_depth": self.worker_count - 1,
        }


def _budget():
    return {
        "database": {},
        "target_database": {},
        "pgbouncer": {},
        "worker": {},
        "browser": {},
        "ux": {},
    }


def _common(operation):
    return {
        "schema_version": (
            "mindscape.managed-site-runtime-resource-probe.v1"
        ),
        "operation": operation,
        "execution_id": "release-test-001",
        "change_set_id": "b" * 64,
        "execution_unit_sha256": "c" * 64,
        "resource_budget": _budget(),
    }


def test_baseline_and_postflight_preserve_exact_raw_measurements():
    collectors = _Collectors()
    facade = ManagedSiteReleaseResourceProbeFacade(collectors)
    baseline = facade.execute(_common("capture_baseline"))["baseline"]
    request = {
        **_common("collect_postflight"),
        "baseline": baseline,
        "release_evidence": {
            "effect_action_ids": ["publish-home", "retire-legacy"],
            "retry_count": 0,
            "duplicate_effects": 0,
        },
    }

    result = facade.execute(request)

    assert set(result["checks"]) == {
        "database",
        "pgbouncer",
        "worker",
    }
    assert result["checks"]["database"]["baseline"]["connections"] == 4
    assert result["checks"]["database"]["observed"]["connections"] == 5
    assert result["checks"]["worker"]["baseline"]["queue_depth"] == 0
    assert result["checks"]["worker"]["observed"]["queue_depth"] == 1
    assert result["checks"]["pgbouncer"]["sample_count"] == 3


def test_postflight_rejects_unproven_retry_or_duplicate_effects():
    facade = ManagedSiteReleaseResourceProbeFacade(_Collectors())
    baseline = facade.execute(_common("capture_baseline"))["baseline"]
    request = {
        **_common("collect_postflight"),
        "baseline": baseline,
        "release_evidence": {
            "effect_action_ids": ["publish-home"],
            "retry_count": 1,
            "duplicate_effects": 0,
        },
    }

    with pytest.raises(
        ValueError,
        match="managed_resource_probe_release_evidence_invalid",
    ):
        facade.execute(request)


def test_probe_rejects_unknown_fields_before_collecting():
    facade = ManagedSiteReleaseResourceProbeFacade(_Collectors())
    request = {**_common("capture_baseline"), "unexpected": True}

    with pytest.raises(
        ValueError,
        match="managed_resource_probe_request_fields_invalid",
    ):
        facade.execute(request)


def test_pgbouncer_probe_does_not_open_a_transaction_context(monkeypatch):
    class _Connection:
        def __init__(self):
            self.closed = False

        def __enter__(self):
            raise AssertionError("PgBouncer admin connection must not BEGIN")

        def close(self):
            self.closed = True

    connection = _Connection()
    monkeypatch.setattr(
        collectors_module,
        "_postgres_url",
        lambda _name: "postgresql://admin@pgbouncer/pgbouncer",
    )
    monkeypatch.setattr(
        collectors_module,
        "_connect_pgbouncer",
        lambda _dsn: connection,
    )
    monkeypatch.setattr(
        RuntimeResourceCollectors,
        "_pgbouncer_config",
        staticmethod(
            lambda _connection: [
                {
                    "changeable": "no",
                    "default": "transaction",
                    "key": "pool_mode",
                    "value": "transaction",
                }
            ]
        ),
    )

    result = RuntimeResourceCollectors().pgbouncer(
        include_samples=False
    )

    assert len(result["config_sha256"]) == 64
    assert connection.closed is True


def test_runner_count_uses_current_redis_resource_heartbeats(monkeypatch):
    now_epoch = collectors_module.time.time()
    values = {
        "mindscape:runner_resources:heartbeat:v1:runner-a": {
            "runner_id": "runner-a",
            "captured_at_epoch": now_epoch,
        },
        "mindscape:runner_resources:heartbeat:v1:runner-b": {
            "runner_id": "runner-b",
            "captured_at_epoch": now_epoch - 10,
        },
        "mindscape:runner_resources:heartbeat:v1:stale": {
            "runner_id": "stale",
            "captured_at_epoch": now_epoch - 120,
        },
    }

    class _Redis:
        def ping(self):
            return True

        def scan(self, *, cursor, match, count):
            assert cursor == 0
            assert match == "mindscape:runner_resources:heartbeat:v1:*"
            assert count == 100
            return 0, list(values)

        def get(self, key):
            return json.dumps(values[key])

    monkeypatch.setattr(
        collectors_module.redis,
        "Redis",
        lambda **_kwargs: _Redis(),
    )

    assert RuntimeResourceCollectors._runner_process_count() == 2
