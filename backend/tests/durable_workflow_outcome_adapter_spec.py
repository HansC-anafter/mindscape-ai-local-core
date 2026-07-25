from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.services.workflow.durable_state.canonical_json import encode, sha256_hex
from app.services.workflow.durable_state.outcome_adapter_port import (
    ProductOutcomeAdapterPort,
)
from app.services.workflow.durable_state.outcome_adapter_resolver import (
    CONTRACT_EXPORT_ID,
    PORT_ID,
    OutcomeAdapterResolver,
    materialize_outcome_adapter_snapshot,
)
from app.services.workflow.durable_state.outcome_evaluation_task_handler import (
    OutcomeEvaluationTaskHandler,
)
from app.services.workflow.durable_state.signature import Ed25519Signer, verify
from durable_workflow_ledger_spec import H, NOW, identity


@pytest.fixture
def signer() -> Ed25519Signer:
    return Ed25519Signer(Ed25519PrivateKey.generate())


def _signed_descriptor(
    capability_code: str, signer: Ed25519Signer
) -> dict:
    core = {
        "descriptor_id": f"descriptor:{capability_code}",
        "port_id": PORT_ID,
        "contract_export_id": CONTRACT_EXPORT_ID,
        "adapter_contract_version": "1.0.0",
        "evaluator_version": "evaluator.v1",
        "capability_identity": {
            "capability_code": capability_code,
            "pack_version": "1.0.0",
            "release_id": f"release:{capability_code}",
        },
        "selector": {
            "terminal_states": ["succeeded"],
            "result_schema_ids": ["result.v1"],
        },
        "input_schema_id": (
            "mindscape://durable-product-semantic-workflow/v1/"
            "execution_terminal_receipt"
        ),
        "output_schema_id": (
            "mindscape://durable-product-semantic-workflow/v1/"
            "outcome_observation"
        ),
        "evaluator_entrypoint": (
            f"capabilities.{capability_code}.services.outcome:evaluate"
        ),
        "review_lens": {
            "component_code": "ProductOutcomeReviewLens",
            "integrity": (
                "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
            ),
            "runtime": "esm",
            "export": "default",
        },
        "authorized_lane": "runner:existing",
        "installed_artifact_sha256": H,
        "manifest_sha256": H,
        "activated_at": NOW,
        "key_id": signer.key_id,
    }
    hashed = {**core, "descriptor_sha256": sha256_hex(core)}
    return {**hashed, "signature": signer.sign(encode(hashed)).value}


def _materialize(
    capability_code: str,
    signer: Ed25519Signer,
    *,
    entry: dict | None = None,
):
    capability_entry = entry if entry is not None else {}
    descriptor = _signed_descriptor(capability_code, signer)
    snapshot = materialize_outcome_adapter_snapshot(
        capability_entry,
        capability_code=capability_code,
        contract_export={
            "contract_id": CONTRACT_EXPORT_ID,
            "module": (
                f"capabilities.{capability_code}.schema."
                "product_outcome_adapter"
            ),
            "version": "1.0.0",
        },
        descriptor=descriptor,
        installed_manifest_sha256=H,
        installed_artifact_sha256=H,
        verification_keys={signer.key_id: signer.public_key()},
        capability_dir=Path(f"/installed/{capability_code}"),
        runtime_active=True,
    )
    return capability_entry, descriptor, snapshot


def _pin(capability_code: str, descriptor: dict) -> dict[str, str]:
    return {
        "capability_code": capability_code,
        "port_id": PORT_ID,
        "contract_export_id": CONTRACT_EXPORT_ID,
        "adapter_contract_version": descriptor[
            "adapter_contract_version"
        ],
        "descriptor_sha256": descriptor["descriptor_sha256"],
        "evaluator_version": descriptor["evaluator_version"],
    }


