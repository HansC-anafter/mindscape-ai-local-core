"""Validate dispatch targets against one admission-pinned topology snapshot."""

from typing import Optional

from backend.app.services.workspace_groups.contracts import (
    WorkspaceGroupTopologySnapshot,
)


class WorkspaceGroupExecutionBoundaryError(PermissionError):
    pass


class GroupExecutionFacade:
    def __init__(
        self,
        *,
        workspace_id: str,
        snapshot: Optional[WorkspaceGroupTopologySnapshot],
    ):
        self.workspace_id = workspace_id
        self.snapshot = snapshot

    @classmethod
    def from_session(cls, session):
        metadata = getattr(session, "metadata", None) or {}
        snapshot_payload = metadata.get("workspace_group_snapshot")
        snapshot = (
            WorkspaceGroupTopologySnapshot.model_validate(snapshot_payload)
            if isinstance(snapshot_payload, dict)
            else None
        )
        return cls(workspace_id=getattr(session, "workspace_id", "") or "", snapshot=snapshot)

    @property
    def snapshot_id(self) -> Optional[str]:
        return self.snapshot.id if self.snapshot else None

    def validate_target(self, target_workspace_id: str) -> str:
        if not self.snapshot:
            if target_workspace_id != self.workspace_id:
                raise WorkspaceGroupExecutionBoundaryError(
                    "cross-workspace dispatch requires an admitted group snapshot"
                )
            return target_workspace_id
        if target_workspace_id not in self.snapshot.role_map:
            raise WorkspaceGroupExecutionBoundaryError(
                f"workspace {target_workspace_id} is outside snapshot {self.snapshot.id}"
            )
        return target_workspace_id
