from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from app.services.workflow.durable_state.experience_summary import (
    build_experience_summary,
)
from app.services.workflow.durable_state.product_iteration_contract import (
    promotion_request_hash,
)
from durable_workflow_ledger_spec import ACTOR, H, NOW, facade, identity
from durable_workflow_product_iteration_fixtures import (
    definition as _definition,
    enrollment as _enrollment,
    evaluation as _evaluation,
    engine,
    observation as _observation,
    open_collecting as _open_collecting,
    signed as _signed,
)

H1 = "1" * 64


def test_upper_chain_requires_signed_evidence_and_owner_effect(
    engine, facade
) -> None:
    workflow_id = "iteration:promotion"
    signer = facade._signer
    with engine.begin() as conn:
        definition = _open_collecting(conn, facade, workflow_id)
        first = _enrollment(workflow_id, "case:1", definition, signer)
        facade.accept_iteration_enrollment(
            conn,
            workflow_id=workflow_id,
            expected_sequence=3,
            enrollment=first,
            actor=ACTOR,
            idempotency_key="enroll:1",
        )
        facade.accept_outcome_observation(
            conn,
            workflow_id=workflow_id,
            expected_sequence=4,
            enrollment=first,
            observation=_observation(
                first,
                definition,
                signer,
                observation_id="observation:1",
            ),
            actor=ACTOR,
            idempotency_key="observe:1",
        )
        rejected = facade.accept_outcome_observation(
            conn,
            workflow_id=workflow_id,
            expected_sequence=5,
            enrollment=first,
            observation=_observation(
                first,
                definition,
                signer,
                observation_id="observation:bad",
                comparable=False,
            ),
            actor=ACTOR,
            idempotency_key="observe:bad",
        )
        assert rejected["event_type"] == "outcome_observation_rejected"
        second = _enrollment(workflow_id, "case:2", definition, signer)
        facade.accept_iteration_enrollment(
            conn,
            workflow_id=workflow_id,
            expected_sequence=6,
            enrollment=second,
            actor=ACTOR,
            idempotency_key="enroll:2",
        )
        facade.accept_outcome_observation(
            conn,
            workflow_id=workflow_id,
            expected_sequence=7,
            enrollment=second,
            observation=_observation(
                second,
                definition,
                signer,
                observation_id="observation:2",
            ),
            actor=ACTOR,
            idempotency_key="observe:2",
        )
        facade.mark_iteration_evidence_ready(
            conn,
            workflow_id=workflow_id,
            expected_sequence=8,
            actor=ACTOR,
            idempotency_key="evidence-ready",
        )
        projection = facade._repository.read_projection(
            conn, workflow_id
        )["state"]
        assert projection["accepted_observation_count"] == 2
        assert "observation:bad" not in projection[
            "accepted_observation_ids"
        ]
        evaluation = _evaluation(definition, projection, signer)
        approval_id = "approval:promotion"
        facade.record_iteration_evaluation(
            conn,
            workflow_id=workflow_id,
            expected_sequence=9,
            evaluation=evaluation,
            approval_request={
                "approval_id": approval_id,
                "workflow_id": workflow_id,
                "interrupt_id": "promotion:interrupt",
                "tool_call_id": "promotion:effect",
                "action_hash": promotion_request_hash(
                    definition, evaluation
                ),
                "resume_payload_hash": H,
                "requested_by": "actor:requester",
                "quorum": 1,
                "separation_of_duties": True,
                "created_at": NOW,
                "expires_at": "2099-07-27T00:00:00Z",
            },
            actor=ACTOR,
            idempotency_key="evaluate",
        )
        with pytest.raises(ValueError, match="requires approval"):
            facade.finalize_iteration_decision(
                conn,
                workflow_id=workflow_id,
                expected_sequence=10,
                target_state="promoted",
                release_workflow_id="release:promotion",
                actor=ACTOR,
                idempotency_key="promote:early",
            )
        facade.decide_approval(
            conn,
            approval_id=approval_id,
            decision_id="decision:promotion",
            decided_by="actor:reviewer",
            decision="approved",
            policy_version="approval-policy:test",
            created_at=NOW,
        )
        facade.consume_approval(
            conn,
            approval_id=approval_id,
            consumption_id="consumption:promotion",
            delivery_id="delivery:promotion",
            effect_or_transition_id="effect:promotion",
            created_at=NOW,
        )
        effect = facade.record_side_effect(
            conn,
            {
                "receipt_id": "receipt:promotion",
                "workflow_id": workflow_id,
                "effect_id": "effect:promotion",
                "effect_type": "product_promotion",
                "owner": definition["release_target"]["owner_id"],
                "request_hash": promotion_request_hash(
                    definition, evaluation
                ),
                "response_hash": H1,
                "adapter_id": "release-owner.adapter.v1",
                "adapter_version": "1",
                "status": "succeeded",
                "replay_disposition": "reuse_receipt",
                "attempt": 1,
                "recorded_at": NOW,
            },
        )
        facade.finalize_iteration_decision(
            conn,
            workflow_id=workflow_id,
            expected_sequence=10,
            target_state="promoted",
            approval_consumption_id="consumption:promotion",
            release_effect_receipt_id=effect["receipt_id"],
            release_workflow_id="release:promotion",
            actor=ACTOR,
            idempotency_key="promote",
        )
        current = facade.read_current(conn, workflow_id)
        assert current["current_state"] == "promoted"
        assert current["terminal"] is True
        release = facade.open_product_release_from_promotion(
            conn,
            identity=identity(
                "release:promotion", "product_release"
            ),
            source_iteration_id=workflow_id,
            release_effect_receipt_id=effect["receipt_id"],
            actor=ACTOR,
            idempotency_key="release:link",
        )
        assert release["current_state"] == "draft"


