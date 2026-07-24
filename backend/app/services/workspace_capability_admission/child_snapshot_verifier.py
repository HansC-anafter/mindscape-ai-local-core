"""Child-only admission verification; never re-queries governance sources."""

from __future__ import annotations

from typing import Any

from .contracts import ExecutionAdmissionSnapshot
from .execution_snapshot import verify_execution_snapshot_hash


def verify_child_snapshot(
    payload: dict[str, Any] | ExecutionAdmissionSnapshot,
    *,
    expected_workspace_id: str,
    expected_root_execution_id: str,
) -> ExecutionAdmissionSnapshot:
    snapshot = (
        payload
        if isinstance(payload, ExecutionAdmissionSnapshot)
        else ExecutionAdmissionSnapshot.model_validate(payload)
    )
    verify_execution_snapshot_hash(snapshot)
    if snapshot.workspace_id != expected_workspace_id:
        raise ValueError("child_snapshot_workspace_mismatch")
    if snapshot.root_execution_id != expected_root_execution_id:
        raise ValueError("child_snapshot_root_execution_mismatch")
    return snapshot
