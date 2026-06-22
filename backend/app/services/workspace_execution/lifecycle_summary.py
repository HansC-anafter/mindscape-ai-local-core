"""Read-only lifecycle summaries for workspace execution payloads."""

from __future__ import annotations

from typing import Any, Mapping


TERMINAL_STATUSES = frozenset(
    {
        "succeeded",
        "completed",
        "done",
        "failed",
        "cancelled",
        "cancelled_by_user",
        "expired",
    }
)
NEEDS_ATTENTION_STATUSES = frozenset({"failed", "cancelled", "cancelled_by_user", "expired"})
WAITING_STATUSES = frozenset({"pending", "queued", "ready", "paused"})


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalized_status(value: Any) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "").strip().lower()


def _phase_for(status: str, frontier_state: str | None, blocked_reason: str | None) -> str:
    if status in NEEDS_ATTENTION_STATUSES:
        return "needs_attention"
    if status in TERMINAL_STATUSES:
        return "completed"
    if blocked_reason:
        return "waiting"
    if status == "running" or frontier_state == "running":
        return "running"
    if status in WAITING_STATUSES or frontier_state in {"ready", "queued"}:
        return "waiting"
    return "unknown"


def _label_for(phase: str) -> str:
    labels = {
        "running": "In progress",
        "waiting": "Waiting for execution",
        "completed": "Output available",
        "needs_attention": "Needs attention",
        "unknown": "State pending",
    }
    return labels.get(phase, labels["unknown"])


def _next_step_for(
    *,
    phase: str,
    blocked_reason: str | None,
    artifact_id: str | None,
    runner_id: str | None,
) -> str:
    if phase == "needs_attention":
        return "Review the failure evidence and decide whether to retry or cancel."
    if phase == "completed":
        return (
            "Open the produced artifact or evidence."
            if artifact_id
            else "Review the completed execution evidence."
        )
    if blocked_reason:
        return f"Waiting for blocker to clear: {blocked_reason}."
    if phase == "running":
        return (
            f"Runtime {runner_id} is reporting progress."
            if runner_id
            else "Runtime is working on this execution."
        )
    return "Waiting for a runtime to claim the work."


def build_lifecycle_summary(
    payload: Mapping[str, Any],
    *,
    source: str,
) -> dict[str, Any]:
    """Build a compact human-oriented summary from an existing read payload."""

    execution_context = _as_mapping(payload.get("execution_context"))
    status = _normalized_status(payload.get("status") or payload.get("task_status"))
    blocked_reason = _text(payload.get("blocked_reason"))
    frontier_state = _text(payload.get("frontier_state"))
    queue_shard = _text(payload.get("queue_shard"))
    runner_id = _text(payload.get("runner_id") or execution_context.get("runner_id"))
    artifact_id = _text(payload.get("artifact_id"))
    phase = _phase_for(status, frontier_state, blocked_reason)
    owner_id = runner_id or queue_shard or "local-core"
    owner_type = "runtime" if runner_id else ("queue" if queue_shard else "local-core")

    return {
        "source": source,
        "status": status or "unknown",
        "phase": phase,
        "label": _label_for(phase),
        "terminal": status in TERMINAL_STATUSES,
        "owner": {"type": owner_type, "id": owner_id},
        "next_step": _next_step_for(
            phase=phase,
            blocked_reason=blocked_reason,
            artifact_id=artifact_id,
            runner_id=runner_id,
        ),
        "evidence": {
            key: value
            for key, value in {
                "task_id": _text(payload.get("task_id") or payload.get("id")),
                "execution_id": _text(payload.get("execution_id")),
                "queue_shard": queue_shard,
                "frontier_state": frontier_state,
                "blocked_reason": blocked_reason,
                "runner_id": runner_id,
                "artifact_id": artifact_id,
                "last_event_at": _text(payload.get("last_event_at")),
                "updated_at": _text(payload.get("updated_at")),
            }.items()
            if value is not None
        },
    }


def attach_lifecycle_summaries_to_tasks(payload: Mapping[str, Any]) -> dict[str, Any]:
    tasks = payload.get("tasks")
    if not isinstance(tasks, list):
        return dict(payload)
    enriched_tasks: list[Any] = []
    for task in tasks:
        if not isinstance(task, Mapping):
            enriched_tasks.append(task)
            continue
        task_payload = dict(task)
        task_payload["lifecycle_summary"] = build_lifecycle_summary(
            task_payload,
            source="workspace_tasks",
        )
        enriched_tasks.append(task_payload)
    return {**dict(payload), "tasks": enriched_tasks}


def attach_lifecycle_summary_to_progress_snapshot(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    snapshot = dict(payload)
    snapshot["lifecycle_summary"] = build_lifecycle_summary(
        snapshot,
        source="progress_snapshot",
    )
    return snapshot
