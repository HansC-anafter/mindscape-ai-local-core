"""Resolve an explicitly selected, authorized Workspace Group context."""

from typing import Optional, Sequence

from backend.app.services.workspace_groups.contracts import (
    ActiveWorkspaceGroupContext,
    WorkspaceGroupTopology,
)
from backend.app.services.workspace_groups.topology_service import (
    WorkspaceGroupAccessError,
    WorkspaceGroupTopologyService,
)


class WorkspaceGroupContextResolver:
    def __init__(self, topology_service: Optional[WorkspaceGroupTopologyService] = None):
        self.topology_service = topology_service or WorkspaceGroupTopologyService()

    def resolve(
        self,
        *,
        active_group_id: Optional[str],
        workspace_id: str,
        actor_user_id: str,
        allowed_group_ids: Sequence[str] = (),
    ) -> Optional[ActiveWorkspaceGroupContext]:
        if not active_group_id:
            return None
        topology = self.topology_service.get_authorized(
            active_group_id,
            actor_user_id=actor_user_id,
            allowed_group_ids=allowed_group_ids,
        )
        member = next(
            (
                candidate
                for candidate in topology.members
                if candidate.workspace_id == workspace_id
            ),
            None,
        )
        if member is None:
            raise WorkspaceGroupAccessError(
                f"workspace {workspace_id} is not in active group {active_group_id}"
            )
        return ActiveWorkspaceGroupContext(
            group_id=topology.id,
            workspace_id=workspace_id,
            role=member.role,
            revision=topology.revision,
            topology=topology,
        )

    def list_for_workspace(self, workspace_id: str) -> list[WorkspaceGroupTopology]:
        """Return every membership; callers must not choose the first as active."""
        return self.topology_service.repository.list_for_workspace(workspace_id)
