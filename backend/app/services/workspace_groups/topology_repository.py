"""PostgreSQL primitives for Workspace Group topology.

This module owns SQL shape only. Application rules and authorization remain in
the topology service and context resolver.
"""

from typing import Any, Dict, Iterable, List, Optional, Sequence

from sqlalchemy import text

from backend.app.services.stores.postgres_base import PostgresStoreBase
from backend.app.services.workspace_groups.contracts import WorkspaceGroupTopology


_GROUP_PROJECTION = """
    SELECT
        definition.id,
        definition.display_name,
        definition.owner_user_id,
        definition.description,
        definition.metadata,
        definition.revision,
        definition.created_at,
        definition.updated_at,
        COALESCE(
            jsonb_agg(
                jsonb_build_object(
                    'workspace_id', membership.workspace_id,
                    'role', membership.role,
                    'title', workspace.title,
                    'visibility', workspace.visibility,
                    'joined_at', membership.joined_at
                ) ORDER BY membership.joined_at, membership.workspace_id
            ) FILTER (WHERE membership.workspace_id IS NOT NULL),
            '[]'::jsonb
        ) AS members
    FROM workspace_group_definitions AS definition
    LEFT JOIN workspace_group_memberships AS membership
      ON membership.group_id = definition.id
    LEFT JOIN workspaces AS workspace
      ON workspace.id = membership.workspace_id
"""


