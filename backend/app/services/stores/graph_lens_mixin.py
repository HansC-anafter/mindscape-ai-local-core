import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from app.models.graph import (
    LensNodeState,
    LensProfileNode,
    MindLensProfile,
    MindLensProfileCreate,
    WorkspaceLensOverride,
)
from app.services.stores.base import StoreValidationError
from app.services.stores.graph_projection import (
    row_data,
    row_to_lens,
    row_to_lens_profile_node,
    row_to_workspace_override,
    rows_to_workspace_override_state_map,
)


class GraphLensMixin:
    @staticmethod
    def _row_data(row) -> Dict[str, Any]:
        return row_data(row)

    def create_lens_profile(
        self,
        lens: MindLensProfileCreate,
        profile_id: str,
    ) -> MindLensProfile:
        """Create lens profile"""
        lens_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        with self.transaction() as conn:
            if lens.is_default:
                conn.execute(
                    text(
                        """
                        UPDATE mind_lens_profiles
                        SET is_default = FALSE, updated_at = :updated_at
                        WHERE profile_id = :profile_id AND is_default = TRUE
                    """
                    ),
                    {"updated_at": now, "profile_id": profile_id},
                )

            conn.execute(
                text(
                    """
                    INSERT INTO mind_lens_profiles (id, profile_id, name, description, is_default, created_at, updated_at)
                    VALUES (:id, :profile_id, :name, :description, :is_default, :created_at, :updated_at)
                """
                ),
                {
                    "id": lens_id,
                    "profile_id": profile_id,
                    "name": lens.name,
                    "description": lens.description,
                    "is_default": lens.is_default,
                    "created_at": now,
                    "updated_at": now,
                },
            )

            if lens.active_node_ids:
                for node_id in lens.active_node_ids:
                    conn.execute(
                        text(
                            """
                            INSERT INTO lens_profile_nodes (id, preset_id, node_id, state, updated_at)
                            VALUES (:id, :preset_id, :node_id, :state, :updated_at)
                            ON CONFLICT (preset_id, node_id) DO UPDATE
                            SET state = EXCLUDED.state, updated_at = EXCLUDED.updated_at
                        """
                        ),
                        {
                            "id": str(uuid.uuid4()),
                            "preset_id": lens_id,
                            "node_id": node_id,
                            "state": LensNodeState.KEEP.value,
                            "updated_at": now,
                        },
                    )

        return self.get_lens_profile(lens_id)

    def get_lens_profile(self, lens_id: str) -> Optional[MindLensProfile]:
        """Get lens profile by ID"""
        with self.get_connection() as conn:
            result = conn.execute(
                text("SELECT * FROM mind_lens_profiles WHERE id = :lens_id"),
                {"lens_id": lens_id},
            )
            row = result.fetchone()
            if not row:
                return None

            return self._row_to_lens(row, conn)

    def list_lens_profiles(self, profile_id: str) -> List[MindLensProfile]:
        """List all lens profiles for a profile"""
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    "SELECT * FROM mind_lens_profiles WHERE profile_id = :profile_id ORDER BY created_at DESC"
                ),
                {"profile_id": profile_id},
            ).fetchall()
            return [self._row_to_lens(row, conn) for row in rows]

    def get_active_lens(
        self,
        profile_id: str,
        workspace_id: Optional[str] = None,
    ) -> Optional[MindLensProfile]:
        """
        Get active lens for profile/workspace

        Priority:
        1. Workspace-bound lens
        2. Profile default lens
        3. None (system default: all nodes active)
        """
        with self.get_connection() as conn:
            if workspace_id:
                row = conn.execute(
                    text(
                        """
                        SELECT mlp.* FROM mind_lens_profiles mlp
                        JOIN mind_lens_workspace_bindings mlwb ON mlp.id = mlwb.lens_id
                        WHERE mlwb.workspace_id = :workspace_id AND mlp.profile_id = :profile_id
                    """
                    ),
                    {"workspace_id": workspace_id, "profile_id": profile_id},
                ).fetchone()
                if row:
                    return self._row_to_lens(row, conn)

            row = conn.execute(
                text(
                    """
                    SELECT * FROM mind_lens_profiles
                    WHERE profile_id = :profile_id AND is_default = TRUE
                    LIMIT 1
                """
                ),
                {"profile_id": profile_id},
            ).fetchone()
            if row:
                return self._row_to_lens(row, conn)

        return None

    def _row_to_lens(self, row, conn) -> MindLensProfile:
        """Convert database row to MindLensProfile"""
        data = self._row_data(row)

        active_rows = conn.execute(
            text(
                """
                SELECT node_id FROM lens_profile_nodes
                WHERE preset_id = :preset_id AND state != :off_state
            """
            ),
            {"preset_id": data["id"], "off_state": LensNodeState.OFF.value},
        ).fetchall()
        active_node_ids = [r._mapping["node_id"] for r in active_rows]

        workspace_rows = conn.execute(
            text(
                "SELECT workspace_id FROM mind_lens_workspace_bindings WHERE lens_id = :lens_id"
            ),
            {"lens_id": data["id"]},
        ).fetchall()
        linked_workspace_ids = [r._mapping["workspace_id"] for r in workspace_rows]

        return row_to_lens(
            row,
            active_node_ids=active_node_ids,
            linked_workspace_ids=linked_workspace_ids,
        )

    def bind_lens_to_workspace(
        self,
        lens_id: str,
        workspace_id: str,
        profile_id: str,
    ) -> bool:
        """Bind lens to workspace (overwrites existing binding)"""
        lens = self.get_lens_profile(lens_id)
        if not lens or lens.profile_id != profile_id:
            raise StoreValidationError("Lens not found or not owned by profile")

        now = datetime.now(timezone.utc)

        with self.transaction() as conn:
            conn.execute(
                text("DELETE FROM mind_lens_workspace_bindings WHERE workspace_id = :workspace_id"),
                {"workspace_id": workspace_id},
            )

            conn.execute(
                text(
                    """
                    INSERT INTO mind_lens_workspace_bindings (lens_id, workspace_id, created_at)
                    VALUES (:lens_id, :workspace_id, :created_at)
                """
                ),
                {"lens_id": lens_id, "workspace_id": workspace_id, "created_at": now},
            )

            return True

    def unbind_lens_from_workspace(
        self,
        workspace_id: str,
        profile_id: str,
    ) -> bool:
        """Unbind lens from workspace"""
        with self.transaction() as conn:
            result = conn.execute(
                text(
                    "DELETE FROM mind_lens_workspace_bindings WHERE workspace_id = :workspace_id"
                ),
                {"workspace_id": workspace_id},
            )
            return result.rowcount > 0

    def upsert_lens_profile_node(
        self,
        preset_id: str,
        node_id: str,
        state: LensNodeState,
    ) -> LensProfileNode:
        """Create or update lens profile node state"""
        now = datetime.now(timezone.utc)

        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO lens_profile_nodes (id, preset_id, node_id, state, updated_at)
                    VALUES (:id, :preset_id, :node_id, :state, :updated_at)
                    ON CONFLICT (preset_id, node_id) DO UPDATE
                    SET state = EXCLUDED.state, updated_at = EXCLUDED.updated_at
                """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "preset_id": preset_id,
                    "node_id": node_id,
                    "state": state.value,
                    "updated_at": now,
                },
            )

            row = conn.execute(
                text(
                    "SELECT * FROM lens_profile_nodes WHERE preset_id = :preset_id AND node_id = :node_id"
                ),
                {"preset_id": preset_id, "node_id": node_id},
            ).fetchone()
            return self._row_to_lens_profile_node(row)

    def get_lens_profile_nodes(self, preset_id: str) -> List[LensProfileNode]:
        """Get all lens profile nodes for a preset"""
        with self.get_connection() as conn:
            rows = conn.execute(
                text("SELECT * FROM lens_profile_nodes WHERE preset_id = :preset_id"),
                {"preset_id": preset_id},
            ).fetchall()
            return [self._row_to_lens_profile_node(row) for row in rows]

    def get_lens_profile_node(
        self,
        preset_id: str,
        node_id: str,
    ) -> Optional[LensProfileNode]:
        """Get specific lens profile node"""
        with self.get_connection() as conn:
            row = conn.execute(
                text(
                    "SELECT * FROM lens_profile_nodes WHERE preset_id = :preset_id AND node_id = :node_id"
                ),
                {"preset_id": preset_id, "node_id": node_id},
            ).fetchone()
            if not row:
                return None
            return self._row_to_lens_profile_node(row)

    def delete_lens_profile_node(self, preset_id: str, node_id: str) -> bool:
        """Delete lens profile node"""
        with self.transaction() as conn:
            result = conn.execute(
                text(
                    "DELETE FROM lens_profile_nodes WHERE preset_id = :preset_id AND node_id = :node_id"
                ),
                {"preset_id": preset_id, "node_id": node_id},
            )
            return result.rowcount > 0

    def count_lens_profile_nodes(
        self,
        preset_id: str,
        state: Optional[LensNodeState] = None,
    ) -> int:
        """Count lens profile nodes by state"""
        query = "SELECT COUNT(*) AS count FROM lens_profile_nodes WHERE preset_id = :preset_id"
        params: Dict[str, Any] = {"preset_id": preset_id}

        if state:
            query += " AND state = :state"
            params["state"] = state.value

        with self.get_connection() as conn:
            result = conn.execute(text(query), params).fetchone()
            data = self._row_data(result)
            return int(data["count"])

    def _row_to_lens_profile_node(self, row) -> LensProfileNode:
        """Convert database row to LensProfileNode"""
        return row_to_lens_profile_node(row)

    def get_workspace_override(
        self,
        workspace_id: str,
    ) -> Optional[Dict[str, LensNodeState]]:
        """Get workspace lens overrides as dict (node_id -> state)"""
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    "SELECT node_id, state FROM workspace_lens_overrides WHERE workspace_id = :workspace_id"
                ),
                {"workspace_id": workspace_id},
            ).fetchall()
            return rows_to_workspace_override_state_map(rows)

    def get_workspace_overrides(
        self,
        workspace_id: str,
    ) -> List[WorkspaceLensOverride]:
        """Get all workspace lens overrides as list"""
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT id, workspace_id, node_id, state, updated_at
                    FROM workspace_lens_overrides WHERE workspace_id = :workspace_id
                """
                ),
                {"workspace_id": workspace_id},
            ).fetchall()
            return [self._row_to_workspace_override(row) for row in rows]

    def set_workspace_override(
        self,
        workspace_id: str,
        node_id: str,
        state: LensNodeState,
    ) -> WorkspaceLensOverride:
        """Set workspace lens override"""
        now = datetime.now(timezone.utc)

        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO workspace_lens_overrides (id, workspace_id, node_id, state, updated_at)
                    VALUES (:id, :workspace_id, :node_id, :state, :updated_at)
                    ON CONFLICT (workspace_id, node_id) DO UPDATE
                    SET state = EXCLUDED.state, updated_at = EXCLUDED.updated_at
                """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "workspace_id": workspace_id,
                    "node_id": node_id,
                    "state": state.value,
                    "updated_at": now,
                },
            )

            row = conn.execute(
                text(
                    "SELECT * FROM workspace_lens_overrides WHERE workspace_id = :workspace_id AND node_id = :node_id"
                ),
                {"workspace_id": workspace_id, "node_id": node_id},
            ).fetchone()
            return self._row_to_workspace_override(row)

    def remove_workspace_override(self, workspace_id: str, node_id: str) -> bool:
        """Remove workspace lens override"""
        with self.transaction() as conn:
            result = conn.execute(
                text(
                    "DELETE FROM workspace_lens_overrides WHERE workspace_id = :workspace_id AND node_id = :node_id"
                ),
                {"workspace_id": workspace_id, "node_id": node_id},
            )
            return result.rowcount > 0

    def _row_to_workspace_override(self, row) -> WorkspaceLensOverride:
        """Convert database row to WorkspaceLensOverride"""
        return row_to_workspace_override(row)
