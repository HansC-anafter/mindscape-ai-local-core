"""Facade seam for every Workspace Group API and host caller."""

from typing import Optional, Sequence

from backend.app.services.workspace_groups.context_resolver import (
    WorkspaceGroupContextResolver,
)
from backend.app.services.workspace_groups.contracts import (
    ActiveWorkspaceGroupContext,
    WorkspaceGroupCreate,
    WorkspaceGroupTopology,
    WorkspaceGroupUpdate,
)
from backend.app.services.workspace_groups.topology_service import (
    WorkspaceGroupTopologyService,
)


class WorkspaceGroupFacade:
    def __init__(self, topology_service: Optional[WorkspaceGroupTopologyService] = None):
        self.topology_service = topology_service or WorkspaceGroupTopologyService()
        self.context_resolver = WorkspaceGroupContextResolver(self.topology_service)

    def list_groups(
        self,
        *,
        actor_user_id: str,
        allowed_group_ids: Sequence[str] = (),
        limit: int = 200,
    ) -> list[WorkspaceGroupTopology]:
        return self.topology_service.list_authorized(
            actor_user_id=actor_user_id,
            allowed_group_ids=allowed_group_ids,
            limit=limit,
        )

    def get_group(self, group_id: str, **auth) -> WorkspaceGroupTopology:
        return self.topology_service.get_authorized(group_id, **auth)

    def create_group(self, command: WorkspaceGroupCreate, **auth) -> WorkspaceGroupTopology:
        return self.topology_service.create(command, **auth)

    def update_group(
        self, group_id: str, command: WorkspaceGroupUpdate, **auth
    ) -> WorkspaceGroupTopology:
        return self.topology_service.update(group_id, command, **auth)

    def delete_group(self, group_id: str, **auth) -> bool:
        return self.topology_service.delete(group_id, **auth)

    def resolve_context(self, **context) -> Optional[ActiveWorkspaceGroupContext]:
        return self.context_resolver.resolve(**context)

    def list_for_workspace(self, workspace_id: str) -> list[WorkspaceGroupTopology]:
        return self.context_resolver.list_for_workspace(workspace_id)

    def membership_refs(self, workspace_ids: Sequence[str]):
        return self.topology_service.repository.membership_refs(workspace_ids)

    def get_explicit_topology(self, group_id: str) -> Optional[WorkspaceGroupTopology]:
        """Internal read for a caller whose scope already names one group ID."""
        return self.topology_service.repository.get(group_id)
