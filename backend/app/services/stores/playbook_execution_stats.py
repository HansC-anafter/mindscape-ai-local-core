"""Playbook execution statistics helpers."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Sequence


def build_playbook_workspace_stats(
    playbook_code: str,
    rows: Iterable[Sequence[Any]],
) -> dict[str, Any]:
    workspace_stats_map: dict[str, dict[str, Any]] = {}
    total_executions = 0

    for row in rows:
        total_executions += 1
        workspace_id = row[0]
        status = row[1]
        created_at = row[2]

        if workspace_id not in workspace_stats_map:
            workspace_stats_map[workspace_id] = {
                "workspace_id": workspace_id,
                "execution_count": 0,
                "success_count": 0,
                "failed_count": 0,
                "running_count": 0,
                "last_executed_at": None,
            }

        stats = workspace_stats_map[workspace_id]
        stats["execution_count"] += 1

        if status in ["completed", "success"]:
            stats["success_count"] += 1
        elif status in ["failed", "error"]:
            stats["failed_count"] += 1
        elif status in ["running", "pending", "initializing"]:
            stats["running_count"] += 1

        if created_at:
            created_dt = datetime.fromisoformat(created_at)
            if stats["last_executed_at"] is None:
                stats["last_executed_at"] = created_at
            else:
                existing_dt = datetime.fromisoformat(stats["last_executed_at"])
                if created_dt > existing_dt:
                    stats["last_executed_at"] = created_at

    workspace_stats = list(workspace_stats_map.values())
    workspace_stats.sort(key=lambda item: item["execution_count"], reverse=True)

    return {
        "playbook_code": playbook_code,
        "total_executions": total_executions,
        "total_workspaces": len(workspace_stats),
        "workspace_stats": workspace_stats,
    }
