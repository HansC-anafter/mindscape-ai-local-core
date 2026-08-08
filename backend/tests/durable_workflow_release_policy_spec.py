from __future__ import annotations

import hashlib
from copy import deepcopy
from datetime import datetime

import pytest
from sqlalchemy import text

from alembic_migrations.postgres import (
    durable_workflow_release_policy_owner_receipts_v1,
)
from app.services.workflow.durable_state.release_policy import (
    DurableReleasePolicyConflict,
    DurableReleasePolicyStore,
)
from app.services.workflow.durable_state.canonical_json import encode
from app.services.workflow.durable_state.runtime_owner_receipts import (
    RuntimeOwnerReceiptError,
    verify_owner_decision,
)
from app.services.workspace_capability_admission.durable_workflow_policy import (
    DurableWorkflowAdmissionUnavailable,
    DurableWorkflowPolicyAdapter,
)
from backend.tests.durable_workflow_database import engine
from backend.tests.durable_workflow_owner_receipt_support import (
    H,
    NOW,
    OwnerReceiptFactory,
)


@pytest.fixture
def receipts() -> OwnerReceiptFactory:
    return OwnerReceiptFactory()


def test_runtime_verifier_accepts_exact_owner_and_registry(
    receipts: OwnerReceiptFactory,
) -> None:
    canary = receipts.canary()
    verified = verify_owner_decision(
        canary,
        receipts.registry,
        expected_registry_sha256=receipts.registry_sha256,
        now=NOW,
    )
    assert verified.receipt_id == "receipt:canary"
    assert verified.registry_sha256 == receipts.registry_sha256


def test_corrective_ddl_adds_no_table_or_resource_owner() -> None:
    statements: list[str] = []

    class Op:
        @staticmethod
        def execute(statement):
            statements.append(str(statement))

    durable_workflow_release_policy_owner_receipts_v1.upgrade(Op)
    source = "\n".join(statements).lower()
    assert "create table" not in source
    assert "create engine" not in source
    assert "owner_receipt jsonb" in source
    assert "canary_receipt jsonb" in source
    assert "num_nonnulls" in source
    assert "in (0, 6)" in source


def test_runtime_verifier_rejects_registry_hash_and_unauthorized_type(
    receipts: OwnerReceiptFactory,
) -> None:
    canary = receipts.canary()
    with pytest.raises(
        RuntimeOwnerReceiptError,
        match="trusted_key_registry_sha256_mismatch",
    ):
        verify_owner_decision(
            canary,
            receipts.registry,
            expected_registry_sha256="f" * 64,
            now=NOW,
        )

    unauthorized = deepcopy(receipts.registry)
    unauthorized["keys"][0]["authorized_receipt_types"] = [
        "durable_release_policy_cas"
    ]
    unauthorized_hash = hashlib.sha256(
        encode(unauthorized, max_bytes=4 * 1024 * 1024)
    ).hexdigest()
    with pytest.raises(
        RuntimeOwnerReceiptError,
        match="trusted_key_receipt_type_unauthorized",
    ):
        verify_owner_decision(
            canary,
            unauthorized,
            expected_registry_sha256=unauthorized_hash,
            now=NOW,
        )

    with pytest.raises(
        RuntimeOwnerReceiptError,
        match="verification_clock_timezone_required",
    ):
        verify_owner_decision(
            canary,
            receipts.registry,
            expected_registry_sha256=receipts.registry_sha256,
            now=datetime(2026, 7, 26, 10, 0),
        )


@pytest.mark.parametrize(
    ("canary_kwargs", "cas_kwargs", "expected_error"),
    [
        (
            {"authorization_scopes": ["durable_workflow:enforced"]},
            {},
            "policy_cas_scope_unauthorized",
        ),
        (
            {},
            {"cas_authority_id": "owner:other"},
            "policy_cas_authority_mismatch",
        ),
        (
            {"backout_owner_id": "owner:backout"},
            {
                "expected_revision": 1,
                "from_mode": "shadow",
                "to_mode": "disabled",
            },
            "policy_cas_backout_owner_mismatch",
        ),
    ],
)
def test_runtime_verifier_rejects_unauthorized_cas_relationships(
    receipts: OwnerReceiptFactory,
    canary_kwargs: dict,
    cas_kwargs: dict,
    expected_error: str,
) -> None:
    canary = receipts.canary(**canary_kwargs)
    cas = receipts.cas(canary, **cas_kwargs)
    with pytest.raises(RuntimeOwnerReceiptError, match=expected_error):
        verify_owner_decision(
            cas,
            receipts.registry,
            expected_registry_sha256=receipts.registry_sha256,
            now=NOW,
        )


def test_runtime_verifier_accepts_disable_scope_for_backout_authority(
    receipts: OwnerReceiptFactory,
) -> None:
    canary = receipts.canary(backout_owner_id="owner:cas")
    cas = receipts.cas(
        canary,
        expected_revision=1,
        from_mode="shadow",
        to_mode="disabled",
    )
    verified = verify_owner_decision(
        cas,
        receipts.registry,
        expected_registry_sha256=receipts.registry_sha256,
        now=NOW,
    )
    assert verified.receipt_type == "durable_release_policy_cas"


