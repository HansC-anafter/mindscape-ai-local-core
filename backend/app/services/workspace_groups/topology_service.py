"""Single application writer for Workspace Group definitions and memberships."""

from typing import Optional, Sequence
from uuid import uuid4

from backend.app.services.workspace_groups.contracts import (
    WorkspaceGroupCreate,
    WorkspaceGroupTopology,
    WorkspaceGroupUpdate,
)
from backend.app.services.workspace_groups.topology_repository import (
    WorkspaceGroupTopologyRepository,
)


class WorkspaceGroupNotFoundError(LookupError):
    pass


class WorkspaceGroupAccessError(PermissionError):
    pass


class WorkspaceGroupTopologyService:
    """Enforce topology validation, authorization, and atomic revision changes."""

    def __init__(self, repository: Optional[WorkspaceGroupTopologyRepository] = None):
        self.repository = repository or WorkspaceGroupTopologyRepository()

    def list_authorized(
        self,
        *,
        actor_user_id: str,
        allowed_group_ids: Sequence[str] = (),
        limit: int = 200,
    ) -> list[WorkspaceGroupTopology]:
        return self.repository.list_authorized(
            actor_user_id=actor_user_id,
            allowed_group_ids=allowed_group_ids,
            limit=limit,
        )

    def get_authorized(
        self,
        group_id: str,
        *,
        actor_user_id: str,
        allowed_group_ids: Sequence[str] = (),
    ) -> WorkspaceGroupTopology:
        topology = self.repository.get(group_id)
        if topology is None:
            raise WorkspaceGroupNotFoundError(group_id)
        self._require_group_access(topology, actor_user_id, allowed_group_ids)
        return topology

    def create(
        self,
        command: WorkspaceGroupCreate,
        *,
        actor_user_id: str,
        allowed_workspace_ids: Sequence[str] = (),
    ) -> WorkspaceGroupTopology:
        group_id = command.id or f"wg_{uuid4().hex}"
        with self.repository.transaction() as conn:
            self._verify_member_access(
                conn,
                command.members,
                actor_user_id=actor_user_id,
                allowed_workspace_ids=allowed_workspace_ids,
            )
            self.repository.create_definition(
                conn,
                group_id=group_id,
                display_name=command.display_name,
                owner_user_id=actor_user_id,
                description=command.description,
                metadata_json=self.repository.serialize_json(command.metadata),
            )
            if command.members:
                self.repository.replace_members(
                    conn,
                    group_id=group_id,
                    members=[member.model_dump() for member in command.members],
                )
        topology = self.repository.get(group_id)
        if topology is None:
            raise RuntimeError("workspace group create did not persist")
        return topology

    def update(
        self,
        group_id: str,
        command: WorkspaceGroupUpdate,
        *,
        actor_user_id: str,
        allowed_group_ids: Sequence[str] = (),
        allowed_workspace_ids: Sequence[str] = (),
    ) -> WorkspaceGroupTopology:
        existing = self.get_authorized(
            group_id,
            actor_user_id=actor_user_id,
            allowed_group_ids=allowed_group_ids,
        )
        if existing.owner_user_id != actor_user_id:
            raise WorkspaceGroupAccessError("only the group owner can mutate topology")
        changes = command.model_dump(exclude_unset=True, exclude={"members"})
        with self.repository.transaction() as conn:
            if command.members is not None:
                self._verify_member_access(
                    conn,
                    command.members,
                    actor_user_id=actor_user_id,
                    allowed_workspace_ids=allowed_workspace_ids,
                )
            self.repository.update_definition(conn, group_id=group_id, values=changes)
            if command.members is not None:
                self.repository.replace_members(
                    conn,
                    group_id=group_id,
                    members=[member.model_dump() for member in command.members],
                )
        updated = self.repository.get(group_id)
        if updated is None:
            raise WorkspaceGroupNotFoundError(group_id)
        return updated

    def delete(
        self,
        group_id: str,
        *,
        actor_user_id: str,
        allowed_group_ids: Sequence[str] = (),
    ) -> bool:
        existing = self.get_authorized(
            group_id,
            actor_user_id=actor_user_id,
            allowed_group_ids=allowed_group_ids,
        )
        if existing.owner_user_id != actor_user_id:
            raise WorkspaceGroupAccessError("only the group owner can delete topology")
        with self.repository.transaction() as conn:
            return self.repository.delete_definition(conn, group_id)

    @staticmethod
    def _require_group_access(
        topology: WorkspaceGroupTopology,
        actor_user_id: str,
        allowed_group_ids: Sequence[str],
    ) -> None:
        if topology.owner_user_id != actor_user_id and topology.id not in allowed_group_ids:
            raise WorkspaceGroupAccessError(topology.id)

    def _verify_member_access(
        self,
        conn,
        members,
        *,
        actor_user_id: str,
        allowed_workspace_ids: Sequence[str],
    ) -> None:
        workspace_ids = [member.workspace_id for member in members]
        owners = self.repository.verify_workspaces(conn, workspace_ids)
        if set(owners) != set(workspace_ids):
            missing = sorted(set(workspace_ids) - set(owners))
            raise WorkspaceGroupNotFoundError(f"unknown workspaces: {missing}")
        allowed = set(allowed_workspace_ids)
        denied = [
            workspace_id
            for workspace_id, owner_user_id in owners.items()
            if owner_user_id != actor_user_id and workspace_id not in allowed
        ]
        if denied:
            raise WorkspaceGroupAccessError(f"workspace access denied: {sorted(denied)}")
