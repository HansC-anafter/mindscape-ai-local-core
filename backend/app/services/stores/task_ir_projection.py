"""Projection helpers for Task IR store rows."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Dict

from backend.app.models.task_ir import (
    ArtifactReference,
    ExecutionMetadata,
    PhaseIR,
    TaskIR,
)

DeserializeJson = Callable[[Any], Any]


def _optional_row_value(row: Any, key: str) -> Any:
    if hasattr(row, "keys") and key in row.keys():
        return row[key]
    if isinstance(row, dict):
        return row.get(key)
    return None


def row_to_task_ir(row: Dict[str, Any], *, deserialize_json: DeserializeJson) -> TaskIR:
    """Convert a task_irs row into a TaskIR model."""
    phases_data = deserialize_json(row["phases"])
    artifacts_data = deserialize_json(row["artifacts"])
    metadata_data = deserialize_json(row["metadata"])

    return TaskIR(
        task_id=row["task_id"],
        intent_instance_id=row["intent_instance_id"],
        workspace_id=row["workspace_id"],
        actor_id=row["actor_id"],
        workspace_group_snapshot_id=_optional_row_value(
            row, "workspace_group_snapshot_id"
        ),
        current_phase=row["current_phase"],
        status=row["status"],
        phases=[PhaseIR(**phase_data) for phase_data in phases_data],
        artifacts=[
            ArtifactReference(**artifact_data) for artifact_data in artifacts_data
        ],
        metadata=ExecutionMetadata(**metadata_data),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        last_checkpoint_at=(
            datetime.fromisoformat(row["last_checkpoint_at"])
            if row["last_checkpoint_at"]
            else None
        ),
    )


def task_ir_stats_from_row(row: Any) -> Dict[str, Any]:
    """Project aggregate stats row into the public stats shape."""
    if not row:
        return empty_task_ir_stats()
    return {
        "total_tasks": row[0],
        "completed_tasks": row[1],
        "running_tasks": row[2],
        "failed_tasks": row[3],
        "avg_duration_hours": row[4] if row[4] else 0,
    }


def empty_task_ir_stats() -> Dict[str, Any]:
    return {
        "total_tasks": 0,
        "completed_tasks": 0,
        "running_tasks": 0,
        "failed_tasks": 0,
        "avg_duration_hours": 0,
    }