def test_experience_summary_is_rebuildable_and_non_authoritative(
    engine, facade
) -> None:
    workflow_id = "iteration:summary"
    signer = facade._signer
    with engine.begin() as conn:
        definition = _open_collecting(
            conn, facade, workflow_id, minimum=1
        )
        enrollment = _enrollment(
            workflow_id, "case:1", definition, signer
        )
        facade.accept_iteration_enrollment(
            conn,
            workflow_id=workflow_id,
            expected_sequence=3,
            enrollment=enrollment,
            actor=ACTOR,
            idempotency_key="enroll",
        )
        facade.accept_outcome_observation(
            conn,
            workflow_id=workflow_id,
            expected_sequence=4,
            enrollment=enrollment,
            observation=_observation(
                enrollment,
                definition,
                signer,
                observation_id="observation:summary",
            ),
            actor=ACTOR,
            idempotency_key="observe",
        )
        second = _enrollment(
            workflow_id, "case:2", definition, signer
        )
        facade.accept_iteration_enrollment(
            conn,
            workflow_id=workflow_id,
            expected_sequence=5,
            enrollment=second,
            actor=ACTOR,
            idempotency_key="enroll:2",
        )
        facade.accept_outcome_observation(
            conn,
            workflow_id=workflow_id,
            expected_sequence=6,
            enrollment=second,
            observation=_observation(
                second,
                definition,
                signer,
                observation_id="observation:summary:2",
            ),
            actor=ACTOR,
            idempotency_key="observe:2",
        )
        facade.mark_iteration_evidence_ready(
            conn,
            workflow_id=workflow_id,
            expected_sequence=7,
            actor=ACTOR,
            idempotency_key="ready",
        )
        projection = facade._repository.read_projection(
            conn, workflow_id
        )["state"]
        evaluation = _evaluation(definition, projection, signer)
        evaluation["recommendation"] = "inconclusive"
        evaluation["decision"] = "inconclusive"
        evaluation = _signed(
            signer,
            {
                key: value
                for key, value in evaluation.items()
                if key not in {"key_id", "signature"}
            },
        )
        facade.record_iteration_evaluation(
            conn,
            workflow_id=workflow_id,
            expected_sequence=8,
            evaluation=evaluation,
            approval_request=None,
            actor=ACTOR,
            idempotency_key="evaluate",
        )
        projection = facade._repository.read_projection(
            conn, workflow_id
        )["state"]
    claims = [
        {
            "claim_id": "claim:1",
            "kind": "strength",
            "text": "The accepted case produced valid evidence.",
            "source_observation_ids": ["observation:summary"],
            "provenance_sha256": H,
        }
    ]
    synthesizer = {
        "model_version": "summary-model.v1",
        "prompt_version": "summary-prompt.v1",
    }
    first = build_experience_summary(
        iteration_projection=projection,
        claims=claims,
        synthesizer=synthesizer,
    )
    second = build_experience_summary(
        iteration_projection=deepcopy(projection),
        claims=deepcopy(claims),
        synthesizer=deepcopy(synthesizer),
    )
    assert first == second
    assert first["authority"] == "projection_only"


def test_upper_source_has_no_pack_or_resource_pool_branch() -> None:
    root = (
        Path(__file__).resolve().parents[1]
        / "app/services/workflow/durable_state"
    )
    paths = [
        root / "product_iterations.py",
        root / "product_iteration_contract.py",
        root / "product_iteration_re_evaluation.py",
        root / "product_iteration_closure.py",
        root / "product_releases.py",
        root / "experience_summary.py",
        root / "facade_append.py",
        root / "reducers.py",
    ]
    source = "\n".join(path.read_text() for path in paths)
    for forbidden in (
        "capabilities.ig",
        "capabilities.yogacoach",
        "playbook_code",
        "create_engine",
        "Queue(",
        "EventSource",
        "setInterval",
        "pgbouncer",
    ):
        assert forbidden not in source
    assert all(len(path.read_text().splitlines()) < 500 for path in paths)
