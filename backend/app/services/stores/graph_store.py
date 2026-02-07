"""
Graph store for Mind-Lens Graph data persistence
Handles graph nodes, edges, and lens profiles CRUD operations
"""

import uuid
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

from sqlalchemy import text

from app.services.stores.postgres_base import PostgresStoreBase
from app.services.stores.base import StoreError, StoreNotFoundError, StoreValidationError
from ...models.graph import (
    GraphNode, GraphNodeCreate, GraphNodeUpdate, GraphNodeResponse,
    GraphEdge, GraphEdgeCreate, GraphEdgeUpdate,
    MindLensProfile, MindLensProfileCreate, MindLensProfileUpdate,
    LensProfileNode, WorkspaceLensOverride, LensNodeState,
    GraphNodeCategory, GraphNodeType, GraphRelationType
)

logger = logging.getLogger(__name__)


class GraphStore(PostgresStoreBase):
    """Store for managing graph nodes, edges, and lens profiles (Postgres)."""

    def __init__(self, db_path: Optional[str] = None, db_role: str = "core"):
        super().__init__(db_role=db_role)
        # Keep db_path for backward compatibility (no longer used)
        self.db_path = db_path

    @staticmethod
    def _row_data(row) -> Dict[str, Any]:
        return row._mapping if hasattr(row, "_mapping") else row

    # ============== Node CRUD ==============

    def create_node(self, node: GraphNodeCreate, profile_id: str) -> GraphNode:
        """Create a new graph node"""
        node_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        with self.transaction() as conn:
            query = text(
                """
                INSERT INTO graph_nodes (
                    id, profile_id, category, node_type, label, description, content,
                    icon, color, size, is_active, confidence, source_type, source_id,
                    metadata, created_at, updated_at
                ) VALUES (
                    :id, :profile_id, :category, :node_type, :label, :description, :content,
                    :icon, :color, :size, :is_active, :confidence, :source_type, :source_id,
                    :metadata, :created_at, :updated_at
                )
            """
            )
            params = {
                "id": node_id,
                "profile_id": profile_id,
                "category": node.category.value,
                "node_type": node.node_type.value,
                "label": node.label,
                "description": node.description,
                "content": node.content,
                "icon": node.icon,
                "color": node.color,
                "size": node.size,
                "is_active": node.is_active,
                "confidence": node.confidence,
                "source_type": node.source_type,
                "source_id": node.source_id,
                "metadata": self.serialize_json(node.metadata),
                "created_at": now,
                "updated_at": now,
            }
            conn.execute(query, params)

        return self.get_node(node_id)

    def get_node(self, node_id: str) -> Optional[GraphNode]:
        """Get node by ID"""
        with self.get_connection() as conn:
            result = conn.execute(
                text("SELECT * FROM graph_nodes WHERE id = :node_id"),
                {"node_id": node_id},
            )
            row = result.fetchone()
            if not row:
                return None
            return self._row_to_node(row)

    def list_nodes(
        self,
        profile_id: str,
        category: Optional[GraphNodeCategory] = None,
        node_type: Optional[GraphNodeType] = None,
        is_active: bool = True,
        limit: int = 100,
    ) -> List[GraphNode]:
        """
        List nodes with filters

        Note: is_active represents node existence (soft delete flag), not execution state.
        Execution state (OFF/KEEP/EMPHASIZE) is stored in lens_profile_nodes.state.
        """
        query = "SELECT * FROM graph_nodes WHERE profile_id = :profile_id"
        params: Dict[str, Any] = {"profile_id": profile_id, "limit": limit}

        if category:
            query += " AND category = :category"
            params["category"] = category.value

        if node_type:
            query += " AND node_type = :node_type"
            params["node_type"] = node_type.value

        if is_active is not None:
            query += " AND is_active = :is_active"
            params["is_active"] = is_active

        query += " ORDER BY created_at DESC LIMIT :limit"

        with self.get_connection() as conn:
            rows = conn.execute(text(query), params).fetchall()
            return [self._row_to_node(row) for row in rows]

    def update_node(self, node_id: str, profile_id: str, updates: GraphNodeUpdate) -> Optional[GraphNode]:
        """Update node"""
        node = self.get_node(node_id)
        if not node or node.profile_id != profile_id:
            return None

        update_fields = []
        params: Dict[str, Any] = {"node_id": node_id, "profile_id": profile_id}

        if updates.label is not None:
            update_fields.append("label = :label")
            params["label"] = updates.label

        if updates.description is not None:
            update_fields.append("description = :description")
            params["description"] = updates.description

        if updates.content is not None:
            update_fields.append("content = :content")
            params["content"] = updates.content

        if updates.icon is not None:
            update_fields.append("icon = :icon")
            params["icon"] = updates.icon

        if updates.color is not None:
            update_fields.append("color = :color")
            params["color"] = updates.color

        if updates.size is not None:
            update_fields.append("size = :size")
            params["size"] = updates.size

        if updates.is_active is not None:
            update_fields.append("is_active = :is_active")
            params["is_active"] = updates.is_active

        if updates.confidence is not None:
            update_fields.append("confidence = :confidence")
            params["confidence"] = updates.confidence

        if updates.metadata is not None:
            update_fields.append("metadata = :metadata")
            params["metadata"] = self.serialize_json(updates.metadata)

        if not update_fields:
            return node

        update_fields.append("updated_at = :updated_at")
        params["updated_at"] = datetime.now(timezone.utc)

        query = text(
            f"UPDATE graph_nodes SET {', '.join(update_fields)} WHERE id = :node_id AND profile_id = :profile_id"
        )

        with self.transaction() as conn:
            conn.execute(query, params)

        return self.get_node(node_id)

    def delete_node(self, node_id: str, profile_id: str, cascade: bool = False) -> bool:
        """Delete node"""
        node = self.get_node(node_id)
        if not node or node.profile_id != profile_id:
            return False

        with self.transaction() as conn:
            if cascade:
                conn.execute(
                    text(
                        "DELETE FROM graph_edges WHERE source_node_id = :node_id OR target_node_id = :node_id"
                    ),
                    {"node_id": node_id},
                )
            result = conn.execute(
                text("DELETE FROM graph_nodes WHERE id = :node_id AND profile_id = :profile_id"),
                {"node_id": node_id, "profile_id": profile_id},
            )
            return result.rowcount > 0

    def _row_to_node(self, row) -> GraphNode:
        """Convert database row to GraphNode"""
        data = self._row_data(row)
        return GraphNode(
            id=data["id"],
            profile_id=data["profile_id"],
            category=GraphNodeCategory(data["category"]),
            node_type=GraphNodeType(data["node_type"]),
            label=data["label"],
            description=data["description"],
            content=data["content"],
            icon=data["icon"],
            color=data["color"],
            size=data["size"],
            is_active=bool(data["is_active"]),
            confidence=data["confidence"],
            source_type=data["source_type"],
            source_id=data["source_id"],
            metadata=self.deserialize_json(data["metadata"], {}),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
        )

    # ============== Edge CRUD ==============

    def create_edge(self, edge: GraphEdgeCreate, profile_id: str) -> GraphEdge:
        """Create edge - validate source/target belong to same profile"""
        source_node = self.get_node(edge.source_node_id)
        if not source_node or source_node.profile_id != profile_id:
            raise StoreValidationError(
                f"Source node {edge.source_node_id} not found or not owned by profile"
            )

        target_node = self.get_node(edge.target_node_id)
        if not target_node or target_node.profile_id != profile_id:
            raise StoreValidationError(
                f"Target node {edge.target_node_id} not found or not owned by profile"
            )

        edge_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        with self.transaction() as conn:
            query = text(
                """
                INSERT INTO graph_edges (
                    id, profile_id, source_node_id, target_node_id, relation_type,
                    weight, label, is_active, metadata, created_at
                ) VALUES (
                    :id, :profile_id, :source_node_id, :target_node_id, :relation_type,
                    :weight, :label, :is_active, :metadata, :created_at
                )
                ON CONFLICT (profile_id, source_node_id, target_node_id, relation_type) DO NOTHING
            """
            )
            params = {
                "id": edge_id,
                "profile_id": profile_id,
                "source_node_id": edge.source_node_id,
                "target_node_id": edge.target_node_id,
                "relation_type": edge.relation_type.value,
                "weight": edge.weight,
                "label": edge.label,
                "is_active": edge.is_active,
                "metadata": self.serialize_json(edge.metadata),
                "created_at": now,
            }
            result = conn.execute(query, params)
            if result.rowcount == 0:
                raise StoreValidationError("Edge already exists")

        return self.get_edge(edge_id)

    def get_edge(self, edge_id: str) -> Optional[GraphEdge]:
        """Get edge by ID"""
        with self.get_connection() as conn:
            result = conn.execute(
                text("SELECT * FROM graph_edges WHERE id = :edge_id"),
                {"edge_id": edge_id},
            )
            row = result.fetchone()
            if not row:
                return None
            return self._row_to_edge(row)

    def list_edges(
        self,
        profile_id: str,
        source_node_id: Optional[str] = None,
        target_node_id: Optional[str] = None,
        relation_type: Optional[GraphRelationType] = None,
    ) -> List[GraphEdge]:
        """List edges with filters"""
        query = "SELECT * FROM graph_edges WHERE profile_id = :profile_id"
        params: Dict[str, Any] = {"profile_id": profile_id}

        if source_node_id:
            query += " AND source_node_id = :source_node_id"
            params["source_node_id"] = source_node_id

        if target_node_id:
            query += " AND target_node_id = :target_node_id"
            params["target_node_id"] = target_node_id

        if relation_type:
            query += " AND relation_type = :relation_type"
            params["relation_type"] = relation_type.value

        query += " ORDER BY created_at DESC"

        with self.get_connection() as conn:
            rows = conn.execute(text(query), params).fetchall()
            return [self._row_to_edge(row) for row in rows]

    def delete_edge(self, edge_id: str, profile_id: str) -> bool:
        """Delete edge"""
        with self.transaction() as conn:
            result = conn.execute(
                text("DELETE FROM graph_edges WHERE id = :edge_id AND profile_id = :profile_id"),
                {"edge_id": edge_id, "profile_id": profile_id},
            )
            return result.rowcount > 0

    def _row_to_edge(self, row) -> GraphEdge:
        """Convert database row to GraphEdge"""
        data = self._row_data(row)
        return GraphEdge(
            id=data["id"],
            profile_id=data["profile_id"],
            source_node_id=data["source_node_id"],
            target_node_id=data["target_node_id"],
            relation_type=GraphRelationType(data["relation_type"]),
            weight=data["weight"],
            label=data["label"],
            is_active=bool(data["is_active"]),
            metadata=self.deserialize_json(data["metadata"], {}),
            created_at=data["created_at"],
        )

    # ============== Lens Profile CRUD ==============

    def create_lens_profile(self, lens: MindLensProfileCreate, profile_id: str) -> MindLensProfile:
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

    def get_active_lens(self, profile_id: str, workspace_id: Optional[str] = None) -> Optional[MindLensProfile]:
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

        return MindLensProfile(
            id=data["id"],
            profile_id=data["profile_id"],
            name=data["name"],
            description=data["description"],
            is_default=bool(data["is_default"]),
            active_node_ids=active_node_ids,
            linked_workspace_ids=linked_workspace_ids,
            created_at=data["created_at"],
            updated_at=data["updated_at"],
        )

    # ============== Playbook Links ==============

    def link_node_to_playbook(
        self,
        node_id: str,
        playbook_code: str,
        profile_id: str,
        link_type: str = "applies",
    ) -> bool:
        """Link node to playbook"""
        node = self.get_node(node_id)
        if not node or node.profile_id != profile_id:
            raise StoreValidationError(
                f"Node {node_id} not found or not owned by profile"
            )

        link_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        with self.transaction() as conn:
            query = text(
                """
                INSERT INTO graph_node_playbook_links (
                    id, graph_node_id, playbook_code, link_type, created_at
                ) VALUES (:id, :graph_node_id, :playbook_code, :link_type, :created_at)
                ON CONFLICT (graph_node_id, playbook_code) DO NOTHING
            """
            )
            result = conn.execute(
                query,
                {
                    "id": link_id,
                    "graph_node_id": node_id,
                    "playbook_code": playbook_code,
                    "link_type": link_type,
                    "created_at": now,
                },
            )
            if result.rowcount == 0:
                raise StoreValidationError("Link already exists")
            return True

    def unlink_node_from_playbook(
        self,
        node_id: str,
        playbook_code: str,
        profile_id: str,
    ) -> bool:
        """Unlink node from playbook"""
        node = self.get_node(node_id)
        if not node or node.profile_id != profile_id:
            raise StoreValidationError(
                f"Node {node_id} not found or not owned by profile"
            )

        with self.transaction() as conn:
            result = conn.execute(
                text(
                    """
                    DELETE FROM graph_node_playbook_links
                    WHERE graph_node_id = :node_id AND playbook_code = :playbook_code
                """
                ),
                {"node_id": node_id, "playbook_code": playbook_code},
            )
            return result.rowcount > 0

    def get_node_linked_playbooks(self, node_id: str) -> List[str]:
        """Get all playbook codes linked to a node"""
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    "SELECT playbook_code FROM graph_node_playbook_links WHERE graph_node_id = :node_id"
                ),
                {"node_id": node_id},
            ).fetchall()
            return [r._mapping["playbook_code"] for r in rows]

    # ============== Workspace Bindings ==============

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

    # ============== Lens Profile Nodes ==============

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

    def get_lens_profile_node(self, preset_id: str, node_id: str) -> Optional[LensProfileNode]:
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

    def count_lens_profile_nodes(self, preset_id: str, state: Optional[LensNodeState] = None) -> int:
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
        data = self._row_data(row)
        return LensProfileNode(
            id=data["id"],
            preset_id=data["preset_id"],
            node_id=data["node_id"],
            state=LensNodeState(data["state"]),
            updated_at=data["updated_at"],
        )

    # ============== Workspace Lens Overrides ==============

    def get_workspace_override(self, workspace_id: str) -> Optional[Dict[str, LensNodeState]]:
        """Get workspace lens overrides as dict (node_id -> state)"""
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    "SELECT node_id, state FROM workspace_lens_overrides WHERE workspace_id = :workspace_id"
                ),
                {"workspace_id": workspace_id},
            ).fetchall()
            return (
                {r._mapping["node_id"]: LensNodeState(r._mapping["state"]) for r in rows}
                if rows
                else None
            )

    def get_workspace_overrides(self, workspace_id: str) -> List[WorkspaceLensOverride]:
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
        data = self._row_data(row)
        return WorkspaceLensOverride(
            id=data["id"],
            workspace_id=data["workspace_id"],
            node_id=data["node_id"],
            state=LensNodeState(data["state"]),
            updated_at=data["updated_at"],
        )
