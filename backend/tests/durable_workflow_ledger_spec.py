from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import create_engine, text

from alembic_migrations.postgres import durable_workflow_v1
from app.services.workflow.durable_state.canonical_json import (
    CanonicalPayloadError,
    encode,
)
from app.services.workflow.durable_state.compatibility import (
    CompatibilityRegistry,
    IncompatibleHistory,
)
from app.services.workflow.durable_state.facade import (
    DurableWorkflowConflict,
    DurableWorkflowFacade,
)
from app.services.workflow.durable_state.signature import (
    Ed25519Signer,
    SigningKeyError,
    verify,
)

H = "0" * 64
NOW = "2026-07-26T00:00:00Z"
SIG = "ed25519:test-signature"
ACTOR = {"actor_type": "service", "actor_id": "durable-ledger-test"}


@pytest.fixture(scope="module")
def engine():
    dsn = os.environ.get("DURABLE_WORKFLOW_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("isolated PostgreSQL URL is required")
    created = create_engine(dsn, pool_size=4, max_overflow=0)
    with created.begin() as conn:
        class Op:
            @staticmethod
            def execute(statement):
                conn.exec_driver_sql(statement)

        durable_workflow_v1.upgrade(Op)
    yield created
    created.dispose()


@pytest.fixture
def facade() -> DurableWorkflowFacade:
    registry = CompatibilityRegistry(
        workflow_definitions={"workflow.v1": object()},
        reducers={"reducer.v1": lambda state, event: state},
        effect_adapters={"effects.v1": object()},
    )
    return DurableWorkflowFacade(
        signer=Ed25519Signer(Ed25519PrivateKey.generate()),
        compatibility=registry,
    )


def identity(
    workflow_id: str,
    kind: str = "execution",
    *,
    root_workflow_id: str | None = None,
    segment_number: int = 0,
    predecessor_segment_id: str | None = None,
    predecessor_terminal_hash: str | None = None,
) -> dict:
    return {
        "contract_id": "mindscape.durable-product-semantic-workflow.v1",
        "contract_version": "1.0.0",
        "workflow_id": workflow_id,
        "root_workflow_id": root_workflow_id or workflow_id,
        "segment_id": f"{workflow_id}:segment:{segment_number}",
        "segment_number": segment_number,
        "predecessor_segment_id": predecessor_segment_id,
        "predecessor_terminal_hash": predecessor_terminal_hash,
        "workflow_kind": kind,
        "workspace_id": "workspace:test",
        "execution_id": f"execution:{workflow_id}" if kind == "execution" else None,
        "psc_ids": [
            "psc.cloud.durable-product-semantic-workflow-publication.v1",
            "psc.local-core.durable-product-semantic-workflow-runtime.v1",
        ],
        "workflow_definition_version": "workflow.v1",
        "reducer_version": "reducer.v1",
        "effect_adapter_registry_version": "effects.v1",
        "runtime_build_id": "test-build",
        "replay_compatibility_class": "exact",
        "critical_durability": "sync",
    }


def side_effect_receipt(workflow_id: str) -> dict:
    return {
        "receipt_id": f"receipt:{workflow_id}",
        "workflow_id": workflow_id,
        "effect_id": "effect:1",
        "effect_type": "fixture",
        "owner": "neutral-adapter:test",
        "request_hash": H,
        "response_hash": H,
        "adapter_id": "neutral.adapter.v1",
        "adapter_version": "1",
        "status": "succeeded",
        "replay_disposition": "reuse_receipt",
        "attempt": 1,
        "recorded_at": NOW,
        "signature": SIG,
    }


def release_health_receipt(workflow_id: str) -> dict:
    measurement = {
        "definition_hash": H,
        "value": 1,
        "threshold": 1,
        "status": "pass",
    }
    return {
        "receipt_id": f"health:{workflow_id}",
        "release_workflow_id": workflow_id,
        "release_id": "release:test",
        "candidate_attestation_id": "attestation:test",
        "window": {
            "started_at": NOW,
            "ended_at": "2026-07-26T01:00:00Z",
            "cohort_hash": H,
        },
        "slo": measurement,
        "error_budget": measurement,
        "quality": measurement,
        "safety": measurement,
        "resource": measurement,
        "drift": measurement,
        "incident_refs": [],
        "decision": "healthy",
        "recorded_at": NOW,
        "signature": SIG,
    }


def test_schema_is_exactly_ten_tables_with_insert_only_triggers(engine) -> None:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name LIKE 'durable_workflow_%'
                ORDER BY table_name
                """
            )
        ).scalars().all()
        triggers = conn.execute(
            text(
                """
                SELECT event_object_table
                FROM information_schema.triggers
                WHERE trigger_schema = 'public'
                  AND trigger_name LIKE 'immutable_durable_workflow_%'
                """
            )
        ).scalars().all()
    assert set(rows) == set(durable_workflow_v1.TABLE_NAMES)
    assert len(rows) == 10
    assert set(triggers) == {
        "durable_workflow_events",
        "durable_workflow_checkpoints",
        "durable_workflow_approval_requests",
        "durable_workflow_approval_decisions",
        "durable_workflow_approval_consumptions",
        "durable_workflow_side_effect_receipts",
        "durable_workflow_integrity_anchors",
        "durable_workflow_release_policies",
    }


@pytest.mark.parametrize(
    ("kind", "first_target"),
    [
        ("execution", "running"),
        ("product_iteration", "admitted"),
        ("product_release", "observing"),
    ],
)
def test_workflow_kinds_share_one_chain(engine, facade, kind, first_target) -> None:
    workflow_id = f"kind:{kind}"
    with engine.begin() as conn:
        facade.open_workflow(conn, identity(workflow_id, kind))
        event = facade.append_transition(
            conn,
            workflow_id=workflow_id,
            expected_sequence=0,
            target_state=first_target,
            idempotency_key="first-transition",
            actor=ACTOR,
        )
        assert facade.verify_chain(conn, workflow_id) == event["event_hash"]
        current = facade.read_current(conn, workflow_id)
    assert current["current_state"] == first_target
    assert current["current_sequence"] == 1


def test_idempotent_retry_returns_original_event(engine, facade) -> None:
    workflow_id = "idempotent:execution"
    with engine.begin() as conn:
        facade.open_workflow(conn, identity(workflow_id))
        first = facade.append_transition(
            conn,
            workflow_id=workflow_id,
            expected_sequence=0,
            target_state="running",
            idempotency_key="same-operation",
            actor=ACTOR,
        )
        retry = facade.append_transition(
            conn,
            workflow_id=workflow_id,
            expected_sequence=0,
            target_state="running",
            idempotency_key="same-operation",
            actor=ACTOR,
        )
    assert retry["event_id"] == first["event_id"]


def test_typed_receipt_uses_event_chain_without_extra_table(engine, facade) -> None:
    workflow_id = "typed:execution"
    with engine.begin() as conn:
        facade.open_workflow(conn, identity(workflow_id))
        facade.append_typed_receipt(
            conn,
            workflow_id=workflow_id,
            expected_sequence=0,
            receipt_type="side_effect_receipt",
            receipt=side_effect_receipt(workflow_id),
            idempotency_key="typed-receipt",
            actor=ACTOR,
        )
        event = facade.read_events_after(conn, workflow_id, 0, 1)[0]
    assert event["payload"]["typed_receipt"]["receipt_type"] == "side_effect_receipt"


def test_release_health_uses_product_release_chain(engine, facade) -> None:
    workflow_id = "health:release"
    with engine.begin() as conn:
        facade.open_product_release(
            conn, identity(workflow_id, "product_release")
        )
        facade.append_release_health(
            conn,
            workflow_id=workflow_id,
            expected_sequence=0,
            health_receipt=release_health_receipt(workflow_id),
            idempotency_key="health-receipt",
            actor=ACTOR,
        )
    with engine.connect() as conn:
        stored = facade.read_events_after(conn, workflow_id, 0, 1)[0]
    assert (
        stored["payload"]["typed_receipt"]["receipt_type"]
        == "release_health_receipt"
    )


def test_transaction_rollback_leaves_no_partial_rows(engine, facade) -> None:
    workflow_id = "rollback:execution"
    with pytest.raises(RuntimeError, match="fault injection"):
        with engine.begin() as conn:
            facade.open_workflow(conn, identity(workflow_id))
            facade.append_transition(
                conn,
                workflow_id=workflow_id,
                expected_sequence=0,
                target_state="running",
                idempotency_key="rollback-transition",
                actor=ACTOR,
            )
            raise RuntimeError("fault injection")
    with engine.connect() as conn:
        count = conn.execute(
            text(
                """
                SELECT COUNT(*) FROM durable_workflow_instances
                WHERE workflow_id = :workflow_id
                """
            ),
            {"workflow_id": workflow_id},
        ).scalar_one()
    assert count == 0


def test_two_writers_cannot_advance_same_sequence(engine, facade) -> None:
    workflow_id = "concurrent:execution"
    with engine.begin() as conn:
        facade.open_workflow(conn, identity(workflow_id))

    def write(key: str) -> str:
        try:
            with engine.begin() as conn:
                facade.append_transition(
                    conn,
                    workflow_id=workflow_id,
                    expected_sequence=0,
                    target_state="running",
                    idempotency_key=key,
                    actor=ACTOR,
                )
            return "committed"
        except DurableWorkflowConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, ("writer-a", "writer-b")))
    assert sorted(results) == ["committed", "conflict"]


def test_rollover_links_successor_in_same_transaction(engine, facade) -> None:
    workflow_id = "rollover:execution"
    with engine.begin() as conn:
        facade.open_workflow(conn, identity(workflow_id))
        conn.execute(
            text(
                """
                UPDATE durable_workflow_instances
                SET event_count = 9999
                WHERE workflow_id = :workflow_id
                """
            ),
            {"workflow_id": workflow_id},
        )
        successor = facade.rollover_segment(
            conn,
            workflow_id=workflow_id,
            expected_sequence=0,
            successor_workflow_id="rollover:execution:1",
            idempotency_key="rollover",
            actor=ACTOR,
        )
        predecessor = facade.read_current(conn, workflow_id)
    assert predecessor["terminal"] is True
    assert successor["segment_number"] == 1
    assert successor["predecessor_terminal_hash"] == predecessor["current_event_hash"]
    assert successor["current_state"] == predecessor["current_state"]


def test_query_paths_have_expected_indexes(engine) -> None:
    with engine.connect() as conn:
        indexes = conn.execute(
            text(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE schemaname = 'public'
                  AND tablename LIKE 'durable_workflow_%'
                """
            )
        ).scalars().all()
    assert {
        "idx_durable_workflow_events_keyset",
        "idx_durable_workflow_workspace_execution",
        "idx_durable_workflow_workspace_state",
        "idx_durable_workflow_deadlines",
    }.issubset(indexes)