def _signed_terminal(
    capability_code: str, signer: Ed25519Signer
) -> dict:
    execution_identity = identity(f"outcome:{capability_code}")
    execution_identity["capability_identity"] = {
        "capability_code": capability_code,
        "pack_version": "1.0.0",
        "manifest_sha256": H,
    }
    fields = (
        "workflow_id",
        "root_workflow_id",
        "execution_id",
        "attempt_id",
        "workspace_id",
        "capability_identity",
        "development_attestation_id",
        "development_attestation_sha256",
        "consumer_compatibility_class",
        "configuration_fingerprint",
        "environment_fingerprint",
        "data_fingerprint",
        "workflow_definition_version",
        "reducer_version",
        "effect_adapter_registry_version",
        "runtime_build_id",
    )
    unsigned = {
        "receipt_id": f"terminal:{capability_code}",
        **{field: execution_identity[field] for field in fields},
        "terminal_sequence": 2,
        "terminal_state": "succeeded",
        "terminal_event_hash": H,
        "result_ref": {
            "uri": f"object://result/{capability_code}",
            "sha256": H,
            "bytes": 1,
            "schema_id": "result.v1",
        },
        "resource_summary": {
            "duration_ms": 1,
            "attempts": 1,
            "task_count": 1,
        },
        "artifact_refs": [],
        "started_at": NOW,
        "completed_at": NOW,
        "key_id": signer.key_id,
    }
    return {**unsigned, "signature": signer.sign(encode(unsigned)).value}


def _enrollment(
    capability_code: str,
    descriptor: dict,
    terminal: dict,
    signer: Ed25519Signer,
) -> dict:
    unsigned = {
        "enrollment_id": f"enrollment:{capability_code}",
        "iteration_id": "iteration:1",
        "arm_id": "control",
        "case_id": "case:1",
        "terminal_receipt_id": terminal["receipt_id"],
        "capability_identity": terminal["capability_identity"],
        "port_id": PORT_ID,
        "contract_export_id": CONTRACT_EXPORT_ID,
        "adapter_contract_version": descriptor[
            "adapter_contract_version"
        ],
        "descriptor_sha256": descriptor["descriptor_sha256"],
        "review_lens": descriptor.get("review_lens"),
        "evaluator_version": descriptor["evaluator_version"],
        "evaluator_contract_sha256": H,
        "cohort_manifest_sha256": H,
        "development_attestation_id": terminal[
            "development_attestation_id"
        ],
        "development_attestation_sha256": terminal[
            "development_attestation_sha256"
        ],
        "consumer_compatibility_class": terminal[
            "consumer_compatibility_class"
        ],
        "configuration_fingerprint": terminal[
            "configuration_fingerprint"
        ],
        "environment_fingerprint": terminal["environment_fingerprint"],
        "data_fingerprint": terminal["data_fingerprint"],
        "observation_window": {"starts_at": NOW, "ends_at": NOW},
        "budget": {"max_attempts": 1, "timeout_seconds": 30},
        "idempotency_key": f"enrollment:{capability_code}",
        "enrolled_at": NOW,
        "key_id": signer.key_id,
    }
    return {
        **unsigned,
        "signature": signer.sign(encode(unsigned)).value,
    }


def _resign_enrollment(
    enrollment: dict, signer: Ed25519Signer
) -> dict:
    unsigned = {
        key: value for key, value in enrollment.items() if key != "signature"
    }
    return {
        **unsigned,
        "signature": signer.sign(encode(unsigned)).value,
    }


@pytest.mark.parametrize(
    "capability_code", ["alpha_capability", "beta_capability"]
)
def test_two_arbitrary_capabilities_resolve_without_host_change(
    capability_code, signer
) -> None:
    entry, descriptor, snapshot = _materialize(capability_code, signer)
    resolver = OutcomeAdapterResolver(signer)
    result = resolver.resolve(
        {capability_code: entry}, _pin(capability_code, descriptor)
    )
    assert result.snapshot == snapshot
    assert result.rejection is None


def test_duplicate_and_hash_mismatch_fail_signed_without_task(signer) -> None:
    capability_code = "gamma_capability"
    entry, descriptor, _snapshot = _materialize(capability_code, signer)
    _materialize(capability_code, signer, entry=entry)
    resolver = OutcomeAdapterResolver(signer)
    ambiguous = resolver.resolve(
        {capability_code: entry}, _pin(capability_code, descriptor)
    )
    assert ambiguous.snapshot is None
    assert ambiguous.rejection["reason"] == "adapter_ambiguous"
    signed = {
        key: value
        for key, value in ambiguous.rejection.items()
        if key != "signature"
    }
    verify(
        signer.public_key(),
        encode(signed),
        ambiguous.rejection["signature"],
    )

    wrong = _pin(capability_code, descriptor)
    wrong["descriptor_sha256"] = "1" * 64
    missing = resolver.resolve({capability_code: {}}, wrong)
    assert missing.rejection["reason"] == "adapter_not_found"


