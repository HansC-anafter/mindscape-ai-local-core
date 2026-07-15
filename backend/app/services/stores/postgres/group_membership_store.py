"""Read-only membership compatibility adapter.

Topology mutation is intentionally absent; callers must use the Workspace Group
facade so definition and membership revision changes remain atomic.
"""

from typing import Any, Dict, List

from backend.app.services.workspace_groups.topology_repository import (
    WorkspaceGroupTopologyRepository,
)


class GroupMembershipStore:
    def __init__(self):
        self.repository = WorkspaceGroupTopologyRepository()

    def list_groups_for_workspace(self, workspace_id: str) -> List[Dict[str, Any]]:
        groups = self.repository.list_for_workspace(workspace_id)
        result = []
        for group in groups:
            member = next(
                item for item in group.members if item.workspace_id == workspace_id
            )
            result.append(
                {
                    "group_id": group.id,
                    "role": member.role,
                    "joined_at": member.joined_at.isoformat() if member.joined_at else None,
                    "display_name": group.display_name,
                    "owner_user_id": group.owner_user_id,
                }
            )
        return result

    def list_workspaces_in_group(self, group_id: str) -> List[Dict[str, Any]]:
        group = self.repository.get(group_id)
        if group is None:
            return []
        return [
            {
                "workspace_id": member.workspace_id,
                "role": member.role,
                "joined_at": member.joined_at.isoformat() if member.joined_at else None,
                "title": member.title,
                "visibility": member.visibility,
            }
            for member in group.members
        ]