def test_cas_persists_and_admission_reverifies_both_receipts(
    engine,
    receipts: OwnerReceiptFactory,
) -> None:
    canary = receipts.canary(workspace_id="workspace:policy:verified")
    cas = receipts.cas(canary)
    store = DurableReleasePolicyStore()
    with engine.begin() as conn:
        created = store.compare_and_swap(
            conn,
            cas_receipt=cas,
            canary_receipt=canary,
            trusted_registry=receipts.registry,
            expected_registry_sha256=receipts.registry_sha256,
            now=NOW,
        )
    assert created.revision == 1
    assert created.mode == "shadow"
    assert created.has_process_signature

    with engine.connect() as conn:
        readback = store.read_current(
            conn,
            workspace_id="workspace:policy:verified",
            workflow_kind="execution",
        )
    decision = DurableWorkflowPolicyAdapter(policy_store=store).evaluate(
        policy=readback,
        workspace_id="workspace:policy:verified",
        workflow_kind="execution",
        trusted_registry=receipts.registry,
        expected_registry_sha256=receipts.registry_sha256,
        now=NOW,
    )
    assert decision.shadow_enabled
    assert decision.candidate_attestations == (
        ("attestation:candidate", H),
    )
    assert len(decision.fixture_descriptors) == 2


def test_cas_is_contiguous_and_stale_revision_fails_closed(
    engine,
    receipts: OwnerReceiptFactory,
) -> None:
    canary = receipts.canary(workspace_id="workspace:policy:contiguous")
    first = receipts.cas(canary)
    store = DurableReleasePolicyStore()
    with engine.begin() as conn:
        store.compare_and_swap(
            conn,
            cas_receipt=first,
            canary_receipt=canary,
            trusted_registry=receipts.registry,
            expected_registry_sha256=receipts.registry_sha256,
            now=NOW,
        )
    with pytest.raises(DurableReleasePolicyConflict) as caught:
        with engine.begin() as conn:
            store.compare_and_swap(
                conn,
                cas_receipt=first,
                canary_receipt=canary,
                trusted_registry=receipts.registry,
                expected_registry_sha256=receipts.registry_sha256,
                now=NOW,
            )
    assert caught.value.expected_revision == 0
    assert caught.value.actual_revision == 1

    enforced = receipts.cas(
        canary,
        expected_revision=1,
        from_mode="shadow",
        to_mode="enforced",
        receipt_id="receipt:cas:2",
    )
    with engine.begin() as conn:
        second = store.compare_and_swap(
            conn,
            cas_receipt=enforced,
            canary_receipt=canary,
            trusted_registry=receipts.registry,
            expected_registry_sha256=receipts.registry_sha256,
            now=NOW,
        )
    assert second.revision == 2
    assert second.supersedes_revision == 1
    assert second.mode == "enforced"


def test_partial_process_signature_columns_are_rejected(
    engine,
) -> None:
    with pytest.raises(
        Exception,
        match="ck_durable_workflow_release_policy_owner_receipt_complete",
    ):
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO durable_workflow_release_policies (
                        workspace_id, workflow_kind, revision,
                        supersedes_revision, mode, policy, policy_hash,
                        owner_receipt_id, key_id, signature, created_by,
                        created_at
                    ) VALUES (
                        'workspace:policy:partial', 'execution', 1,
                        NULL, 'shadow', '{}'::jsonb, :policy_hash,
                        'receipt:partial', 'key:partial', 'signature',
                        'owner:partial', NOW()
                    )
                    """
                ),
                {"policy_hash": H},
            )


def test_corrective_schema_is_same_table_with_bounded_receipt_evidence(
    engine,
) -> None:
    with engine.connect() as conn:
        columns = set(
            conn.execute(
                text(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'durable_workflow_release_policies'
                    """
                )
            ).scalars()
        )
        index = conn.execute(
            text(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE schemaname = 'public'
                  AND tablename = 'durable_workflow_release_policies'
                  AND indexname =
                    'uq_durable_workflow_release_policy_owner_receipt_id'
                """
            )
        ).scalar_one()
    assert {
        "owner_receipt",
        "canary_receipt",
        "owner_receipt_id",
        "owner_receipt_sha256",
        "trusted_key_registry_revision",
        "trusted_key_registry_sha256",
    }.issubset(columns)
    assert index == "uq_durable_workflow_release_policy_owner_receipt_id"


def test_admission_rejects_incomplete_legacy_policy(
    engine,
    receipts: OwnerReceiptFactory,
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO durable_workflow_release_policies (
                    workspace_id, workflow_kind, revision,
                    supersedes_revision, mode, policy, policy_hash,
                    key_id, signature, created_by, created_at
                ) VALUES (
                    'workspace:policy:legacy', 'execution', 1,
                    NULL, 'shadow', '{}'::jsonb, :policy_hash,
                    'legacy:key', 'legacy:signature', 'legacy:owner', NOW()
                )
                """
            ),
            {"policy_hash": H},
        )
    store = DurableReleasePolicyStore()
    with engine.connect() as conn:
        legacy = store.read_current(
            conn,
            workspace_id="workspace:policy:legacy",
            workflow_kind="execution",
        )
    with pytest.raises(
        DurableWorkflowAdmissionUnavailable,
        match="process_signature_missing",
    ):
        DurableWorkflowPolicyAdapter(policy_store=store).evaluate(
            policy=legacy,
            workspace_id="workspace:policy:legacy",
            workflow_kind="execution",
            trusted_registry=receipts.registry,
            expected_registry_sha256=receipts.registry_sha256,
            now=NOW,
        )
