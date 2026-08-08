from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)

from alembic_migrations.postgres import durable_outcome_lookup_v1
from app.services.workflow.durable_state import outcome_adapter_activation
from app.services.workflow.durable_state import terminal_outcome_service
from app.services.workflow.durable_state.outcome_adapter_activation import (
    materialize_declared_outcome_adapter,
)
from app.services.workflow.durable_state.outcome_adapter_resolver import (
    SNAPSHOT_INDEX_KEY,
    attach_outcome_adapter_snapshot,
)
from app.services.workflow.durable_state.outcome_evidence_repository import (
    OutcomeEvidenceRepository,
)
from app.services.workflow.durable_state.outcome_runtime_trust import (
    OutcomeRuntimeTrust,
)
from app.services.workflow.durable_state.outcome_task_admission import (
    build_outcome_task_admission,
    verify_outcome_task_admission,
)
from app.services.workflow.durable_state.signature import Ed25519Signer

H = "0" * 64


def _template(capability_code: str) -> dict:
    return {
        "descriptor_id": f"descriptor:{capability_code}",
        "port_id": "mindscape.product-outcome-adapter-port.v1",
        "contract_export_id": "product_outcome_adapter",
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
            "mindscape://durable-product-semantic-workflow/v1/" "outcome_observation"
        ),
        "evaluator_entrypoint": (
            f"capabilities.{capability_code}.services.outcome:evaluate"
        ),
        "review_lens": None,
        "authorized_lane": "runner:existing",
    }


def _entry(capability_code: str, directory: Path) -> dict:
    return {
        "directory": directory,
        "manifest": {
            "code": capability_code,
            "version": "1.0.0",
            "contract_exports": [
                {
                    "contract_id": "product_outcome_adapter",
                    "module": (
                        f"capabilities.{capability_code}.schema."
                        "product_outcome_adapter"
                    ),
                    "version": "1.0.0",
                }
            ],
            "product_outcome_adapter": {
                "descriptor_factory": (
                    f"capabilities.{capability_code}.services."
                    "outcome:build_descriptor"
                )
            },
        },
    }


@pytest.mark.parametrize(
    "capability_code",
    ["alpha_capability", "beta_capability"],
)
def test_activation_materializes_arbitrary_capability_without_host_literal(
    monkeypatch,
    tmp_path,
    capability_code,
) -> None:
    trust = OutcomeRuntimeTrust(
        descriptor_signer=Ed25519Signer(Ed25519PrivateKey.generate()),
        observation_signer=Ed25519Signer(Ed25519PrivateKey.generate()),
    )
    monkeypatch.setattr(
        outcome_adapter_activation,
        "resolve_capability_backend_callable",
        lambda **_kwargs: lambda: _template(capability_code),
    )
    entry = _entry(capability_code, tmp_path)
    snapshot = materialize_declared_outcome_adapter(
        entry,
        capability_code=capability_code,
        installed_manifest_sha256=H,
        installed_artifact_sha256=H,
        trust=trust,
        runtime_active=True,
    )
    assert snapshot is not None
    assert snapshot.provider_pack == capability_code
    assert snapshot.runtime_active is True
    assert snapshot.descriptor["manifest_sha256"] == H
    assert snapshot.descriptor["installed_artifact_sha256"] == H


def test_activation_preflight_isolated_until_route_activation_succeeds(
    monkeypatch,
    tmp_path,
) -> None:
    from app.services import capability_runtime_activation
    from backend.app.services.workflow.durable_state import (
        outcome_adapter_activation as runtime_adapter_activation,
    )
    from backend.app.services.workflow.durable_state.outcome_runtime_trust import (
        OutcomeRuntimeTrust as RuntimeOutcomeTrust,
    )

    capability_code = "delta_capability"
    trust = OutcomeRuntimeTrust(
        descriptor_signer=Ed25519Signer(Ed25519PrivateKey.generate()),
        observation_signer=Ed25519Signer(Ed25519PrivateKey.generate()),
    )
    monkeypatch.setattr(
        outcome_adapter_activation,
        "resolve_capability_backend_callable",
        lambda **_kwargs: lambda: _template(capability_code),
    )
    monkeypatch.setattr(
        runtime_adapter_activation,
        "resolve_capability_backend_callable",
        lambda **_kwargs: lambda: _template(capability_code),
    )
    monkeypatch.setattr(
        RuntimeOutcomeTrust,
        "from_mounted_files",
        classmethod(lambda cls: trust),
    )
    entry = _entry(capability_code, tmp_path)
    context = capability_runtime_activation._prepare_outcome_adapter_context(
        entry,
        capability_code=capability_code,
        manifest_sha256=H,
        installed_artifact_sha256=H,
    )
    prepared = (
        capability_runtime_activation._materialize_prepared_outcome_adapter(
            entry,
            capability_code=capability_code,
            manifest_sha256=H,
            context=context,
        )
    )
    assert prepared is not None
    assert SNAPSHOT_INDEX_KEY not in entry

    readback = capability_runtime_activation._attach_prepared_outcome_adapter(
        entry,
        prepared,
    )
    assert readback["state"] == "materialized"
    assert len(entry[SNAPSHOT_INDEX_KEY]) == 1


