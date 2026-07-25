from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from app.services.workflow.durable_state.facade import (
    DurableWorkflowConflict,
)
from app.services.workflow.durable_state.product_iteration_contract import (
    product_iteration_definition_sha256,
)
from app.services.workflow.durable_state.transitions import (
    TRANSITIONS,
    InvalidTransition,
    require_transition,
)
from durable_workflow_ledger_spec import ACTOR, H, NOW, facade, identity
from durable_workflow_product_iteration_fixtures import (
    definition,
    engine,
    enrollment,
    observation,
    open_collecting,
)


def test_definition_immutable_and_generic_transition_blocked(
    engine, facade
) -> None:
    workflow_id = "iteration:immutable"
    with engine.begin() as conn:
        draft = definition(workflow_id)
        facade.open_product_iteration(
            conn,
            identity=identity(workflow_id, "product_iteration"),
            definition=draft,
            actor=ACTOR,
            idempotency_key="define",
        )
        changed = definition(workflow_id, state="admitted")
        changed["objective"] = "A silently changed objective."
        changed["definition_sha256"] = (
            product_iteration_definition_sha256(changed)
        )
        with pytest.raises(ValueError, match="immutable"):
            facade.admit_product_iteration(
                conn,
                workflow_id=workflow_id,
                expected_sequence=1,
                definition=changed,
                actor=ACTOR,
                idempotency_key="admit:changed",
            )
        with pytest.raises(
            DurableWorkflowConflict, match="specialized facade seam"
        ):
            facade.append_transition(
                conn,
                workflow_id=workflow_id,
                expected_sequence=1,
                target_state="admitted",
                actor=ACTOR,
                idempotency_key="generic:bypass",
            )


def test_inconclusive_and_cancelled_are_terminal(
    engine, facade
) -> None:
    with engine.begin() as conn:
        inconclusive_id = "iteration:inconclusive"
        open_collecting(conn, facade, inconclusive_id)
        facade.close_product_iteration_inconclusive(
            conn,
            workflow_id=inconclusive_id,
            expected_sequence=3,
            closure={
                "reason_code": "budget_exhausted",
                "evidence_hash": H,
                "recorded_at": NOW,
            },
            actor=ACTOR,
            idempotency_key="inconclusive",
        )
        with pytest.raises(ValueError):
            facade.start_product_iteration_collection(
                conn,
                workflow_id=inconclusive_id,
                expected_sequence=4,
                actor=ACTOR,
                idempotency_key="reopen",
            )

        cancelled_id = "iteration:cancelled"
        open_collecting(conn, facade, cancelled_id)
        facade.cancel_product_iteration(
            conn,
            workflow_id=cancelled_id,
            expected_sequence=3,
            reason={"reason": "authenticated owner cancellation"},
            actor=ACTOR,
            idempotency_key="cancel",
        )
        current = facade.read_current(conn, cancelled_id)
        assert current["current_state"] == "cancelled"
        assert current["terminal"] is True


def test_supersede_requires_admitted_pinned_successor(
    engine, facade
) -> None:
    source_id = "iteration:supersede:source"
    successor_id = "iteration:supersede:successor"
    with engine.begin() as conn:
        open_collecting(conn, facade, source_id)
        successor_draft = definition(
            successor_id, parent_iteration_id=source_id
        )
        successor_admitted = definition(
            successor_id,
            state="admitted",
            parent_iteration_id=source_id,
        )
        facade.open_product_iteration(
            conn,
            identity=identity(successor_id, "product_iteration"),
            definition=successor_draft,
            actor=ACTOR,
            idempotency_key="define",
        )
        facade.admit_product_iteration(
            conn,
            workflow_id=successor_id,
            expected_sequence=1,
            definition=successor_admitted,
            actor=ACTOR,
            idempotency_key="admit",
        )
        facade.supersede_product_iteration(
            conn,
            workflow_id=source_id,
            successor_workflow_id=successor_id,
            expected_sequence=3,
            actor=ACTOR,
            idempotency_key="supersede",
        )
        source = facade.read_current(conn, source_id)
        assert source["current_state"] == "superseded"
        assert source["terminal"] is True


def test_transition_tables_accept_only_declared_edges() -> None:
    for kind, states in TRANSITIONS.items():
        all_states = set(states)
        for source, allowed in states.items():
            for target in all_states:
                if target in allowed:
                    assert require_transition(kind, source, target) == (
                        not states[target]
                    )
                else:
                    with pytest.raises(InvalidTransition):
                        require_transition(kind, source, target)


def test_concurrent_observation_advances_one_frontier(
    engine, facade
) -> None:
    workflow_id = "iteration:concurrent"
    signer = facade._signer
    with engine.begin() as conn:
        iteration = open_collecting(
            conn, facade, workflow_id, minimum=1
        )
        enrolled = enrollment(
            workflow_id, "case:1", iteration, signer
        )
        facade.accept_iteration_enrollment(
            conn,
            workflow_id=workflow_id,
            expected_sequence=3,
            enrollment=enrolled,
            actor=ACTOR,
            idempotency_key="enroll",
        )

    def write(observation_id: str) -> str:
        try:
            with engine.begin() as conn:
                facade.accept_outcome_observation(
                    conn,
                    workflow_id=workflow_id,
                    expected_sequence=4,
                    enrollment=enrolled,
                    observation=observation(
                        enrolled,
                        iteration,
                        signer,
                        observation_id=observation_id,
                    ),
                    actor=ACTOR,
                    idempotency_key=observation_id,
                )
            return "committed"
        except DurableWorkflowConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(write, ("observation:a", "observation:b"))
        )
    assert sorted(results) == ["committed", "conflict"]
    with engine.connect() as conn:
        state = facade._repository.read_projection(
            conn, workflow_id
        )["state"]
    assert state["accepted_observation_count"] == 1
