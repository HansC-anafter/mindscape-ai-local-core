from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
from sqlalchemy import text

from app.services.workflow.durable_state.canonical_json import encode
from app.services.workflow.durable_state.product_iteration_contract import (
    product_iteration_definition_sha256,
)
from app.services.workflow.durable_state.product_outcome_commands import (
    plan_iteration_fork,
    plan_re_evaluation,
)
from app.services.workflow.durable_state.product_outcome_review import (
    ProductOutcomeReviewService,
)
from app.services.workflow.durable_state.reducers import reduce_v1
from durable_workflow_ledger_spec import ACTOR, H, NOW, facade, identity
from durable_workflow_product_iteration_fixtures import (
    definition,
    enrollment,
    engine,
    evaluation,
    observation,
    open_collecting,
    signed,
)


@pytest.fixture
def review() -> ProductOutcomeReviewService:
    return ProductOutcomeReviewService(reducers={"reducer.v1": reduce_v1})


def _collect_two(conn, facade, workflow_id: str, *, attempts: int = 1):
    iteration = open_collecting(
        conn,
        facade,
        workflow_id,
        max_evaluation_attempts=attempts,
    )
    for index in (1, 2):
        enrolled = enrollment(
            workflow_id, f"case:{index}", iteration, facade._signer
        )
        expected = 2 * index + 1
        facade.accept_iteration_enrollment(
            conn,
            workflow_id=workflow_id,
            expected_sequence=expected,
            enrollment=enrolled,
            actor=ACTOR,
            idempotency_key=f"enroll:{index}",
        )
        facade.accept_outcome_observation(
            conn,
            workflow_id=workflow_id,
            expected_sequence=expected + 1,
            enrollment=enrolled,
            observation=observation(
                enrolled,
                iteration,
                facade._signer,
                observation_id=f"observation:{workflow_id}:{index}",
            ),
            actor=ACTOR,
            idempotency_key=f"observe:{index}",
        )
    facade.mark_iteration_evidence_ready(
        conn,
        workflow_id=workflow_id,
        expected_sequence=7,
        actor=ACTOR,
        idempotency_key="evidence-ready",
    )
    return iteration


def test_compact_summary_pages_and_as_of_are_upper_only(
    engine, facade, review
) -> None:
    workflow_id = "iteration:review:compact"
    with engine.begin() as conn:
        _collect_two(conn, facade, workflow_id)
        summary = review.iteration_summary(
            conn,
            workspace_id="workspace:test",
            iteration_id=workflow_id,
        )
        observation_page = review.observations_page(
            conn,
            workspace_id="workspace:test",
            iteration_id=workflow_id,
            cursor=None,
            limit=50,
        )
        snapshot = review.as_of(
            conn,
            workspace_id="workspace:test",
            iteration_id=workflow_id,
            target_sequence=8,
        )
    assert summary["state"] == "evidence_ready"
    assert summary["gate_results"] == []
    assert summary["product_release"]["state"] == "not_started"
    assert summary["review_lens"]["capability_code"] == "test_capability"
    assert summary["review_lens"]["runtime"] == "esm"
    assert summary["evidence_frontier"][
        "accepted_observation_count"
    ] == 2
    assert observation_page["next_cursor"] is None
    assert len(observation_page["observations"]) == 2
    assert all(
        "value" not in item
        for item in observation_page["observations"]
    )
    assert snapshot["state"]["current_state"] == "evidence_ready"
    assert snapshot["effect_policy"] == "read_only_no_effect"


def test_compare_fails_closed_without_a_delta(
    engine, facade, review
) -> None:
    left_id = "iteration:review:left"
    right_id = "iteration:review:right"
    with engine.begin() as conn:
        for workflow_id, cohort_hash in (
            (left_id, H),
            (right_id, "1" * 64),
        ):
            draft = definition(workflow_id)
            draft["cohort"]["definition_hash"] = cohort_hash
            draft["definition_sha256"] = (
                product_iteration_definition_sha256(draft)
            )
            admitted = deepcopy(draft)
            admitted["state"] = "admitted"
            admitted["admitted_at"] = NOW
            admitted["definition_sha256"] = (
                product_iteration_definition_sha256(admitted)
            )
            facade.open_product_iteration(
                conn,
                identity=identity(workflow_id, "product_iteration"),
                definition=draft,
                actor=ACTOR,
                idempotency_key=f"define:{workflow_id}",
            )
            facade.admit_product_iteration(
                conn,
                workflow_id=workflow_id,
                expected_sequence=1,
                definition=admitted,
                actor=ACTOR,
                idempotency_key=f"admit:{workflow_id}",
            )
        comparison = review.compare(
            conn,
            workspace_id="workspace:test",
            left={"iteration_id": left_id, "sequence": 2},
            right={"iteration_id": right_id, "sequence": 2},
        )
    assert comparison["status"] == "incomparable"
    assert comparison["delta"] is None
    assert comparison["reason_codes"] == ["cohort_definition_hash"]