def test_unenrolled_and_parity_rejected_terminals_create_no_task(
    signer,
) -> None:
    capability_code = "delta_capability"
    entry, descriptor, _snapshot = _materialize(capability_code, signer)
    terminal = _signed_terminal(capability_code, signer)
    created = []
    linked = []
    handler = OutcomeEvaluationTaskHandler(
        OutcomeAdapterResolver(signer),
        create_task_with_conn=lambda *_args, **_kwargs: created.append(
            _args[1]
        ),
        append_linkage_with_conn=lambda *_args, **_kwargs: linked.append(
            _args[1]
        ),
        terminal_verification_keys={signer.key_id: signer.public_key()},
        enrollment_verification_keys={signer.key_id: signer.public_key()},
    )
    not_enrolled = handler.prepare(
        object(),
        capability_entries={capability_code: entry},
        terminal_receipt=terminal,
        enrollment=None,
    )
    assert not_enrolled["status"] == "not_enrolled"

    enrollment = _enrollment(
        capability_code, descriptor, terminal, signer
    )
    enrollment["data_fingerprint"] = "1" * 64
    enrollment = _resign_enrollment(enrollment, signer)
    rejected = handler.prepare(
        object(),
        capability_entries={capability_code: entry},
        terminal_receipt=terminal,
        enrollment=enrollment,
    )
    assert rejected["status"] == "rejected"
    assert rejected["rejection"]["reason"] == "data_fingerprint_mismatch"
    assert created == []
    assert linked == []


def test_exact_enrollment_creates_one_existing_lane_intent(signer) -> None:
    capability_code = "epsilon_capability"
    entry, descriptor, snapshot = _materialize(capability_code, signer)
    terminal = _signed_terminal(capability_code, signer)
    enrollment = _enrollment(
        capability_code, descriptor, terminal, signer
    )
    created = []
    linked = []

    def create(_conn, task, *, idempotency_key):
        created.append((task, idempotency_key))
        return task

    handler = OutcomeEvaluationTaskHandler(
        OutcomeAdapterResolver(signer),
        create_task_with_conn=create,
        append_linkage_with_conn=lambda _conn, event: linked.append(event),
        terminal_verification_keys={signer.key_id: signer.public_key()},
        enrollment_verification_keys={signer.key_id: signer.public_key()},
    )
    result = handler.prepare(
        object(),
        capability_entries={capability_code: entry},
        terminal_receipt=terminal,
        enrollment=enrollment,
    )
    assert result["status"] == "task_created"
    assert result["snapshot"] == snapshot
    assert len(created) == len(linked) == 1
    assert created[0][0]["task_type"] == "product_outcome_evaluation"
    assert created[0][0]["authorized_lane"] == "runner:existing"
    assert result["wake_after_commit"] is True


def test_review_lens_mismatch_fails_before_task_creation(signer) -> None:
    capability_code = "lens_capability"
    entry, descriptor, _snapshot = _materialize(capability_code, signer)
    terminal = _signed_terminal(capability_code, signer)
    enrollment = _enrollment(
        capability_code, descriptor, terminal, signer
    )
    enrollment["review_lens"] = {
        **enrollment["review_lens"],
        "component_code": "DifferentReviewLens",
    }
    enrollment = _resign_enrollment(enrollment, signer)
    created = []
    handler = OutcomeEvaluationTaskHandler(
        OutcomeAdapterResolver(signer),
        create_task_with_conn=lambda *_args, **_kwargs: created.append(
            _args[1]
        ),
        append_linkage_with_conn=lambda *_args, **_kwargs: None,
        terminal_verification_keys={signer.key_id: signer.public_key()},
        enrollment_verification_keys={signer.key_id: signer.public_key()},
    )
    rejected = handler.prepare(
        object(),
        capability_entries={capability_code: entry},
        terminal_receipt=terminal,
        enrollment=enrollment,
    )
    assert rejected["status"] == "rejected"
    assert rejected["rejection"]["reason"] == "review_lens_pin_mismatch"
    assert created == []


