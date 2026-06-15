from datetime import datetime, timezone

from backend.app.models.run_harness import RunHarnessStatus
from backend.app.services.stores.postgres.run_harness_episode_ledger_store import (
    PostgresRunHarnessEpisodeLedgerStore,
)


def test_store_rebuilds_episode_attempts_and_refs_from_event_rows() -> None:
    now = datetime.now(timezone.utc)
    episode = PostgresRunHarnessEpisodeLedgerStore._rows_to_episode(
        {
            "episode_id": "episode-1",
            "run_id": "run-1",
            "intent_envelope_ref": "intent-1",
            "selection_ref": "selection-1",
            "harness_kind": "deterministic_tool",
            "status": "succeeded",
            "workspace_id": "ws",
            "created_at": now,
            "updated_at": now,
        },
        [
            {
                "event_id": "event-1",
                "event_type": "tool.started",
                "status": "running",
                "payload_ref": "artifact:event-1",
                "attempt_id": "attempt-1",
                "attempt_number": 1,
                "policy_eval": {
                    "policy_ref": "policy-1",
                    "decision": "allow",
                    "reason_codes": ["readonly"],
                    "evaluated_at": now,
                },
                "trace_refs": [{"trace_id": "trace-1", "node_ids": ["tool"]}],
                "artifact_lineage": [
                    {"artifact_ref": "artifact:out", "relation": "produced"}
                ],
                "created_at": now,
            },
            {
                "event_id": "event-2",
                "event_type": "tool.completed",
                "status": "succeeded",
                "payload_ref": "artifact:event-2",
                "attempt_id": "attempt-1",
                "attempt_number": 1,
                "policy_eval": {},
                "trace_refs": [],
                "artifact_lineage": [],
                "created_at": now,
            },
        ],
    )

    assert episode.status == RunHarnessStatus.SUCCEEDED
    assert episode.attempts[0].attempt_id == "attempt-1"
    assert episode.attempts[0].status == RunHarnessStatus.SUCCEEDED
    assert [event.event_id for event in episode.attempts[0].step_events] == [
        "event-1",
        "event-2",
    ]
    assert episode.policy_evals[0].policy_ref == "policy-1"
    assert episode.trace_refs[0].trace_id == "trace-1"
    assert episode.artifact_lineage[0].artifact_ref == "artifact:out"


def test_store_rebuilds_result_snapshot_contract() -> None:
    result = PostgresRunHarnessEpisodeLedgerStore._row_to_result(
        {
            "episode_id": "episode-1",
            "run_id": "run-1",
            "harness_kind": "deterministic_tool",
            "status": "failed",
            "failure_code": "tool_failed",
            "failure_message": "Tool failed.",
            "failure_details": {"stderr_ref": "artifact:stderr"},
            "wait_state": None,
            "score": {"score": 0.2, "rubric": "runtime", "reason_codes": ["error"]},
            "next_action": {
                "disposition": "fail_closed",
                "reason": "Tool returned failure.",
            },
            "trace_refs": [{"trace_id": "trace-1", "node_ids": []}],
            "output_artifact_refs": ["artifact:out"],
            "result_metadata": {"source": "unit"},
        }
    )

    assert result.status == RunHarnessStatus.FAILED
    assert result.failure is not None
    assert result.failure.details["stderr_ref"] == "artifact:stderr"
    assert result.score is not None
    assert result.next_action is not None
    assert result.output_artifact_refs == ["artifact:out"]
    assert result.trace_refs[0].trace_id == "trace-1"


def test_store_synthesizes_wait_state_for_waiting_episode_without_result() -> None:
    result = PostgresRunHarnessEpisodeLedgerStore._pending_result_from_episode(
        {
            "episode_id": "episode-1",
            "run_id": "run-1",
            "harness_kind": "durable_workflow",
            "status": "waiting",
        }
    )

    assert result.status == RunHarnessStatus.WAITING
    assert result.wait_state is not None
    assert result.metadata["source"] == "episode_without_result"
