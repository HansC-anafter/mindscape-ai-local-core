"""Contract tests for the managed site release resource probe."""

from __future__ import annotations

import pytest

from scripts.managed_site_release_resource_probe_core import (
    ManagedSiteReleaseResourceProbeFacade,
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