def test_insert_only_event_rejects_update(engine, facade) -> None:
    workflow_id = "immutable:execution"
    with engine.begin() as conn:
        facade.open_workflow(conn, identity(workflow_id))
        event = facade.append_transition(
            conn,
            workflow_id=workflow_id,
            expected_sequence=0,
            target_state="running",
            idempotency_key="immutable",
            actor=ACTOR,
        )
    with pytest.raises(Exception, match="insert-only"):
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE durable_workflow_events SET event_type = 'transition'
                    WHERE event_id = :event_id
                    """
                ),
                {"event_id": event["event_id"]},
            )


def test_canonical_json_and_signatures_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(CanonicalPayloadError):
        encode({"bad": float("nan")})
    with pytest.raises(CanonicalPayloadError):
        encode({"too_large": "x" * 16_384})

    signer = Ed25519Signer(Ed25519PrivateKey.generate())
    payload = encode({"receipt": "exact"})
    signed = signer.sign(payload)
    verify(signer.public_key(), payload, signed.value)
    with pytest.raises(SigningKeyError):
        verify(signer.public_key(), encode({"receipt": "mutated"}), signed.value)

    key_file = tmp_path / "workflow.key"
    key_file.write_bytes(b"x" * 31)
    key_file.chmod(0o600)
    os.environ["MINDSCAPE_WORKFLOW_SIGNING_KEY_FILE"] = str(key_file)
    with pytest.raises(SigningKeyError, match="32 raw bytes"):
        Ed25519Signer.from_mounted_file()


def test_missing_pinned_version_fails_closed() -> None:
    registry = CompatibilityRegistry()
    with pytest.raises(IncompatibleHistory, match="workflow_definition_version"):
        registry.require(identity("missing:versions"))


def test_source_has_no_owned_pool_or_production_caller() -> None:
    root = Path(__file__).resolve().parents[1]
    durable_root = root / "app" / "services" / "workflow" / "durable_state"
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in durable_root.glob("*.py")
    )
    assert "create_" + "engine(" not in source
    assert ".commit(" not in source

    callers = []
    for path in (root / "app").rglob("*.py"):
        if durable_root in path.parents:
            continue
        body = path.read_text(encoding="utf-8")
        if "services.workflow.durable_state" in body:
            callers.append(path)
    assert callers == []
