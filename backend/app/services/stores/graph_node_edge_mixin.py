import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from app.models.graph import (
    GraphEdge,
    GraphEdgeCreate,
    GraphNode,
    GraphNodeCategory,
    GraphNodeCreate,
    GraphNodeType,
    GraphNodeUpdate,
    GraphRelationType,
)
from app.services.stores.base import StoreValidationError
from app.services.stores.graph_projection import row_data, row_to_edge, row_to_node


class GraphNodeEdgeMixin:
    @staticmethod
    def _row_data(row) -> Dict[str, Any]:
        return row_data(row)

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

    def update_node(
        self,
        node_id: str,
        profile_id: str,
        updates: GraphNodeUpdate,
    ) -> Optional[GraphNode]:
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

    def delete_node(
        self,
        node_id: str,
        profile_id: str,
        cascade: bool = False,
    ) -> bool:
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
        return row_to_node(row, self.deserialize_json)

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
        return row_to_edge(row, self.deserialize_json)

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
