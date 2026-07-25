"""Pure validation helpers for the product-iteration aggregate."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .canonical_json import encode, sha256_hex
from .contracts.v1.validator import validate_contract
from .signature import SigningKeyError, verify

PROMOTION_GATE_ORDER = (
    "development_attestation_consumer",
    "validation_evaluator_validity",
    "observation_cohort_coverage",
    "quality_correctness",
    "safety_rights_policy",
    "baseline_comparability_non_regression",
    "efficiency_cost",
)


def product_iteration_definition_sha256(definition: dict[str, Any]) -> str:
    immutable = {
        key: value
        for key, value in definition.items()
        if key
        not in {
            "state",
            "evidence_frontier",
            "admitted_at",
            "definition_sha256",
        }
    }
    return sha256_hex(immutable)


def immutable_definition(definition: dict) -> dict:
    immutable = deepcopy(definition)
    for key in ("state", "evidence_frontier", "admitted_at"):
        immutable.pop(key, None)
    return immutable


def comparability_key(
    definition: dict[str, Any], metric_id: str
) -> str:
    metric = next(
        (
            item
            for item in definition["metric_definitions"]
            if item["metric_id"] == metric_id
        ),
        None,
    )
    if metric is None:
        raise ValueError(f"iteration metric {metric_id!r} is not defined")
    return sha256_hex(
        {
            "cohort_definition_hash": definition["cohort"][
                "definition_hash"
            ],
            "case_manifest_sha256": definition["cohort"][
                "case_manifest_ref"
            ]["sha256"],
            "metric_id": metric_id,
            "denominator_definition": metric["denominator_definition"],
            "evaluator": definition["evaluator"],
        }
    )


def promotion_request_hash(definition: dict, evaluation: dict) -> str:
    return sha256_hex(
        {
            "iteration_id": definition["iteration_id"],
            "definition_sha256": definition["definition_sha256"],
            "evaluation_id": evaluation["evaluation_id"],
            "frontier_hash": evaluation["frontier_hash"],
            "development_attestation_set_sha256": evaluation[
                "development_attestation_set_sha256"
            ],
            "release_target": definition["release_target"],
        }
    )


def require_definition(definition: dict, *, state: str) -> None:
    validate_contract("product_iteration", definition)
    if definition["state"] != state:
        raise ValueError(f"iteration definition must be {state}")
    if definition["definition_sha256"] != (
        product_iteration_definition_sha256(definition)
    ):
        raise ValueError("iteration definition canonical hash mismatch")
    if len({item["arm_id"] for item in definition["arms"]}) != len(
        definition["arms"]
    ):
        raise ValueError("iteration arm IDs must be unique")
    if definition["release_target"]["arm_id"] not in {
        item["arm_id"] for item in definition["arms"]
    }:
        raise ValueError("release target must pin one declared arm")
    if abs(
        sum(item["allocation_weight"] for item in definition["arms"])
        - 1.0
    ) > 1e-9:
        raise ValueError("iteration allocation weights must sum to one")


def verify_signed(payload: dict, verification_keys: dict) -> None:
    public_key = verification_keys.get(payload["key_id"])
    if public_key is None:
        raise ValueError("signed upper receipt key is unavailable")
    try:
        verify(
            public_key,
            encode(
                {
                    key: value
                    for key, value in payload.items()
                    if key != "signature"
                }
            ),
            payload["signature"],
        )
    except SigningKeyError as exc:
        raise ValueError("signed upper receipt is invalid") from exc


def arm(definition: dict, arm_id: str) -> dict:
    selected = next(
        (
            item
            for item in definition["arms"]
            if item["arm_id"] == arm_id
        ),
        None,
    )
    if selected is None:
        raise ValueError(f"iteration arm {arm_id!r} is not defined")
    return selected


def require_enrollment_parity(
    definition: dict, selected_arm: dict, enrollment: dict
) -> None:
    expected = {
        "capability_identity": selected_arm["capability_identity"],
        "development_attestation_id": selected_arm[
            "development_attestation_id"
        ],
        "development_attestation_sha256": selected_arm[
            "development_attestation_sha256"
        ],
        "consumer_compatibility_class": selected_arm[
            "consumer_compatibility_class"
        ],
        "configuration_fingerprint": selected_arm[
            "configuration_fingerprint"
        ],
        "environment_fingerprint": selected_arm[
            "environment_fingerprint"
        ],
        "data_fingerprint": selected_arm["data_fingerprint"],
        "cohort_manifest_sha256": definition["cohort"][
            "case_manifest_ref"
        ]["sha256"],
        "evaluator_version": definition["evaluator"]["version"],
        "evaluator_contract_sha256": definition["evaluator"][
            "contract_hash"
        ],
        "observation_window": definition["observation_window"],
    }
    for field, value in expected.items():
        if enrollment.get(field) != value:
            raise ValueError(f"iteration enrollment {field} mismatch")
    if enrollment["consumer_compatibility_class"] != "compatible":
        raise ValueError("iteration enrollment is not compatible")


def observation_rejection(
    state: dict,
    definition: dict,
    selected_arm: dict,
    enrollment: dict,
    observation: dict,
) -> str | None:
    try:
        require_enrollment_parity(definition, selected_arm, enrollment)
    except ValueError:
        return "enrollment_definition_mismatch"
    expected = {
        "iteration_id": definition["iteration_id"],
        "arm_id": selected_arm["arm_id"],
        "enrollment_id": enrollment["enrollment_id"],
        "terminal_receipt_id": enrollment["terminal_receipt_id"],
        "case_id": enrollment["case_id"],
        "capability_identity": selected_arm["capability_identity"],
        "adapter_contract_version": enrollment[
            "adapter_contract_version"
        ],
        "descriptor_sha256": enrollment["descriptor_sha256"],
        "evaluator_id": definition["evaluator"]["evaluator_id"],
        "evaluator_version": definition["evaluator"]["version"],
        "development_attestation_id": selected_arm[
            "development_attestation_id"
        ],
        "development_attestation_sha256": selected_arm[
            "development_attestation_sha256"
        ],
        "consumer_compatibility_class": "compatible",
        "configuration_fingerprint": selected_arm[
            "configuration_fingerprint"
        ],
        "environment_fingerprint": selected_arm[
            "environment_fingerprint"
        ],
        "data_fingerprint": selected_arm["data_fingerprint"],
    }
    for field, value in expected.items():
        if observation.get(field) != value:
            return f"{field}_mismatch"
    if observation["comparability_key"] != comparability_key(
        definition, observation["metric_id"]
    ):
        return "comparability_key_mismatch"
    if observation["observation_id"] in state.get(
        "accepted_observation_ids", []
    ):
        return "duplicate_observation"
    if (
        observation.get("status") != "accepted_candidate"
        or observation.get("quality_state") != "valid"
    ):
        return "observation_not_valid"
    return None


def require_evaluation_parity(
    state: dict, definition: dict, evaluation: dict
) -> None:
    expected_attestation = sha256_hex(
        sorted(
            item["development_attestation_sha256"]
            for item in definition["arms"]
        )
    )
    expected = {
        "iteration_id": definition["iteration_id"],
        "definition_sha256": definition["definition_sha256"],
        "development_attestation_set_sha256": expected_attestation,
        "consumer_compatibility_class": "compatible",
        "evaluator_id": definition["evaluator"]["evaluator_id"],
        "evaluator_version": definition["evaluator"]["version"],
        "frontier_sequence": state["evidence_frontier"][
            "last_observation_sequence"
        ],
        "frontier_hash": state["evidence_frontier"]["frontier_hash"],
    }
    for field, value in expected.items():
        if evaluation.get(field) != value:
            raise ValueError(f"iteration evaluation {field} mismatch")
    gate_ids = tuple(
        result["gate_id"] for result in evaluation["gate_results"]
    )
    if gate_ids != PROMOTION_GATE_ORDER:
        raise ValueError("iteration evaluation gate order is invalid")
    if evaluation["recommendation"] == "promote":
        if (
            evaluation["decision"] != "pass"
            or any(
                result["status"] != "pass"
                for result in evaluation["gate_results"]
            )
        ):
            raise ValueError(
                "promotion requires every mandatory gate to pass"
            )
