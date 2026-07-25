from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from alembic_migrations.postgres import durable_workflow_v1
from app.services.workflow.durable_state.reducers import reduce_v1
from app.services.workflow.durable_state.replay import (
    ReplayCompatibilityError,
    reduce_as_of,
)
from app.services.workflow.durable_state.review_service import (
    DurableWorkflowReviewService,
)
from durable_workflow_ledger_spec import ACTOR, facade, identity


@pytest.fixture(scope="module")
def engine():
    dsn = os.environ.get("DURABLE_WORKFLOW_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("isolated PostgreSQL URL is required")
    created = create_engine(dsn, pool_size=2, max_overflow=0)
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


@pytest.fixture
def review() -> DurableWorkflowReviewService:
    return DurableWorkflowReviewService(reducers={"reducer.v1": reduce_v1})


def test_summary_and_bounded_as_of_share_pinned_identity(
    engine, facade, review
) -> None:
    workflow_id = "review:execution"
    execution_id = f"execution:{workflow_id}"
    with engine.begin() as conn:
        facade.open_workflow(conn, identity(workflow_id))
        event = facade.append_transition(
            conn,
            workflow_id=workflow_id,
            expected_sequence=0,
            target_state="running",
            idempotency_key="review-start",
            actor=ACTOR,
        )
        summary = review.execution_summary(
            conn,
            workspace_id="workspace:test",
            execution_id=execution_id,
        )
        snapshot = review.as_of(
            conn,
            workspace_id="workspace:test",
            workflow_id=workflow_id,
            target_sequence=1,
        )
    assert summary["current_state"] == "running"
    assert summary["current_sequence"] == 1
    assert summary["current_event_hash"] == event["event_hash"]
    assert summary["reducer_version"] == "reducer.v1"
    assert summary["configuration_fingerprint"] == "0" * 64
    assert summary["evidence_lifecycle"] is None
    assert snapshot["state"]["current_state"] == "running"
    assert snapshot["development_attestation_id"] == "attestation:test"
    assert snapshot["effect_policy"] == "receipts_only_no_direct_effect"


def test_review_reads_are_keyset_bounded_and_workspace_scoped(
    engine, facade, review
) -> None:
    workflow_id = "review:boundary"
    with engine.begin() as conn:
        facade.open_workflow(conn, identity(workflow_id))
        facade.append_transition(
            conn,
            workflow_id=workflow_id,
            expected_sequence=0,
            target_state="running",
            idempotency_key="boundary-start",
            actor=ACTOR,
        )
        events = review.events_after(
            conn,
            workspace_id="workspace:test",
            workflow_id=workflow_id,
            cursor=0,
            limit=50,
        )
        with pytest.raises(KeyError, match="workspace"):
            review.events_after(
                conn,
                workspace_id="workspace:other",
                workflow_id=workflow_id,
                cursor=0,
                limit=50,
            )
        with pytest.raises(ValueError, match="between 1 and 50"):
            review.events_after(
                conn,
                workspace_id="workspace:test",
                workflow_id=workflow_id,
                cursor=0,
                limit=51,
            )
    assert [row["sequence"] for row in events] == [1]


def test_compare_resolves_both_refs_inside_workspace(
    engine, facade, review
) -> None:
    left_id = "review:compare:left"
    right_id = "review:compare:right"
    with engine.begin() as conn:
        for workflow_id in (left_id, right_id):
            facade.open_workflow(conn, identity(workflow_id))
            facade.append_transition(
                conn,
                workflow_id=workflow_id,
                expected_sequence=0,
                target_state="running",
                idempotency_key=f"start:{workflow_id}",
                actor=ACTOR,
            )
        comparison = review.compare_as_of(
            conn,
            workspace_id="workspace:test",
            left_workflow_id=left_id,
            left_sequence=1,
            right_workflow_id=right_id,
            right_sequence=1,
        )
        with pytest.raises(KeyError, match="workspace"):
            review.compare_as_of(
                conn,
                workspace_id="workspace:other",
                left_workflow_id=left_id,
                left_sequence=1,
                right_workflow_id=right_id,
                right_sequence=1,
            )
    assert comparison["compatible"] is True
    assert comparison["compatibility_reasons"] == []
    assert comparison["differing_fields"] == []


def test_replay_fails_closed_on_hash_or_window_gaps() -> None:
    initial = {
        "current_state": "pending",
        "cancellation_state": None,
        "last_sequence": 0,
        "last_event_hash": None,
    }
    event = {
        "sequence": 2,
        "previous_event_hash": None,
        "event_hash": "a" * 64,
        "event_type": "transition",
        "payload": {"to_state": "running"},
    }
    with pytest.raises(ReplayCompatibilityError, match="not contiguous"):
        reduce_as_of(
            initial_state=initial,
            events=[event],
            target_sequence=2,
            reducer=reduce_v1,
            reducer_version="reducer.v1",
        )


def test_phase_four_source_stays_disabled_and_resource_bounded() -> None:
    repo = Path(__file__).resolve().parents[2]
    route_leaf = (
        repo
        / "backend/app/routes/core/durable_workflows_core/read_routes.py"
    ).read_text()
    workspace_router = (
        repo / "backend/app/routes/core/workspace/__init__.py"
    ).read_text()
    governance = (
        repo
        / "web-console/src/app/workspaces/components/"
        "execution-inspector/GovernanceTab.tsx"
    ).read_text()
    frontend_root = (
        repo
        / "web-console/src/app/workspaces/components/execution-inspector/"
        "durable-workflow-review"
    )
    frontend_source = "\n".join(
        path.read_text() for path in sorted(frontend_root.glob("*.*"))
    )
    replay_source = (
        repo
        / "backend/app/services/workflow/durable_state/replay.py"
    ).read_text()

    assert "durable_workflows" not in workspace_router
    assert "durable-workflow-review" not in governance
    assert "sqlalchemy" not in route_leaf
    assert ".commit(" not in route_leaf
    assert "new EventSource" not in frontend_source
    assert "setInterval" not in frontend_source
    assert "subscribeEventStream" in frontend_source
    assert "limit=50" in frontend_source
    assert "capabilities/ig" not in frontend_source
    for forbidden in ("datetime", "random", "requests", "httpx", "open("):
        assert forbidden not in replay_source
