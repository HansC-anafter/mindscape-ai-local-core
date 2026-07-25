from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text

from alembic_migrations.postgres import durable_workflow_v1
from app.services.workflow.durable_state.canonical_json import (
    encode,
    sha256_hex,
)
from app.services.workflow.durable_state.product_iteration_contract import (
    PROMOTION_GATE_ORDER,
    comparability_key,
    product_iteration_definition_sha256,
)
from durable_workflow_ledger_spec import ACTOR, H, NOW, identity


@pytest.fixture(scope="module")
def engine():
    dsn = os.environ.get("DURABLE_WORKFLOW_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("isolated PostgreSQL URL is required")
    created = create_engine(dsn, pool_size=4, max_overflow=0)
    with created.begin() as conn:
        exists = conn.execute(
            text(
                "SELECT to_regclass("
                "'public.durable_workflow_instances')"
            )
        ).scalar_one()
        if exists is None:
            class Op:
                @staticmethod
                def execute(statement):
                    conn.exec_driver_sql(statement)

            durable_workflow_v1.upgrade(Op)
    yield created
    created.dispose()


def definition(
    workflow_id: str,
    *,
    state: str = "draft",
    minimum_sample_size: int = 2,
    parent_iteration_id: str | None = None,
    max_evaluation_attempts: int = 1,
) -> dict:
    effective_minimum = max(2, minimum_sample_size)
    value = {
        "iteration_id": workflow_id,
        "revision": 1,
        "parent_iteration_id": parent_iteration_id,
        "workspace_id": "workspace:test",
        "objective": "Improve a generic product outcome.",
        "state": state,
        "arms": [
            {
                "arm_id": "candidate",
                "development_attestation_id": "attestation:test",
                "development_attestation_sha256": H,
                "consumer_compatibility_class": "compatible",
                "capability_identity": {
                    "capability_code": "test_capability",
                    "pack_version": "1.0.0",
                    "manifest_sha256": H,
                },
                "configuration_fingerprint": H,
                "environment_fingerprint": H,
                "data_fingerprint": H,
                "consumer_impact_manifest_sha256": H,
                "allocation_weight": 1,
            }
        ],
        "cohort": {
            "definition_hash": H,
            "case_manifest_ref": {
                "uri": f"object://cohort/{workflow_id}",
                "sha256": H,
                "bytes": 1,
                "schema_id": "cohort.v1",
            },
            "population": effective_minimum,
            "holdout": True,
            "randomization_method": (
                "deterministic stratified assignment"
            ),
        },
        "metric_definitions": [
            {
                "metric_id": "quality",
                "direction": "increase",
                "denominator_definition": "signed enrolled cases",
                "quality_gate": "valid accepted observations only",
            }
        ],
        "validation_design": {
            "power": 0.8,
            "minimum_detectable_effect": 0.1,
            "minimum_sample_size": effective_minimum,
            "stopping_rule": "fixed sample",
            "multiplicity_control": "holm",
            "holdout_policy": "immutable holdout",
            "leakage_guard": "identity partition",
            "missing_data_policy": "missing remains explicit",
            "sequential_look_schedule": [effective_minimum],
            "evaluator_calibration": "gold set v1",
            "evaluator_drift_threshold": 0.05,
            "adjudication_policy": "two-owner review",
        },
        "evaluator": {
            "evaluator_id": "evaluator:test",
            "version": "evaluator.v1",
            "contract_hash": H,
        },
        "evidence_frontier": {
            "last_observation_sequence": 0,
            "frontier_hash": H,
        },
        "promotion_policy": {
            "required_gates": list(PROMOTION_GATE_ORDER),
            "approval_policy_id": "approval-policy:test",
        },
        "observation_window": {"starts_at": NOW, "ends_at": NOW},
        "budget": {
            "max_observations": 10,
            "max_evaluation_attempts": max_evaluation_attempts,
        },
        "release_target": {
            "arm_id": "candidate",
            "owner_id": "release-owner:test",
            "target_revision": "revision:test",
            "target_sha256": H,
        },
        "definition_sha256": H,
        "created_at": NOW,
    }
    if state == "admitted":
        value["admitted_at"] = NOW
    value["definition_sha256"] = product_iteration_definition_sha256(
        value
    )
    return value


def signed(signer, payload: dict) -> dict:
    unsigned = {**payload, "key_id": signer.key_id}
    return {
        **unsigned,
        "signature": signer.sign(encode(unsigned)).value,
    }


def enrollment(
    workflow_id: str, case_id: str, iteration: dict, signer
) -> dict:
    selected_arm = iteration["arms"][0]
    return signed(
        signer,
        {
            "enrollment_id": f"enrollment:{workflow_id}:{case_id}",
            "iteration_id": workflow_id,
            "arm_id": selected_arm["arm_id"],
            "case_id": case_id,
            "terminal_receipt_id": f"terminal:{case_id}",
            "capability_identity": selected_arm["capability_identity"],
            "port_id": "mindscape.product-outcome-adapter-port.v1",
            "contract_export_id": "product_outcome_adapter",
            "adapter_contract_version": "1.0.0",
            "descriptor_sha256": H,
            "review_lens": {
                "component_code": "ProductOutcomeReviewLens",
                "integrity": (
                    "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
                ),
                "runtime": "esm",
                "export": "default",
            },
            "evaluator_version": iteration["evaluator"]["version"],
            "evaluator_contract_sha256": iteration["evaluator"][
                "contract_hash"
            ],
            "cohort_manifest_sha256": iteration["cohort"][
                "case_manifest_ref"
            ]["sha256"],
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
            "observation_window": iteration["observation_window"],
            "budget": {"max_attempts": 1, "timeout_seconds": 30},
            "idempotency_key": f"enrollment:{workflow_id}:{case_id}",
            "enrolled_at": NOW,
        },
    )


def observation(
    enrolled: dict,
    iteration: dict,
    signer,
    *,
    observation_id: str,
    comparable: bool = True,
) -> dict:
    return signed(
        signer,
        {
            "observation_id": observation_id,
            "iteration_id": iteration["iteration_id"],
            "arm_id": enrolled["arm_id"],
            "case_id": enrolled["case_id"],
            "terminal_receipt_id": enrolled["terminal_receipt_id"],
            "enrollment_id": enrolled["enrollment_id"],
            "descriptor_id": "descriptor:test",
            "capability_identity": enrolled["capability_identity"],
            "adapter_contract_version": enrolled[
                "adapter_contract_version"
            ],
            "descriptor_sha256": enrolled["descriptor_sha256"],
            "evaluator_id": iteration["evaluator"]["evaluator_id"],
            "evaluator_version": iteration["evaluator"]["version"],
            "development_attestation_id": enrolled[
                "development_attestation_id"
            ],
            "development_attestation_sha256": enrolled[
                "development_attestation_sha256"
            ],
            "configuration_fingerprint": enrolled[
                "configuration_fingerprint"
            ],
            "environment_fingerprint": enrolled[
                "environment_fingerprint"
            ],
            "data_fingerprint": enrolled["data_fingerprint"],
            "consumer_compatibility_class": "compatible",
            "metric_id": "quality",
            "value": 1,
            "denominator": 1,
            "unit": "ratio",
            "comparability_key": (
                comparability_key(iteration, "quality")
                if comparable
                else "not-comparable"
            ),
            "quality_state": "valid",
            "provenance_hash": H,
            "status": "accepted_candidate",
            "observed_at": NOW,
        },
    )


def evaluation(iteration: dict, projection: dict, signer) -> dict:
    return signed(
        signer,
        {
            "evaluation_id": f"evaluation:{iteration['iteration_id']}",
            "evaluation_attempt_id": "evaluation-attempt:1",
            "iteration_id": iteration["iteration_id"],
            "definition_sha256": iteration["definition_sha256"],
            "development_attestation_set_sha256": sha256_hex([H]),
            "consumer_compatibility_class": "compatible",
            "evaluator_id": iteration["evaluator"]["evaluator_id"],
            "evaluator_version": iteration["evaluator"]["version"],
            "frontier_sequence": projection["evidence_frontier"][
                "last_observation_sequence"
            ],
            "frontier_hash": projection["evidence_frontier"][
                "frontier_hash"
            ],
            "comparability_fingerprint": comparability_key(
                iteration, "quality"
            ),
            "source_observation_ref": {
                "uri": "object://observations/test",
                "sha256": H,
                "bytes": 1,
                "schema_id": "observation-set.v1",
            },
            "gate_results": [
                {
                    "gate_id": gate_id,
                    "status": "pass",
                    "evidence_hash": H,
                }
                for gate_id in PROMOTION_GATE_ORDER
            ],
            "decision": "pass",
            "recommendation": "promote",
            "promotion_effect_receipt_id": None,
            "evaluated_at": NOW,
        },
    )


def open_collecting(
    conn,
    facade,
    workflow_id: str,
    minimum: int = 2,
    max_evaluation_attempts: int = 1,
) -> dict:
    draft = definition(
        workflow_id,
        minimum_sample_size=minimum,
        max_evaluation_attempts=max_evaluation_attempts,
    )
    admitted = definition(
        workflow_id,
        state="admitted",
        minimum_sample_size=minimum,
        max_evaluation_attempts=max_evaluation_attempts,
    )
    facade.open_product_iteration(
        conn,
        identity=identity(workflow_id, "product_iteration"),
        definition=draft,
        actor=ACTOR,
        idempotency_key="define",
    )
    facade.admit_product_iteration(
        conn,
        workflow_id=workflow_id,
        expected_sequence=1,
        definition=admitted,
        actor=ACTOR,
        idempotency_key="admit",
    )
    facade.start_product_iteration_collection(
        conn,
        workflow_id=workflow_id,
        expected_sequence=2,
        actor=ACTOR,
        idempotency_key="collect",
    )
    return admitted