def test_snapshot_attachment_is_idempotent_and_conflict_closed(
    monkeypatch,
    tmp_path,
) -> None:
    capability_code = "epsilon_capability"
    trust = OutcomeRuntimeTrust(
        descriptor_signer=Ed25519Signer(Ed25519PrivateKey.generate()),
        observation_signer=Ed25519Signer(Ed25519PrivateKey.generate()),
    )
    monkeypatch.setattr(
        outcome_adapter_activation,
        "resolve_capability_backend_callable",
        lambda **_kwargs: lambda: _template(capability_code),
    )
    entry = _entry(capability_code, tmp_path)
    snapshot = materialize_declared_outcome_adapter(
        entry,
        capability_code=capability_code,
        installed_manifest_sha256=H,
        installed_artifact_sha256=H,
        trust=trust,
        runtime_active=True,
    )
    assert attach_outcome_adapter_snapshot(entry, snapshot) is snapshot
    with pytest.raises(ValueError, match="identity conflict"):
        attach_outcome_adapter_snapshot(
            entry,
            replace(snapshot, runtime_active=False),
        )


def test_pack_cannot_supply_runtime_owned_descriptor_fields(
    monkeypatch,
    tmp_path,
) -> None:
    capability_code = "gamma_capability"
    trust = OutcomeRuntimeTrust(
        descriptor_signer=Ed25519Signer(Ed25519PrivateKey.generate()),
        observation_signer=Ed25519Signer(Ed25519PrivateKey.generate()),
    )
    template = {**_template(capability_code), "signature": "pack-owned"}
    monkeypatch.setattr(
        outcome_adapter_activation,
        "resolve_capability_backend_callable",
        lambda **_kwargs: lambda: template,
    )
    with pytest.raises(ValueError, match="unknown_fields"):
        materialize_declared_outcome_adapter(
            _entry(capability_code, tmp_path),
            capability_code=capability_code,
            installed_manifest_sha256=H,
            installed_artifact_sha256=H,
            trust=trust,
            runtime_active=True,
        )


def test_pack_cannot_select_a_second_runner_lane(
    monkeypatch,
    tmp_path,
) -> None:
    capability_code = "lane_capability"
    trust = OutcomeRuntimeTrust(
        descriptor_signer=Ed25519Signer(Ed25519PrivateKey.generate()),
        observation_signer=Ed25519Signer(Ed25519PrivateKey.generate()),
    )
    template = {
        **_template(capability_code),
        "authorized_lane": "runner:pack-owned",
    }
    monkeypatch.setattr(
        outcome_adapter_activation,
        "resolve_capability_backend_callable",
        lambda **_kwargs: lambda: template,
    )
    with pytest.raises(ValueError, match="authorized_lane_mismatch"):
        materialize_declared_outcome_adapter(
            _entry(capability_code, tmp_path),
            capability_code=capability_code,
            installed_manifest_sha256=H,
            installed_artifact_sha256=H,
            trust=trust,
            runtime_active=True,
        )


def test_outcome_task_admission_uses_descriptor_authority_only() -> None:
    descriptor_signer = Ed25519Signer(Ed25519PrivateKey.generate())
    observation_signer = Ed25519Signer(Ed25519PrivateKey.generate())
    receipt = build_outcome_task_admission(
        descriptor_signer,
        task_id="task:1",
        workspace_id="workspace:1",
        terminal_receipt_id="terminal:1",
        enrollment_id="enrollment:1",
        iteration_id="iteration:1",
        descriptor_sha256=H,
        task_params={"descriptor_sha256": H},
    )
    verified = verify_outcome_task_admission(
        receipt,
        expected_task_id="task:1",
        expected_workspace_id="workspace:1",
        expected_params={"descriptor_sha256": H},
        verification_keys={descriptor_signer.key_id: descriptor_signer.public_key()},
    )
    assert verified["authorized_lane"] == "runner:existing"
    with pytest.raises(ValueError, match="task_params_sha256_mismatch"):
        verify_outcome_task_admission(
            receipt,
            expected_task_id="task:1",
            expected_workspace_id="workspace:1",
            expected_params={"descriptor_sha256": "1" * 64},
            verification_keys={
                descriptor_signer.key_id: descriptor_signer.public_key()
            },
        )
    with pytest.raises(ValueError, match="key_unavailable"):
        verify_outcome_task_admission(
            receipt,
            expected_task_id="task:1",
            expected_workspace_id="workspace:1",
            expected_params={"descriptor_sha256": H},
            verification_keys={
                observation_signer.key_id: observation_signer.public_key()
            },
        )


