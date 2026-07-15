"""Read-only compatibility adapter for computed Workspace Group projections.

All topology writes belong to ``WorkspaceGroupTopologyService``. Keeping this
adapter read-only prevents old host/pack readers from becoming a second writer.
"""

from typing import List, Optional

from backend.app.models.workspace_group import WorkspaceGroup
from backend.app.services.stores.postgres_base import PostgresStoreBase
from backend.app.services.workspace_groups.topology_repository import (
    WorkspaceGroupTopologyRepository,
)


class PostgresWorkspaceGroupStore(PostgresStoreBase):
    def __init__(self, db_role: str = "core"):
        super().__init__(db_role=db_role)
        self.repository = WorkspaceGroupTopologyRepository()

    def get(self, group_id: str) -> Optional[WorkspaceGroup]:
        topology = self.repository.get(group_id)
        return self._to_compatibility_model(topology) if topology else None

    def list_by_owner(self, owner_user_id: str, limit: int = 50) -> List[WorkspaceGroup]:
        groups = self.repository.list_authorized(
            actor_user_id=owner_user_id,
            allowed_group_ids=(),
            limit=limit,
        )
        return [self._to_compatibility_model(group) for group in groups]

    def get_by_workspace_id(self, workspace_id: str) -> Optional[WorkspaceGroup]:
        groups = self.repository.list_for_workspace(workspace_id)
        if len(groups) != 1:
            return None
        return self._to_compatibility_model(groups[0])

    @staticmethod
    def _to_compatibility_model(topology) -> WorkspaceGroup:
        return WorkspaceGroup(
            id=topology.id,
            display_name=topology.display_name,
            owner_user_id=topology.owner_user_id,
            description=topology.description,
            role_map=topology.role_map,
            metadata=topology.metadata,
            revision=topology.revision,
            created_at=topology.created_at,
            updated_at=topology.updated_at,
        )
