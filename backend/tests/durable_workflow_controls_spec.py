from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from alembic_migrations.postgres import durable_workflow_v1
from app.services.run_harness.durable_workflow_adapter import (
    DurableRunHarnessAdapter,
)
from app.services.workflow.durable_state.effect_task_adapter import (
    DurableEffectTaskAdapter,
)
from app.services.workflow.durable_state.facade import DurableWorkflowConflict
from durable_workflow_ledger_spec import (
    ACTOR,
    H,
    NOW,
    facade,
    identity,
    side_effect_receipt,
)


@pytest.fixture(scope="module")
def engine():
    dsn = os.environ.get("DURABLE_WORKFLOW_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("isolated PostgreSQL URL is required")
    created = create_engine(dsn, pool_size=4, max_overflow=0)
    with created.begin() as conn:
        schema_exists = conn.execute(
            text("SELECT to_regclass('public.durable_workflow_instances')")
        ).scalar_one()
        if schema_exists is None:
            class Op:
                @staticmethod
                def execute(statement):
                    conn.exec_driver_sql(statement)

            durable_workflow_v1.upgrade(Op)
    yield created
    created.dispose()


def test_checkpoint_is_signed_append_only_lineage(engine, facade) -> None:
    workflow_id = "checkpoint:execution"
    with engine.begin() as conn:
        facade.open_workflow(conn, identity(workflow_id))
        event = facade.append_transition(
            conn,
            workflow_id=workflow_id,
            expected_sequence=0,
            target_state="running",
            idempotency_key="checkpoint-start",
            actor=ACTOR,
        )
        receipt = facade.append_checkpoint(
            conn,
            {
                "checkpoint_id": "checkpoint:execution:1",
                "workflow_id": workflow_id,
                "segment_id": f"{workflow_id}:segment:0",
                "sequence": 1,
                "state_hash": H,
                "event_hash": event["event_hash"],
                "reducer_version": "reducer.v1",
                "effect_frontier": 0,
                "approval_frontier": 0,
                "timer_frontier": 0,
                "message_frontier": 0,
                "cancellation_frontier": 0,
                "segment_event_count": 1,
                "segment_canonical_bytes": event["canonical_bytes"],
                "committed_at": NOW,
                "critical_durability": "sync",
            },
        )
        listed = facade.list_checkpoints(conn, workflow_id)
    assert receipt["signature"]
    assert listed == [receipt]


def test_approval_quorum_sod_and_one_time_consumption(engine, facade) -> None:
    workflow_id = "approval:execution"
    request = {
        "approval_id": "approval:request:1",
        "workflow_id": workflow_id,
        "interrupt_id": "interrupt:1",
        "tool_call_id": "tool-call:1",
        "action_hash": H,
        "resume_payload_hash": H,
        "requested_by": "actor:requester",
        "quorum": 2,
        "separation_of_duties": True,
        "created_at": NOW,
        "expires_at": "2099-07-27T00:00:00Z",
    }
    with engine.begin() as conn:
        facade.open_workflow(conn, identity(workflow_id))
        facade.request_approval(conn, request)
        with pytest.raises(ValueError, match="separation"):
            facade.decide_approval(
                conn,
                approval_id=request["approval_id"],
                decision_id="decision:self",
                decided_by=request["requested_by"],
                decision="approved",
                policy_version="policy.v1",
                created_at=NOW,
            )
        facade.decide_approval(
            conn,
            approval_id=request["approval_id"],
            decision_id="decision:1",
            decided_by="actor:reviewer:1",
            decision="approved",
            policy_version="policy.v1",
            created_at=NOW,
        )
        with pytest.raises(ValueError, match="quorum"):
            facade.consume_approval(
                conn,
                approval_id=request["approval_id"],
                consumption_id="consumption:early",
                delivery_id="delivery:early",
                effect_or_transition_id="effect:early",
                created_at=NOW,
            )
        facade.decide_approval(
            conn,
            approval_id=request["approval_id"],
            decision_id="decision:2",
            decided_by="actor:reviewer:2",
            decision="approved",
            policy_version="policy.v1",
            created_at=NOW,
        )
        consumed = facade.consume_approval(
            conn,
            approval_id=request["approval_id"],
            consumption_id="consumption:1",
            delivery_id="delivery:1",
            effect_or_transition_id="effect:1",
            created_at=NOW,
        )
    assert consumed["phase"] == "consumption"
    assert consumed["consumed_effect_id"] == "effect:1"


def test_side_effect_attempts_are_immutable_and_retryable(engine, facade) -> None:
    workflow_id = "effect:execution"
    with engine.begin() as conn:
        facade.open_workflow(conn, identity(workflow_id))
        base = side_effect_receipt(workflow_id)
        base.pop("signature")
        base.update({"status": "prepared", "replay_disposition": "retry_idempotently"})
        facade.record_side_effect(conn, base)
        retry = {
            **base,
            "receipt_id": "receipt:effect:retry",
            "attempt": 2,
            "status": "succeeded",
            "response_hash": H,
            "replay_disposition": "reuse_receipt",
        }
        signed = facade.record_side_effect(conn, retry)
    assert signed["attempt"] == 2
    assert signed["signature"]


def test_terminal_receipt_is_atomic_and_identity_pinned(engine, facade) -> None:
    workflow_id = "terminal:execution"
    exact_identity = identity(workflow_id)
    with engine.begin() as conn:
        facade.open_workflow(conn, exact_identity)
        facade.append_transition(
            conn,
            workflow_id=workflow_id,
            expected_sequence=0,
            target_state="running",
            idempotency_key="terminal-start",
            actor=ACTOR,
        )
        draft = _terminal_draft(exact_identity)
        receipt = facade.append_execution_terminal(
            conn,
            workflow_id=workflow_id,
            expected_sequence=1,
            target_state="succeeded",
            receipt=draft,
            idempotency_key="terminal-complete",
            actor=ACTOR,
        )
        retry = facade.append_execution_terminal(
            conn,
            workflow_id=workflow_id,
            expected_sequence=1,
            target_state="succeeded",
            receipt=draft,
            idempotency_key="terminal-complete",
            actor=ACTOR,
        )
        current = facade.read_current(conn, workflow_id)
        events = facade.read_events_after(conn, workflow_id, 0, 10)
    assert receipt == retry
    assert receipt["terminal_sequence"] == 2
    assert receipt["terminal_event_hash"] == events[1]["event_hash"]
    assert current["terminal"] is True
    assert current["current_sequence"] == 3


def _terminal_draft(exact_identity: dict) -> dict:
    parity_fields = (
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
    return {
        "receipt_id": "terminal:receipt:1",
        **{key: exact_identity[key] for key in parity_fields},
        "terminal_state": "succeeded",
        "result_ref": {
            "uri": "object://result/1",
            "sha256": H,
            "bytes": 1,
            "schema_id": "result.v1",
        },
        "resource_summary": {"duration_ms": 1, "attempts": 1, "task_count": 1},
        "artifact_refs": [],
        "started_at": NOW,
        "completed_at": NOW,
    }


def test_direct_execution_terminal_transition_is_forbidden(engine, facade) -> None:
    workflow_id = "terminal:direct"
    with engine.begin() as conn:
        facade.open_workflow(conn, identity(workflow_id))
        facade.append_transition(
            conn,
            workflow_id=workflow_id,
            expected_sequence=0,
            target_state="running",
            idempotency_key="direct-start",
            actor=ACTOR,
        )
        with pytest.raises(DurableWorkflowConflict, match="append_execution_terminal"):
            facade.append_transition(
                conn,
                workflow_id=workflow_id,
                expected_sequence=1,
                target_state="succeeded",
                idempotency_key="direct-terminal",
                actor=ACTOR,
            )


def test_disabled_run_harness_adapter_requires_exact_attestation(engine, facade) -> None:
    adapter = DurableRunHarnessAdapter(
        facade,
        attestation_verifier=lambda _payload: {
            "attestation_id": "attestation:test",
            "sha256": H,
        },
    )
    exact_identity = identity("adapter:run-harness")
    with engine.begin() as conn:
        admitted = adapter.admit_execution(
            conn,
            identity=exact_identity,
            development_attestation={"opaque": "fixture"},
        )
    assert admitted["workflow_id"] == exact_identity["workflow_id"]

    mismatched = identity("adapter:rejected")
    mismatched["development_attestation_sha256"] = "1" * 64
    with engine.begin() as conn:
        with pytest.raises(ValueError, match="does not match attestation"):
            adapter.admit_execution(
                conn,
                identity=mismatched,
                development_attestation={"opaque": "fixture"},
            )


def test_disabled_effect_adapter_uses_same_connection_creator(engine, facade) -> None:
    workflow_id = "adapter:effect"
    seen = []

    def create_task_with_conn(conn, task):
        assert conn.in_transaction()
        seen.append(task)
        return task

    adapter = DurableEffectTaskAdapter(
        facade, create_task_with_conn=create_task_with_conn
    )
    with engine.begin() as conn:
        facade.open_workflow(conn, identity(workflow_id))
        prepared = side_effect_receipt(workflow_id)
        prepared.pop("signature")
        prepared.update(
            {"status": "prepared", "replay_disposition": "retry_idempotently"}
        )
        receipt, created = adapter.prepare(
            conn, prepared_receipt=prepared, task={"task_id": "task:1"}
        )
    assert receipt["status"] == "prepared"
    assert created == seen[0]


def test_adapters_are_source_only_and_pack_neutral() -> None:
    root = Path(__file__).resolve().parents[1] / "app" / "services"
    scheduled_task_composition_root = (
        root / "workflow" / "scheduled_task_pack_api.py"
    )
    adapter_paths = {
        root / "run_harness" / "durable_workflow_adapter.py",
        root / "playbook" / "durable_checkpoint_adapter.py",
        root / "host_runtime_sessions" / "durable_approval_adapter.py",
        root / "workflow" / "durable_state" / "effect_task_adapter.py",
        root / "workflow" / "durable_state" / "durable_control_adapter.py",
    }
    bodies = "\n".join(
        path.read_text(encoding="utf-8")
        for path in adapter_paths | {scheduled_task_composition_root}
    )
    for forbidden in ("capabilities.ig", "capabilities.yogacoach", "ig_pack"):
        assert forbidden not in bodies
    adapter_names = {path.stem for path in adapter_paths}
    live_importers = []
    for path in root.rglob("*.py"):
        if path in adapter_paths:
            continue
        body = path.read_text(encoding="utf-8")
        if any(name in body for name in adapter_names):
            live_importers.append(path)
    assert set(live_importers) == {scheduled_task_composition_root}
