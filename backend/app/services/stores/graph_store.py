"""
Graph store for Mind-Lens Graph data persistence
Handles graph nodes, edges, and lens profiles CRUD operations
"""

import uuid
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from app.services.stores.base import StoreBase, StoreError, StoreNotFoundError, StoreValidationError
from ...models.graph import (
    GraphNode, GraphNodeCreate, GraphNodeUpdate, GraphNodeResponse,
    GraphEdge, GraphEdgeCreate, GraphEdgeUpdate,
    MindLensProfile, MindLensProfileCreate, MindLensProfileUpdate,
    LensProfileNode, WorkspaceLensOverride, LensNodeState,
    GraphNodeCategory, GraphNodeType, GraphRelationType
)
import logging

logger = logging.getLogger(__name__)


class GraphStore(StoreBase):
    """Store for managing graph nodes, edges, and lens profiles"""

    # ============== Node CRUD ==============

    def create_node(self, node: GraphNodeCreate, profile_id: str) -> GraphNode:
        """Create a new graph node"""
        node_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO graph_nodes (
                    id, profile_id, category, node_type, label, description, content,
                    icon, color, size, is_active, confidence, source_type, source_id,
                    metadata, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                node_id,
                profile_id,
                node.category.value,
                node.node_type.value,
                node.label,
                node.description,
                node.content,
                node.icon,
                node.color,
                node.size,
                node.is_active,
                node.confidence,
                node.source_type,
                node.source_id,
                self.serialize_json(node.metadata),
                self.to_isoformat(now),
                self.to_isoformat(now),
            ))
            conn.commit()

        return self.get_node(node_id)

    def get_node(self, node_id: str) -> Optional[GraphNode]:
        """Get node by ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM graph_nodes WHERE id = ?', (node_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_node(row)

    def list_nodes(
        self,
        profile_id: str,
        category: Optional[GraphNodeCategory] = None,
        node_type: Optional[GraphNodeType] = None,
        is_active: bool = True,
        limit: int = 100
    ) -> List[GraphNode]:
        """
        List nodes with filters

        Note: is_active represents node existence (soft delete flag), not execution state.
        Execution state (OFF/KEEP/EMPHASIZE) is stored in lens_profile_nodes.state.
        """
        query = 'SELECT * FROM graph_nodes WHERE profile_id = ?'
        params = [profile_id]

        if category:
            query += ' AND category = ?'
            params.append(category.value)

        if node_type:
            query += ' AND node_type = ?'
            params.append(node_type.value)

        if is_active is not None:
            query += ' AND is_active = ?'
            params.append(1 if is_active else 0)

        query += ' ORDER BY created_at DESC LIMIT ?'
        params.append(limit)

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [self._row_to_node(row) for row in rows]

    def update_node(self, node_id: str, profile_id: str, updates: GraphNodeUpdate) -> Optional[GraphNode]:
        """Update node"""
        node = self.get_node(node_id)
        if not node or node.profile_id != profile_id:
            return None

        update_fields = []
        params = []

        if updates.label is not None:
            update_fields.append('label = ?')
            params.append(updates.label)

        if updates.description is not None:
            update_fields.append('description = ?')
            params.append(updates.description)

        if updates.content is not None:
            update_fields.append('content = ?')
            params.append(updates.content)

        if updates.icon is not None:
            update_fields.append('icon = ?')
            params.append(updates.icon)

        if updates.color is not None:
            update_fields.append('color = ?')
            params.append(updates.color)

        if updates.size is not None:
            update_fields.append('size = ?')
            params.append(updates.size)

        if updates.is_active is not None:
            update_fields.append('is_active = ?')
            params.append(1 if updates.is_active else 0)

        if updates.confidence is not None:
            update_fields.append('confidence = ?')
            params.append(updates.confidence)

        if updates.metadata is not None:
            update_fields.append('metadata = ?')
            params.append(self.serialize_json(updates.metadata))

        if not update_fields:
            return node

        update_fields.append('updated_at = ?')
        params.append(self.to_isoformat(datetime.now(timezone.utc)))
        params.append(node_id)
        params.append(profile_id)

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f'UPDATE graph_nodes SET {", ".join(update_fields)} WHERE id = ? AND profile_id = ?',
                params
            )
            conn.commit()

        return self.get_node(node_id)

    def delete_node(self, node_id: str, profile_id: str, cascade: bool = False) -> bool:
        """Delete node"""
        node = self.get_node(node_id)
        if not node or node.profile_id != profile_id:
            return False

        with self.get_connection() as conn:
            cursor = conn.cursor()
            if cascade:
                cursor.execute('DELETE FROM graph_edges WHERE source_node_id = ? OR target_node_id = ?', (node_id, node_id))
            cursor.execute('DELETE FROM graph_nodes WHERE id = ? AND profile_id = ?', (node_id, profile_id))
            conn.commit()
            return cursor.rowcount > 0

    def _row_to_node(self, row) -> GraphNode:
        """Convert database row to GraphNode"""
        return GraphNode(
            id=row['id'],
            profile_id=row['profile_id'],
            category=GraphNodeCategory(row['category']),
            node_type=GraphNodeType(row['node_type']),
            label=row['label'],
            description=row['description'],
            content=row['content'],
            icon=row['icon'],
            color=row['color'],
            size=row['size'],
            is_active=bool(row['is_active']),
            confidence=row['confidence'],
            source_type=row['source_type'],
            source_id=row['source_id'],
            metadata=self.deserialize_json(row['metadata'], {}),
            created_at=self.from_isoformat(row['created_at']),
            updated_at=self.from_isoformat(row['updated_at']),
        )

    # ============== Edge CRUD ==============

    def create_edge(self, edge: GraphEdgeCreate, profile_id: str) -> GraphEdge:
        """Create edge - validate source/target belong to same profile"""
        source_node = self.get_node(edge.source_node_id)
        if not source_node or source_node.profile_id != profile_id:
            raise StoreValidationError(f"Source node {edge.source_node_id} not found or not owned by profile")

        target_node = self.get_node(edge.target_node_id)
        if not target_node or target_node.profile_id != profile_id:
            raise StoreValidationError(f"Target node {edge.target_node_id} not found or not owned by profile")

        edge_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    INSERT INTO graph_edges (
                        id, profile_id, source_node_id, target_node_id, relation_type,
                        weight, label, is_active, metadata, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    edge_id,
                    profile_id,
                    edge.source_node_id,
                    edge.target_node_id,
                    edge.relation_type.value,
                    edge.weight,
                    edge.label,
                    1 if edge.is_active else 0,
                    self.serialize_json(edge.metadata),
                    self.to_isoformat(now),
                ))
                conn.commit()
            except Exception as e:
                if 'UNIQUE' in str(e) or 'uq_graph_edges_no_duplicate' in str(e):
                    raise StoreValidationError("Edge already exists")
                raise

        return self.get_edge(edge_id)

    def get_edge(self, edge_id: str) -> Optional[GraphEdge]:
        """Get edge by ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM graph_edges WHERE id = ?', (edge_id,))
            row = cursor.fetchone()
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
        query = 'SELECT * FROM graph_edges WHERE profile_id = ?'
        params = [profile_id]

        if source_node_id:
            query += ' AND source_node_id = ?'
            params.append(source_node_id)

        if target_node_id:
            query += ' AND target_node_id = ?'
            params.append(target_node_id)

        if relation_type:
            query += ' AND relation_type = ?'
            params.append(relation_type.value)

        query += ' ORDER BY created_at DESC'

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [self._row_to_edge(row) for row in rows]

    def delete_edge(self, edge_id: str, profile_id: str) -> bool:
        """Delete edge"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM graph_edges WHERE id = ? AND profile_id = ?', (edge_id, profile_id))
            conn.commit()
            return cursor.rowcount > 0

    def _row_to_edge(self, row) -> GraphEdge:
        """Convert database row to GraphEdge"""
        return GraphEdge(
            id=row['id'],
            profile_id=row['profile_id'],
            source_node_id=row['source_node_id'],
            target_node_id=row['target_node_id'],
            relation_type=GraphRelationType(row['relation_type']),
            weight=row['weight'],
            label=row['label'],
            is_active=bool(row['is_active']),
            metadata=self.deserialize_json(row['metadata'], {}),
            created_at=self.from_isoformat(row['created_at']),
        )

    # ============== Lens Profile CRUD ==============

    def create_lens_profile(self, lens: MindLensProfileCreate, profile_id: str) -> MindLensProfile:
        """Create lens profile"""
        lens_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        with self.transaction() as conn:
            cursor = conn.cursor()

            if lens.is_default:
                cursor.execute('''
                    UPDATE mind_lens_profiles
                    SET is_default = 0, updated_at = ?
                    WHERE profile_id = ? AND is_default = 1
                ''', (self.to_isoformat(now), profile_id))

            cursor.execute('''
                INSERT INTO mind_lens_profiles (id, profile_id, name, description, is_default, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                lens_id,
                profile_id,
                lens.name,
                lens.description,
                1 if lens.is_default else 0,
                self.to_isoformat(now),
                self.to_isoformat(now),
            ))

            if lens.active_node_ids:
                for node_id in lens.active_node_ids:
                    cursor.execute('''
                        INSERT OR REPLACE INTO lens_profile_nodes (id, preset_id, node_id, state, updated_at)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (
                        str(uuid.uuid4()),
                        lens_id,
                        node_id,
                        LensNodeState.KEEP.value,
                        self.to_isoformat(now)
                    ))

            conn.commit()

        return self.get_lens_profile(lens_id)

    def get_lens_profile(self, lens_id: str) -> Optional[MindLensProfile]:
        """Get lens profile by ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM mind_lens_profiles WHERE id = ?', (lens_id,))
            row = cursor.fetchone()
            if not row:
                return None

            lens = self._row_to_lens(row, conn)
            return lens

    def list_lens_profiles(self, profile_id: str) -> List[MindLensProfile]:
        """List all lens profiles for a profile"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM mind_lens_profiles WHERE profile_id = ? ORDER BY created_at DESC', (profile_id,))
            rows = cursor.fetchall()
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
            cursor = conn.cursor()

            if workspace_id:
                cursor.execute('''
                    SELECT mlp.* FROM mind_lens_profiles mlp
                    JOIN mind_lens_workspace_bindings mlwb ON mlp.id = mlwb.lens_id
                    WHERE mlwb.workspace_id = ? AND mlp.profile_id = ?
                ''', (workspace_id, profile_id))
                row = cursor.fetchone()
                if row:
                    return self._row_to_lens(row, conn)

            cursor.execute('''
                SELECT * FROM mind_lens_profiles
                WHERE profile_id = ? AND is_default = 1
                LIMIT 1
            ''', (profile_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_lens(row, conn)

        return None

    def _row_to_lens(self, row, conn) -> MindLensProfile:
        """Convert database row to MindLensProfile"""
        cursor = conn.cursor()

        cursor.execute('''
            SELECT node_id FROM lens_profile_nodes
            WHERE preset_id = ? AND state != ?
        ''', (row['id'], LensNodeState.OFF.value))
        active_node_ids = [r['node_id'] for r in cursor.fetchall()]

        cursor.execute('SELECT workspace_id FROM mind_lens_workspace_bindings WHERE lens_id = ?', (row['id'],))
        linked_workspace_ids = [r['workspace_id'] for r in cursor.fetchall()]

        return MindLensProfile(
            id=row['id'],
            profile_id=row['profile_id'],
            name=row['name'],
            description=row['description'],
            is_default=bool(row['is_default']),
            active_node_ids=active_node_ids,
            linked_workspace_ids=linked_workspace_ids,
            created_at=self.from_isoformat(row['created_at']),
            updated_at=self.from_isoformat(row['updated_at']),
        )

    # ============== Playbook Links ==============

    def link_node_to_playbook(
        self,
        node_id: str,
        playbook_code: str,
        profile_id: str,
        link_type: str = 'applies',
    ) -> bool:
        """Link node to playbook"""
        node = self.get_node(node_id)
        if not node or node.profile_id != profile_id:
            raise StoreValidationError(f"Node {node_id} not found or not owned by profile")

        link_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    INSERT INTO graph_node_playbook_links (
                        id, graph_node_id, playbook_code, link_type, created_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                ''', (link_id, node_id, playbook_code, link_type, self.to_isoformat(now)))
                conn.commit()
                return True
            except Exception as e:
                if 'UNIQUE' in str(e) or 'uq_graph_node_playbook' in str(e):
                    raise StoreValidationError("Link already exists")
                raise

    def unlink_node_from_playbook(
        self,
        node_id: str,
        playbook_code: str,
        profile_id: str,
    ) -> bool:
        """Unlink node from playbook"""
        node = self.get_node(node_id)
        if not node or node.profile_id != profile_id:
            raise StoreValidationError(f"Node {node_id} not found or not owned by profile")

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM graph_node_playbook_links
                WHERE graph_node_id = ? AND playbook_code = ?
            ''', (node_id, playbook_code))
            conn.commit()
            return cursor.rowcount > 0

    def get_node_linked_playbooks(self, node_id: str) -> List[str]:
        """Get all playbook codes linked to a node"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT playbook_code FROM graph_node_playbook_links
                WHERE graph_node_id = ?
            ''', (node_id,))
            return [row['playbook_code'] for row in cursor.fetchall()]

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
            cursor = conn.cursor()

            cursor.execute('''
                DELETE FROM mind_lens_workspace_bindings WHERE workspace_id = ?
            ''', (workspace_id,))

            cursor.execute('''
                INSERT INTO mind_lens_workspace_bindings (lens_id, workspace_id, created_at)
                VALUES (?, ?, ?)
            ''', (lens_id, workspace_id, self.to_isoformat(now)))

            conn.commit()
            return True

    def unbind_lens_from_workspace(
        self,
        workspace_id: str,
        profile_id: str,
    ) -> bool:
        """Unbind lens from workspace"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM mind_lens_workspace_bindings WHERE workspace_id = ?
            ''', (workspace_id,))
            conn.commit()
            return cursor.rowcount > 0

    # ============== Lens Profile Nodes ==============

    def upsert_lens_profile_node(
        self,
        preset_id: str,
        node_id: str,
        state: LensNodeState,
    ) -> LensProfileNode:
        """Create or update lens profile node state"""
        now = datetime.now(timezone.utc)

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id FROM lens_profile_nodes WHERE preset_id = ? AND node_id = ?
            ''', (preset_id, node_id))
            existing = cursor.fetchone()

            if existing:
                cursor.execute('''
                    UPDATE lens_profile_nodes
                    SET state = ?, updated_at = ?
                    WHERE preset_id = ? AND node_id = ?
                ''', (state.value, self.to_isoformat(now), preset_id, node_id))
            else:
                profile_node_id = str(uuid.uuid4())
                cursor.execute('''
                    INSERT INTO lens_profile_nodes (id, preset_id, node_id, state, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                ''', (profile_node_id, preset_id, node_id, state.value, self.to_isoformat(now)))

            conn.commit()

            cursor.execute('''
                SELECT * FROM lens_profile_nodes WHERE preset_id = ? AND node_id = ?
            ''', (preset_id, node_id))
            row = cursor.fetchone()
            return self._row_to_lens_profile_node(row)

    def get_lens_profile_nodes(self, preset_id: str) -> List[LensProfileNode]:
        """Get all lens profile nodes for a preset"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM lens_profile_nodes WHERE preset_id = ?
            ''', (preset_id,))
            rows = cursor.fetchall()
            return [self._row_to_lens_profile_node(row) for row in rows]

    def get_lens_profile_node(self, preset_id: str, node_id: str) -> Optional[LensProfileNode]:
        """Get specific lens profile node"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM lens_profile_nodes WHERE preset_id = ? AND node_id = ?
            ''', (preset_id, node_id))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_lens_profile_node(row)

    def delete_lens_profile_node(self, preset_id: str, node_id: str) -> bool:
        """Delete lens profile node"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM lens_profile_nodes WHERE preset_id = ? AND node_id = ?
            ''', (preset_id, node_id))
            conn.commit()
            return cursor.rowcount > 0

    def count_lens_profile_nodes(self, preset_id: str, state: Optional[LensNodeState] = None) -> int:
        """Count lens profile nodes by state"""
        query = 'SELECT COUNT(*) FROM lens_profile_nodes WHERE preset_id = ?'
        params = [preset_id]

        if state:
            query += ' AND state = ?'
            params.append(state.value)

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchone()[0]

    def _row_to_lens_profile_node(self, row) -> LensProfileNode:
        """Convert database row to LensProfileNode"""
        return LensProfileNode(
            id=row['id'],
            preset_id=row['preset_id'],
            node_id=row['node_id'],
            state=LensNodeState(row['state']),
            updated_at=self.from_isoformat(row['updated_at']),
        )

    # ============== Workspace Lens Overrides ==============

    def get_workspace_override(self, workspace_id: str) -> Optional[Dict[str, LensNodeState]]:
        """Get workspace lens overrides as dict (node_id -> state)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT node_id, state FROM workspace_lens_overrides WHERE workspace_id = ?
            ''', (workspace_id,))
            rows = cursor.fetchall()
            return {row['node_id']: LensNodeState(row['state']) for row in rows} if rows else None

    def get_workspace_overrides(self, workspace_id: str) -> List[WorkspaceLensOverride]:
        """Get all workspace lens overrides as list"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, workspace_id, node_id, state, updated_at
                FROM workspace_lens_overrides WHERE workspace_id = ?
            ''', (workspace_id,))
            rows = cursor.fetchall()
            return [self._row_to_workspace_override(row) for row in rows]

    def set_workspace_override(
        self,
        workspace_id: str,
        node_id: str,
        state: LensNodeState,
    ) -> WorkspaceLensOverride:
        """Set workspace lens override"""
        now = datetime.now(timezone.utc)

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id FROM workspace_lens_overrides WHERE workspace_id = ? AND node_id = ?
            ''', (workspace_id, node_id))
            existing = cursor.fetchone()

            if existing:
                cursor.execute('''
                    UPDATE workspace_lens_overrides
                    SET state = ?, updated_at = ?
                    WHERE workspace_id = ? AND node_id = ?
                ''', (state.value, self.to_isoformat(now), workspace_id, node_id))
            else:
                override_id = str(uuid.uuid4())
                cursor.execute('''
                    INSERT INTO workspace_lens_overrides (id, workspace_id, node_id, state, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                ''', (override_id, workspace_id, node_id, state.value, self.to_isoformat(now)))

            conn.commit()

            cursor.execute('''
                SELECT * FROM workspace_lens_overrides WHERE workspace_id = ? AND node_id = ?
            ''', (workspace_id, node_id))
            row = cursor.fetchone()
            return self._row_to_workspace_override(row)

    def remove_workspace_override(self, workspace_id: str, node_id: str) -> bool:
        """Remove workspace lens override"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM workspace_lens_overrides WHERE workspace_id = ? AND node_id = ?
            ''', (workspace_id, node_id))
            conn.commit()
            return cursor.rowcount > 0

    def _row_to_workspace_override(self, row) -> WorkspaceLensOverride:
        """Convert database row to WorkspaceLensOverride"""
        return WorkspaceLensOverride(
            id=row['id'],
            workspace_id=row['workspace_id'],
            node_id=row['node_id'],
            state=LensNodeState(row['state']),
            updated_at=self.from_isoformat(row['updated_at']),
        )

