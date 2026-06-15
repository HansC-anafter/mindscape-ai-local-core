"""Mapping helpers for run harness episode ledger rows."""

from __future__ import annotations

from collections import OrderedDict
from typing import Any, Dict, Iterable, Optional

from backend.app.models.run_harness import (
    RunHarnessArtifactLineageRef,
    RunHarnessAttempt,
    RunHarnessEpisode,
    RunHarnessFailure,
    RunHarnessKind,
    RunHarnessNextAction,
    RunHarnessPolicyEval,
    RunHarnessResult,
    RunHarnessScore,
    RunHarnessStatus,
    RunHarnessStepEvent,
    RunHarnessTraceRef,
    RunHarnessWaitKind,
    RunHarnessWaitState,
)


TERMINAL_STATUS_VALUES = {
    RunHarnessStatus.SUCCEEDED.value,
    RunHarnessStatus.FAILED.value,
    RunHarnessStatus.CANCELED.value,
    RunHarnessStatus.ESCALATED.value,
}


def row_mapping(row: Any) -> Dict[str, Any]:
    return dict(row._mapping if hasattr(row, "_mapping") else row)


def first_non_empty(*values: Any) -> Optional[str]:
    for value in values:
        normalized = str(value or "").strip()
        if normalized:
            return normalized
    return None


def rows_to_episode(
    episode_row: Any,
    event_rows: Iterable[Any],
) -> RunHarnessEpisode:
    episode = row_mapping(episode_row)
    policy_evals: list[RunHarnessPolicyEval] = []
    trace_refs: list[RunHarnessTraceRef] = []
    artifact_lineage: list[RunHarnessArtifactLineageRef] = []
    attempts: "OrderedDict[str, RunHarnessAttempt]" = OrderedDict()
    for raw_event in event_rows:
        event = row_mapping(raw_event)
        policy_evals.extend(policy_evals_from_payload(event.get("policy_eval")))
        trace_refs.extend(trace_refs_from_payload(event.get("trace_refs")))
        artifact_lineage.extend(
            artifact_lineage_from_payload(event.get("artifact_lineage"))
        )
        attempt_id = first_non_empty(
            event.get("attempt_id"),
            f"run-harness-attempt:{episode['episode_id']}:1",
        )
        attempt_number = int(event.get("attempt_number") or 1)
        step_event = RunHarnessStepEvent(
            event_id=event["event_id"],
            event_type=event["event_type"],
            status=RunHarnessStatus(event["status"]),
            payload_ref=event.get("payload_ref"),
            occurred_at=event["created_at"],
        )
        if attempt_id not in attempts:
            attempts[attempt_id] = RunHarnessAttempt(
                attempt_id=attempt_id,
                attempt_number=attempt_number,
                status=RunHarnessStatus(event["status"]),
                step_events=[],
                started_at=event["created_at"],
                completed_at=(
                    event["created_at"]
                    if event["status"] in TERMINAL_STATUS_VALUES
                    else None
                ),
            )
        attempt = attempts[attempt_id]
        attempt.step_events.append(step_event)
        attempt.status = RunHarnessStatus(event["status"])
        if event["status"] in TERMINAL_STATUS_VALUES:
            attempt.completed_at = event["created_at"]

    return RunHarnessEpisode(
        episode_id=episode["episode_id"],
        intent_envelope_ref=episode["intent_envelope_ref"],
        selection_ref=episode["selection_ref"],
        status=RunHarnessStatus(episode["status"]),
        attempts=list(attempts.values()),
        policy_evals=policy_evals,
        trace_refs=trace_refs,
        artifact_lineage=artifact_lineage,
        created_at=episode["created_at"],
        updated_at=episode["updated_at"],
    )


def row_to_result(row: Any) -> RunHarnessResult:
    result = row_mapping(row)
    failure = None
    if result.get("failure_code") or result.get("failure_message"):
        failure = RunHarnessFailure(
            code=result.get("failure_code") or "run_harness_failed",
            message=result.get("failure_message") or "Run harness execution failed.",
            details=result.get("failure_details") or {},
        )
    wait_state_payload = result.get("wait_state")
    score_payload = result.get("score")
    next_action_payload = result.get("next_action")
    return RunHarnessResult(
        run_id=result["run_id"],
        episode_id=result["episode_id"],
        harness_kind=RunHarnessKind(result["harness_kind"]),
        status=RunHarnessStatus(result["status"]),
        output_artifact_refs=list(result.get("output_artifact_refs") or []),
        failure=failure,
        score=RunHarnessScore(**score_payload) if score_payload else None,
        next_action=(
            RunHarnessNextAction(**next_action_payload)
            if next_action_payload
            else None
        ),
        wait_state=RunHarnessWaitState(**wait_state_payload)
        if wait_state_payload
        else None,
        trace_refs=trace_refs_from_payload(result.get("trace_refs")),
        metadata=result.get("result_metadata") or {},
    )


def pending_result_from_episode(episode_row: Any) -> RunHarnessResult:
    episode = row_mapping(episode_row)
    status = RunHarnessStatus(episode["status"])
    return RunHarnessResult(
        run_id=episode["run_id"],
        episode_id=episode["episode_id"],
        harness_kind=RunHarnessKind(episode["harness_kind"]),
        status=status,
        wait_state=(
            RunHarnessWaitState(
                kind=RunHarnessWaitKind.RESOURCE,
                reason="Run harness episode is waiting without a result snapshot.",
            )
            if status == RunHarnessStatus.WAITING
            else None
        ),
        metadata={"source": "episode_without_result"},
    )


def policy_evals_from_payload(payload: Any) -> list[RunHarnessPolicyEval]:
    if not payload:
        return []
    items = payload if isinstance(payload, list) else [payload]
    return [
        RunHarnessPolicyEval(**item)
        for item in items
        if isinstance(item, dict) and item.get("policy_ref")
    ]


def trace_refs_from_payload(payload: Any) -> list[RunHarnessTraceRef]:
    if not payload:
        return []
    items = payload if isinstance(payload, list) else [payload]
    return [
        RunHarnessTraceRef(**item)
        for item in items
        if isinstance(item, dict) and item.get("trace_id")
    ]


def artifact_lineage_from_payload(
    payload: Any,
) -> list[RunHarnessArtifactLineageRef]:
    if not payload:
        return []
    items = payload if isinstance(payload, list) else [payload]
    return [
        RunHarnessArtifactLineageRef(**item)
        for item in items
        if isinstance(item, dict) and item.get("artifact_ref")
    ]