def test_outcome_runtime_rejects_shared_descriptor_and_observation_key() -> None:
    signer = Ed25519Signer(Ed25519PrivateKey.generate())
    with pytest.raises(ValueError, match="authorities must be distinct"):
        OutcomeRuntimeTrust(
            descriptor_signer=signer,
            observation_signer=signer,
        )


def test_result_ref_budget_fails_before_database_read() -> None:
    calls = []

    class Connection:
        def execute(self, *_args, **_kwargs):
            calls.append("execute")
            raise AssertionError("database read must not run")

    with pytest.raises(ValueError, match="byte_budget_exceeded"):
        OutcomeEvidenceRepository().read_result_ref(
            Connection(),
            result_ref={
                "uri": "artifact://too-large",
                "sha256": H,
                "bytes": 16_385,
                "schema_id": "result.v1",
            },
            workspace_id="workspace:1",
        )
    assert calls == []


def test_outcome_lookup_migration_is_bounded_and_idempotent() -> None:
    statements = []

    class Op:
        @staticmethod
        def execute(statement):
            statements.append(str(statement))

    durable_outcome_lookup_v1.upgrade(Op)
    assert statements[:2] == [
        "SET LOCAL lock_timeout = '5s'",
        "SET LOCAL statement_timeout = '30s'",
    ]
    ddl = "\n".join(statements[2:])
    assert ddl.count("CREATE UNIQUE INDEX IF NOT EXISTS") == 2
    assert "uq_durable_workflow_terminal_receipt_id" in ddl
    assert "uq_durable_workflow_enrollment_terminal_receipt" in ddl


def test_terminal_composition_enqueues_only_after_transaction_commit(
    monkeypatch,
) -> None:
    events = []
    terminal = {
        "receipt_id": "terminal:1",
        "workspace_id": "workspace:1",
    }
    enrollment = {"enrollment_id": "enrollment:1"}

    @contextmanager
    def transaction():
        events.append("transaction:open")
        yield object()
        events.append("transaction:committed")

    class FakeHandler:
        def __init__(self, *_args, **_kwargs):
            pass

        def prepare(self, *_args, **_kwargs):
            events.append("task:intent")
            return {
                "status": "task_created",
                "task": ("created-task", True),
                "rejection": None,
            }

    class TaskAdapter:
        def create_with_conn(self, *_args, **_kwargs):
            raise AssertionError("fake handler owns the task intent")

        def finalize_after_commit(self, created):
            assert created == ("created-task", True)
            events.append("task:enqueued")
            return SimpleNamespace(id="task:1")

    class Facade:
        def append_execution_terminal(self, *_args, **_kwargs):
            events.append("terminal:recorded")
            return terminal

        def append_outcome_evaluation_intent(self, *_args, **_kwargs):
            raise AssertionError("fake handler owns the linkage")

    class Evidence:
        def enrollment_for_terminal(self, *_args, **_kwargs):
            events.append("enrollment:read")
            return {"enrollment": enrollment}

    monkeypatch.setattr(
        terminal_outcome_service,
        "OutcomeEvaluationTaskHandler",
        FakeHandler,
    )
    service = terminal_outcome_service.DurableTerminalOutcomeService(
        transaction=transaction,
        facade=Facade(),
        resolver=object(),
        task_adapter=TaskAdapter(),
        evidence_repository=Evidence(),
        capability_entries={},
        terminal_verification_keys={},
        enrollment_verification_keys={},
    )
    result = service.record_terminal()
    assert result["outcome_evaluation"]["task_id"] == "task:1"
    assert events == [
        "transaction:open",
        "terminal:recorded",
        "enrollment:read",
        "task:intent",
        "transaction:committed",
        "task:enqueued",
    ]


def test_generic_outcome_runtime_has_no_pack_literal_or_resource_owner() -> None:
    root = Path(__file__).resolve().parents[1] / "app/services/workflow/durable_state"
    paths = (
        root / "outcome_adapter_activation.py",
        root / "outcome_runtime_trust.py",
        root / "outcome_evidence_repository.py",
        root / "outcome_task_adapter.py",
        root / "outcome_task_admission.py",
        root / "outcome_task_dispatcher.py",
        root / "terminal_outcome_service.py",
    )
    source = "\n".join(path.read_text() for path in paths)
    for forbidden in (
        "walkto_lab",
        "capabilities.walkto",
        "create_engine",
        "QueuePool",
        "setInterval",
        "EventSource",
    ):
        assert forbidden not in source
    assert all(len(path.read_text().splitlines()) < 500 for path in paths)