class WorkspaceGroupTopologyRepository(PostgresStoreBase):
    """Normalized topology persistence and aggregate reads."""

    def list_authorized(
        self,
        *,
        actor_user_id: str,
        allowed_group_ids: Sequence[str],
        limit: int = 200,
    ) -> List[WorkspaceGroupTopology]:
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    _GROUP_PROJECTION
                    + """
                    WHERE definition.owner_user_id = :actor_user_id
                       OR definition.id = ANY(CAST(:allowed_group_ids AS varchar[]))
                    GROUP BY definition.id
                    ORDER BY definition.updated_at DESC
                    LIMIT :limit
                    """
                ),
                {
                    "actor_user_id": actor_user_id,
                    "allowed_group_ids": list(allowed_group_ids),
                    "limit": min(max(limit, 1), 200),
                },
            ).fetchall()
        return [self._row_to_topology(row) for row in rows]

    def get(self, group_id: str) -> Optional[WorkspaceGroupTopology]:
        with self.get_connection() as conn:
            row = conn.execute(
                text(
                    _GROUP_PROJECTION
                    + """
                    WHERE definition.id = :group_id
                    GROUP BY definition.id
                    """
                ),
                {"group_id": group_id},
            ).fetchone()
        return self._row_to_topology(row) if row else None

    def list_for_workspace(self, workspace_id: str) -> List[WorkspaceGroupTopology]:
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    _GROUP_PROJECTION
                    + """
                    WHERE EXISTS (
                        SELECT 1
                        FROM workspace_group_memberships AS selected_membership
                        WHERE selected_membership.group_id = definition.id
                          AND selected_membership.workspace_id = :workspace_id
                    )
                    GROUP BY definition.id
                    ORDER BY definition.updated_at DESC
                    """
                ),
                {"workspace_id": workspace_id},
            ).fetchall()
        return [self._row_to_topology(row) for row in rows]

    def membership_refs(self, workspace_ids: Sequence[str]) -> Dict[str, List[Dict[str, Any]]]:
        """Load compact membership projections in one statement."""
        if not workspace_ids:
            return {}
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT
                        membership.workspace_id,
                        jsonb_agg(
                            jsonb_build_object(
                                'group_id', definition.id,
                                'display_name', definition.display_name,
                                'role', membership.role,
                                'revision', definition.revision
                            ) ORDER BY definition.updated_at DESC, definition.id
                        ) AS memberships
                    FROM workspace_group_memberships AS membership
                    JOIN workspace_group_definitions AS definition
                      ON definition.id = membership.group_id
                    WHERE membership.workspace_id = ANY(CAST(:workspace_ids AS varchar[]))
                    GROUP BY membership.workspace_id
                    """
                ),
                {"workspace_ids": list(workspace_ids)},
            ).fetchall()
        return {
            row.workspace_id: self.deserialize_json(row.memberships, default=[])
            for row in rows
        }

    def create_definition(
        self,
        conn: Any,
        *,
        group_id: str,
        display_name: str,
        owner_user_id: str,
        description: Optional[str],
        metadata_json: str,
    ) -> None:
        conn.execute(
            text(
                """
                INSERT INTO workspace_group_definitions
                    (id, display_name, owner_user_id, description, metadata)
                VALUES
                    (:id, :display_name, :owner_user_id, :description,
                     CAST(:metadata AS jsonb))
                """
            ),
            {
                "id": group_id,
                "display_name": display_name,
                "owner_user_id": owner_user_id,
                "description": description,
                "metadata": metadata_json,
            },
        )

    def update_definition(
        self,
        conn: Any,
        *,
        group_id: str,
        values: Dict[str, Any],
    ) -> None:
        assignments: List[str] = []
        params: Dict[str, Any] = {"group_id": group_id}
        for column in ("display_name", "description"):
            if column in values:
                assignments.append(f"{column} = :{column}")
                params[column] = values[column]
        if "metadata" in values:
            assignments.append("metadata = CAST(:metadata AS jsonb)")
            params["metadata"] = self.serialize_json(values["metadata"])
        if not assignments:
            return
        assignments.extend(["revision = revision + 1", "updated_at = NOW()"])
        conn.execute(
            text(
                "UPDATE workspace_group_definitions SET "
                + ", ".join(assignments)
                + " WHERE id = :group_id"
            ),
            params,
        )

    def replace_members(
        self,
        conn: Any,
        *,
        group_id: str,
        members: Iterable[Dict[str, str]],
    ) -> None:
        member_rows = list(members)
        workspace_ids = [member["workspace_id"] for member in member_rows]
        conn.execute(
            text(
                """
                DELETE FROM workspace_group_memberships
                WHERE group_id = :group_id
                  AND NOT (workspace_id = ANY(CAST(:workspace_ids AS varchar[])))
                """
            ),
            {"group_id": group_id, "workspace_ids": workspace_ids},
        )
        if member_rows:
            conn.execute(
                text(
                    """
                    INSERT INTO workspace_group_memberships
                        (workspace_id, group_id, role)
                    VALUES (:workspace_id, :group_id, :role)
                    ON CONFLICT (workspace_id, group_id) DO UPDATE
                    SET role = EXCLUDED.role
                    """
                ),
                [dict(member, group_id=group_id) for member in member_rows],
            )
        conn.execute(
            text(
                """
                UPDATE workspace_group_definitions
                SET revision = revision + 1, updated_at = NOW()
                WHERE id = :group_id
                """
            ),
            {"group_id": group_id},
        )

    def verify_workspaces(
        self,
        conn: Any,
        workspace_ids: Sequence[str],
    ) -> Dict[str, str]:
        if not workspace_ids:
            return {}
        rows = conn.execute(
            text(
                """
                SELECT id, owner_user_id FROM workspaces
                WHERE id = ANY(CAST(:workspace_ids AS varchar[]))
                """
            ),
            {"workspace_ids": list(workspace_ids)},
        ).fetchall()
        return {row.id: row.owner_user_id for row in rows}

    def delete_definition(self, conn: Any, group_id: str) -> bool:
        result = conn.execute(
            text("DELETE FROM workspace_group_definitions WHERE id = :group_id"),
            {"group_id": group_id},
        )
        return result.rowcount > 0

    def _row_to_topology(self, row: Any) -> WorkspaceGroupTopology:
        return WorkspaceGroupTopology.model_validate(
            {
                "id": row.id,
                "display_name": row.display_name,
                "owner_user_id": row.owner_user_id,
                "description": row.description,
                "metadata": self.deserialize_json(row.metadata, default={}),
                "revision": row.revision,
                "members": self.deserialize_json(row.members, default=[]),
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }
        )
