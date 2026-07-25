"""Pure comparability rules for product-iteration review."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def _arm_identity(arm: dict[str, Any]) -> dict[str, Any]:
    return {
        "arm_id": arm["arm_id"],
        "capability_identity": deepcopy(arm["capability_identity"]),
        "development_attestation_sha256": arm[
            "development_attestation_sha256"
        ],
        "consumer_compatibility_class": arm[
            "consumer_compatibility_class"
        ],
        "configuration_fingerprint": arm[
            "configuration_fingerprint"
        ],
        "environment_fingerprint": arm["environment_fingerprint"],
        "data_fingerprint": arm["data_fingerprint"],
    }


def comparability_identity(state: dict[str, Any]) -> dict[str, Any]:
    definition = state.get("definition")
    if not definition:
        raise ValueError("iteration comparison requires a definition")
    return {
        "cohort_definition_hash": definition["cohort"][
            "definition_hash"
        ],
        "case_manifest_sha256": definition["cohort"][
            "case_manifest_ref"
        ]["sha256"],
        "evaluator": deepcopy(definition["evaluator"]),
        "metrics": [
            {
                "metric_id": item["metric_id"],
                "direction": item["direction"],
                "denominator_definition": item[
                    "denominator_definition"
                ],
                "quality_gate": item["quality_gate"],
            }
            for item in sorted(
                definition["metric_definitions"],
                key=lambda value: value["metric_id"],
            )
        ],
        "arms": [
            _arm_identity(item)
            for item in sorted(
                definition["arms"], key=lambda value: value["arm_id"]
            )
        ],
    }


def compare_iteration_states(
    left: dict[str, Any], right: dict[str, Any]
) -> dict[str, Any]:
    left_identity = comparability_identity(left)
    right_identity = comparability_identity(right)
    reasons = [
        field
        for field in left_identity
        if left_identity[field] != right_identity[field]
    ]
    if reasons:
        return {
            "status": "incomparable",
            "comparable": False,
            "reason_codes": reasons,
            "delta": None,
        }
    left_gates = {
        item["gate_id"]: item["status"]
        for item in (left.get("evaluation") or {}).get(
            "gate_results", []
        )
    }
    right_gates = {
        item["gate_id"]: item["status"]
        for item in (right.get("evaluation") or {}).get(
            "gate_results", []
        )
    }
    gate_changes = {
        gate_id: {
            "left": left_gates.get(gate_id, "missing"),
            "right": right_gates.get(gate_id, "missing"),
        }
        for gate_id in sorted(set(left_gates) | set(right_gates))
        if left_gates.get(gate_id) != right_gates.get(gate_id)
    }
    return {
        "status": "comparable",
        "comparable": True,
        "reason_codes": [],
        "delta": {
            "accepted_observation_count": (
                int(right.get("accepted_observation_count", 0))
                - int(left.get("accepted_observation_count", 0))
            ),
            "gate_status_changes": gate_changes,
        },
    }