def test_re_evaluation_reuses_definition_and_fork_owns_changes(
    engine, facade
) -> None:
    workflow_id = "iteration:review:reevaluate"
    with engine.begin() as conn:
        iteration = _collect_two(
            conn, facade, workflow_id, attempts=2
        )
        projection = facade._repository.read_projection(
            conn, workflow_id
        )["state"]
        first = evaluation(iteration, projection, facade._signer)
        first["evaluation_id"] = "evaluation:first"
        first["recommendation"] = "inconclusive"
        first["decision"] = "inconclusive"
        first = signed(
            facade._signer,
            {
                key: value
                for key, value in first.items()
                if key not in {"key_id", "signature"}
            },
        )
        facade.record_iteration_evaluation(
            conn,
            workflow_id=workflow_id,
            expected_sequence=8,
            evaluation=first,
            approval_request=None,
            actor=ACTOR,
            idempotency_key="evaluate:first",
        )
        projection = facade._repository.read_projection(
            conn, workflow_id
        )["state"]
        intent = plan_re_evaluation(
            iteration_state=projection,
            current_sequence=9,
            evaluation_attempt_id="evaluation-attempt:2",
            evaluator=iteration["evaluator"],
            authorized_lane="runner:existing",
        )
        changed = deepcopy(iteration["evaluator"])
        changed["version"] = "evaluator.v2"
        with pytest.raises(ValueError, match="successor iteration fork"):
            plan_re_evaluation(
                iteration_state=projection,
                current_sequence=9,
                evaluation_attempt_id="evaluation-attempt:2",
                evaluator=changed,
                authorized_lane="runner:existing",
            )
        second = evaluation(iteration, projection, facade._signer)
        second["evaluation_id"] = "evaluation:second"
        second["evaluation_attempt_id"] = "evaluation-attempt:2"
        second["recommendation"] = "inconclusive"
        second["decision"] = "inconclusive"
        second = signed(
            facade._signer,
            {
                key: value
                for key, value in second.items()
                if key not in {"key_id", "signature"}
            },
        )
        facade.record_iteration_re_evaluation(
            conn,
            workflow_id=workflow_id,
            expected_sequence=9,
            evaluation=second,
            approval_request=None,
            actor=ACTOR,
            idempotency_key="evaluate:second",
        )
        latest = facade._repository.read_projection(
            conn, workflow_id
        )["state"]
    assert intent["lower_execution_policy"] == "do_not_dispatch"
    assert intent["effect_policy"] == "no_external_effect"
    assert latest["evaluation_attempt_count"] == 2
    fork = plan_iteration_fork(
        source_state=latest,
        new_iteration_id="iteration:review:successor",
        new_revision=2,
        changes={"evaluator": changed},
        created_at=NOW,
    )
    assert fork["source_mutation_policy"] == "do_not_reopen"
    assert fork["changed_fields"] == ["evaluator"]
    assert fork["draft_definition"]["parent_iteration_id"] == workflow_id


def test_upper_read_query_uses_bounded_ledger_index(
    engine, facade, review
) -> None:
    workflow_id = "iteration:review:query"
    with engine.begin() as conn:
        _collect_two(conn, facade, workflow_id)
        conn.execute(text("SET LOCAL enable_seqscan = off"))
        plan = "\n".join(
            row[0]
            for row in conn.execute(
                text(
                    """
                    EXPLAIN (COSTS OFF)
                    SELECT sequence
                    FROM durable_workflow_events
                    WHERE workflow_id = :workflow_id
                      AND sequence > 0
                      AND event_type IN (
                        'outcome_observation_accepted',
                        'outcome_observation_rejected'
                      )
                    ORDER BY sequence
                    LIMIT 50
                    """
                ),
                {"workflow_id": workflow_id},
            )
        )
        with pytest.raises(ValueError, match="between 1 and 50"):
            review.observations_page(
                conn,
                workspace_id="workspace:test",
                iteration_id=workflow_id,
                cursor=None,
                limit=51,
            )
    assert "durable_workflow_events_keyset" in plan


def test_phase_seven_source_is_unmounted_neutral_and_bounded() -> None:
    repo = Path(__file__).resolve().parents[2]
    service_root = (
        repo / "backend/app/services/workflow/durable_state"
    )
    paths = [
        service_root / "product_outcome_review.py",
        service_root / "product_outcome_compare.py",
        service_root / "product_outcome_commands.py",
    ]
    source = "\n".join(path.read_text() for path in paths)
    workspace_router = (
        repo / "backend/app/routes/core/workspace/__init__.py"
    ).read_text()
    assert "product-iterations" not in workspace_router
    for forbidden in (
        "capabilities.ig",
        "playbook_code",
        "durable_tasks",
        "artifacts",
        "create_engine",
        "EventSource",
        "setInterval",
    ):
        assert forbidden not in source
    assert "LIMIT :limit" in source
    assert all(len(path.read_text().splitlines()) < 500 for path in paths)
