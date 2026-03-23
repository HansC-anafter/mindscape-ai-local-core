"""
Helpers for projecting task execution records into API-friendly views.
"""

from typing import Any, Dict, Iterable, Optional


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _normalize_status(value: Any) -> str:
    if hasattr(value, "value"):
        value = value.value
    return str(value or "").strip().lower()


def build_remote_execution_summary(task_payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    ctx = _as_dict(task_payload.get("execution_context"))
    remote = _as_dict(ctx.get("remote_execution"))
    if not remote:
        return None

    execution_id = task_payload.get("execution_id") or task_payload.get("id")
    result_ingress_mode = remote.get("result_ingress_mode") or ctx.get("remote_result_mode")
    replay_children = remote.get("replay_children_execution_ids")
    if not isinstance(replay_children, list):
        replay_children = []
    latest_replay_execution_id = remote.get("latest_replay_execution_id")

    return {
        "job_type": remote.get("job_type"),
        "capability_code": remote.get("capability_code"),
        "tool_name": remote.get("tool_name"),
        "workflow_step_id": remote.get("workflow_step_id") or ctx.get("workflow_step_id"),
        "result_ingress_mode": result_ingress_mode,
        "cloud_dispatch_state": remote.get("cloud_dispatch_state"),
        "cloud_execution_id": remote.get("cloud_execution_id"),
        "cloud_state": remote.get("cloud_state"),
        "target_device_id": remote.get("target_device_id"),
        "lineage_root_execution_id": remote.get("lineage_root_execution_id") or execution_id,
        "replay_of_execution_id": remote.get("replay_of_execution_id"),
        "latest_replay_execution_id": latest_replay_execution_id,
        "replay_children_execution_ids": replay_children,
        "replay_children_count": len(replay_children),
        "replay_requested_at": remote.get("replay_requested_at"),
        "is_workflow_step_child": result_ingress_mode == "workflow_step_child",
        "is_replay_attempt": bool(remote.get("replay_of_execution_id")),
        "is_superseded_by_replay": bool(
            latest_replay_execution_id and latest_replay_execution_id != execution_id
        ),
        "has_replays": bool(replay_children),
    }


def project_execution_for_api(
    task_payload: Dict[str, Any],
    *,
    queue_position: Any,
    queue_total: Any,
) -> Dict[str, Any]:
    projected = dict(task_payload)
    execution_context = _as_dict(projected.get("execution_context"))
    projected["playbook_code"] = projected.get("pack_id") or execution_context.get(
        "playbook_code"
    )
    projected["execution_id"] = projected.get("execution_id") or projected.get("id")
    projected["queue_position"] = queue_position
    projected["queue_total"] = queue_total
    projected["parent_execution_id"] = projected.get("parent_execution_id")
    projected["remote_execution_summary"] = build_remote_execution_summary(projected)
    return projected


def build_execution_group_summary(executions: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    items = list(executions)
    statuses = [_normalize_status(item.get("status", "")) for item in items]
    remote_summaries = [
        summary
        for summary in (item.get("remote_execution_summary") for item in items)
        if isinstance(summary, dict)
    ]
    return {
        "total": len(items),
        "succeeded": sum(1 for s in statuses if s in {"succeeded", "completed"}),
        "failed": sum(1 for s in statuses if s == "failed"),
        "running": sum(1 for s in statuses if s == "running"),
        "pending": sum(1 for s in statuses if s == "pending"),
        "remote_workflow_step_children": sum(
            1 for summary in remote_summaries if summary.get("is_workflow_step_child")
        ),
        "replay_attempts": sum(
            1 for summary in remote_summaries if summary.get("is_replay_attempt")
        ),
        "superseded_by_replay": sum(
            1 for summary in remote_summaries if summary.get("is_superseded_by_replay")
        ),
        "lineage_root_count": len(
            {
                summary.get("lineage_root_execution_id")
                for summary in remote_summaries
                if summary.get("lineage_root_execution_id")
            }
        ),
    }
