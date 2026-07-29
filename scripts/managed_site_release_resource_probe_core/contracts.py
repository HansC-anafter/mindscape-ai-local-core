"""Fail-closed request contracts for the managed release resource probe."""

from __future__ import annotations

import re
from typing import Any

SHA256 = re.compile(r"^[0-9a-f]{64}$")
IDENTIFIER = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,127}$")

_BUDGET_KEYS = {
    "database",
    "target_database",
    "pgbouncer",
    "worker",
    "browser",
    "ux",
}
_DATABASE_FIELDS = {
    "connections",
    "active",
    "idle_transaction",
    "waiting_locks",
    "long_transactions",
}
_WORKER_FIELDS = {"process_count", "queue_depth"}


def _metrics(value: Any, fields: set[str], code: str) -> dict[str, int]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(code)
    result: dict[str, int] = {}
    for field in fields:
        metric = value[field]
        if isinstance(metric, bool) or not isinstance(metric, int) or metric < 0:
            raise ValueError(code)
        result[field] = metric
    return result


def validate_request(value: Any) -> dict[str, Any]:
    """Validate the one stdin request before any runtime connection opens."""
    if not isinstance(value, dict):
        raise ValueError("managed_resource_probe_request_not_object")
    operation = value.get("operation")
    common = {
        "schema_version",
        "operation",
        "execution_id",
        "change_set_id",
        "execution_unit_sha256",
        "resource_budget",
    }
    expected = (
        common
        if operation == "capture_baseline"
        else common | {"baseline", "release_evidence"}
        if operation == "collect_postflight"
        else set()
    )
    if set(value) != expected:
        raise ValueError("managed_resource_probe_request_fields_invalid")
    if (
        value["schema_version"]
        != "mindscape.managed-site-runtime-resource-probe.v1"
        or not IDENTIFIER.fullmatch(str(value["execution_id"]))
        or not SHA256.fullmatch(str(value["change_set_id"]))
        or not SHA256.fullmatch(str(value["execution_unit_sha256"]))
    ):
        raise ValueError("managed_resource_probe_identity_invalid")
    budget = value["resource_budget"]
    if not isinstance(budget, dict) or set(budget) != _BUDGET_KEYS:
        raise ValueError("managed_resource_probe_budget_invalid")
    if operation == "collect_postflight":
        baseline = value["baseline"]
        if not isinstance(baseline, dict) or set(baseline) != {
            "database",
            "pgbouncer_config_sha256",
            "worker",
        }:
            raise ValueError("managed_resource_probe_baseline_invalid")
        _metrics(
            baseline["database"],
            _DATABASE_FIELDS,
            "managed_resource_probe_database_baseline_invalid",
        )
        _metrics(
            baseline["worker"],
            _WORKER_FIELDS,
            "managed_resource_probe_worker_baseline_invalid",
        )
        if not SHA256.fullmatch(
            str(baseline["pgbouncer_config_sha256"])
        ):
            raise ValueError(
                "managed_resource_probe_pgbouncer_baseline_invalid"
            )
        evidence = value["release_evidence"]
        if (
            not isinstance(evidence, dict)
            or set(evidence)
            != {
                "effect_action_ids",
                "retry_count",
                "duplicate_effects",
            }
            or not isinstance(evidence["effect_action_ids"], list)
            or not evidence["effect_action_ids"]
            or len(set(evidence["effect_action_ids"]))
            != len(evidence["effect_action_ids"])
            or any(
                not IDENTIFIER.fullmatch(str(action_id))
                for action_id in evidence["effect_action_ids"]
            )
            or evidence["retry_count"] != 0
            or evidence["duplicate_effects"] != 0
        ):
            raise ValueError(
                "managed_resource_probe_release_evidence_invalid"
            )
    return value