def test_invalid_enrollment_signature_creates_no_task(signer) -> None:
    capability_code = "eta_capability"
    entry, descriptor, _snapshot = _materialize(capability_code, signer)
    terminal = _signed_terminal(capability_code, signer)
    enrollment = _enrollment(
        capability_code, descriptor, terminal, signer
    )
    enrollment["signature"] = "invalid"
    created = []
    linked = []
    handler = OutcomeEvaluationTaskHandler(
        OutcomeAdapterResolver(signer),
        create_task_with_conn=lambda *_args, **_kwargs: created.append(
            _args[1]
        ),
        append_linkage_with_conn=lambda *_args, **_kwargs: linked.append(
            _args[1]
        ),
        terminal_verification_keys={signer.key_id: signer.public_key()},
        enrollment_verification_keys={signer.key_id: signer.public_key()},
    )
    rejected = handler.prepare(
        object(),
        capability_entries={capability_code: entry},
        terminal_receipt=terminal,
        enrollment=enrollment,
    )
    assert rejected["status"] == "rejected"
    assert (
        rejected["rejection"]["reason"]
        == "enrollment_signature_invalid"
    )
    assert created == []
    assert linked == []


def test_port_verifies_generic_observation_identity_and_signature(
    signer,
) -> None:
    capability_code = "zeta_capability"
    _entry, descriptor, snapshot = _materialize(capability_code, signer)
    terminal = _signed_terminal(capability_code, signer)
    enrollment = _enrollment(
        capability_code, descriptor, terminal, signer
    )
    unsigned_observation = {
        "observation_id": "observation:1",
        "iteration_id": enrollment["iteration_id"],
        "arm_id": enrollment["arm_id"],
        "case_id": enrollment["case_id"],
        "terminal_receipt_id": terminal["receipt_id"],
        "enrollment_id": enrollment["enrollment_id"],
        "descriptor_id": descriptor["descriptor_id"],
        "capability_identity": terminal["capability_identity"],
        "adapter_contract_version": descriptor[
            "adapter_contract_version"
        ],
        "descriptor_sha256": descriptor["descriptor_sha256"],
        "evaluator_id": "evaluator:fixture",
        "evaluator_version": descriptor["evaluator_version"],
        "development_attestation_id": enrollment[
            "development_attestation_id"
        ],
        "development_attestation_sha256": enrollment[
            "development_attestation_sha256"
        ],
        "consumer_compatibility_class": "compatible",
        "configuration_fingerprint": enrollment[
            "configuration_fingerprint"
        ],
        "environment_fingerprint": enrollment["environment_fingerprint"],
        "data_fingerprint": enrollment["data_fingerprint"],
        "metric_id": "quality",
        "missing_reason": "source metric was not emitted",
        "denominator": 1,
        "unit": None,
        "comparability_key": "cohort:1",
        "quality_state": "needs_review",
        "provenance_hash": H,
        "status": "needs_human_review",
        "observed_at": NOW,
        "key_id": signer.key_id,
    }
    observation = {
        **unsigned_observation,
        "signature": signer.sign(encode(unsigned_observation)).value,
    }
    port = ProductOutcomeAdapterPort(
        load_callable=lambda **_kwargs: lambda _envelope: observation,
        observation_verification_keys={
            signer.key_id: signer.public_key()
        },
    )
    assert port.evaluate(
        snapshot=snapshot,
        terminal_receipt=terminal,
        enrollment=enrollment,
    ) == [observation]


def test_generic_source_has_no_pack_dispatch_or_resource_owner() -> None:
    root = (
        Path(__file__).resolve().parents[1]
        / "app/services/workflow/durable_state"
    )
    paths = [
        root / "outcome_adapter_port.py",
        root / "outcome_adapter_resolver.py",
        root / "outcome_evaluation_task_handler.py",
    ]
    source = "\n".join(path.read_text() for path in paths)
    for forbidden in (
        "capabilities.ig",
        "capabilities.yogacoach",
        "playbook_code",
        "create_engine",
        ".commit(",
        "new EventSource",
        "setInterval",
    ):
        assert forbidden not in source
    resolver_source = paths[1].read_text()
    for forbidden in ("read_text(", "read_bytes(", "open(", "Path("):
        assert forbidden not in resolver_source
    assert all(len(path.read_text().splitlines()) < 500 for path in paths)
