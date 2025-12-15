"""
Tool Slot Mappings Store

Manages tool slot to tool ID mappings at workspace and project levels.
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
import json
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)


class ToolSlotMapping:
    """Tool slot mapping model"""

    def __init__(
        self,
        id: str,
        workspace_id: str,
        slot: str,
        tool_id: str,
        priority: int = 0,
        enabled: bool = True,
        project_id: Optional[str] = None,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.id = id
        self.workspace_id = workspace_id
        self.project_id = project_id
        self.slot = slot
        self.tool_id = tool_id
        self.priority = priority
        self.enabled = enabled
        self.created_at = created_at or datetime.utcnow()
        self.updated_at = updated_at or datetime.utcnow()
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'workspace_id': self.workspace_id,
            'project_id': self.project_id,
            'slot': self.slot,
            'tool_id': self.tool_id,
            'priority': self.priority,
            'enabled': self.enabled,
            'created_at': self.created_at.isoformat() if isinstance(self.created_at, datetime) else self.created_at,
            'updated_at': self.updated_at.isoformat() if isinstance(self.updated_at, datetime) else self.updated_at,
            'metadata': self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ToolSlotMapping':
        """Create from dictionary"""
        created_at = data.get('created_at')
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        updated_at = data.get('updated_at')
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)

        return cls(
            id=data['id'],
            workspace_id=data['workspace_id'],
            slot=data['slot'],
            tool_id=data['tool_id'],
            priority=data.get('priority', 0),
            enabled=data.get('enabled', True),
            project_id=data.get('project_id'),
            created_at=created_at,
            updated_at=updated_at,
            metadata=data.get('metadata', {})
        )


class ToolSlotMappingsStore:
    """Store for tool slot mappings"""

    def __init__(self, db_path: str):
        """
        Initialize store

        Args:
            db_path: Path to SQLite database
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize database table"""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS tool_slot_mappings (
                        id TEXT PRIMARY KEY,
                        workspace_id TEXT NOT NULL,
                        project_id TEXT,
                        slot TEXT NOT NULL,
                        tool_id TEXT NOT NULL,
                        priority INTEGER NOT NULL DEFAULT 0,
                        enabled INTEGER NOT NULL DEFAULT 1,
                        metadata TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        UNIQUE(workspace_id, project_id, slot)
                    )
                """)

                # Create indices for faster lookups
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_tool_slot_mappings_workspace_slot
                    ON tool_slot_mappings(workspace_id, slot, enabled)
                """)

                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_tool_slot_mappings_project_slot
                    ON tool_slot_mappings(project_id, slot, enabled)
                """)

                conn.commit()
        except Exception as e:
            logger.error(f"Failed to initialize tool_slot_mappings table: {e}", exc_info=True)
            raise

    def create_mapping(self, mapping: ToolSlotMapping) -> ToolSlotMapping:
        """
        Create a new mapping

        Args:
            mapping: ToolSlotMapping instance

        Returns:
            Created mapping
        """
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO tool_slot_mappings
                    (id, workspace_id, project_id, slot, tool_id, priority, enabled, metadata, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    mapping.id,
                    mapping.workspace_id,
                    mapping.project_id,
                    mapping.slot,
                    mapping.tool_id,
                    mapping.priority,
                    1 if mapping.enabled else 0,
                    json.dumps(mapping.metadata),
                    mapping.created_at.isoformat(),
                    mapping.updated_at.isoformat()
                ))
                conn.commit()

            logger.info(f"Created tool slot mapping: {mapping.slot} -> {mapping.tool_id}")
            return mapping

        except sqlite3.IntegrityError as e:
            logger.error(f"Failed to create mapping (duplicate?): {e}")
            raise ValueError(f"Mapping already exists for slot '{mapping.slot}' in workspace '{mapping.workspace_id}'")
        except Exception as e:
            logger.error(f"Failed to create mapping: {e}", exc_info=True)
            raise

    def get_mapping(self, mapping_id: str) -> Optional[ToolSlotMapping]:
        """
        Get mapping by ID

        Args:
            mapping_id: Mapping ID

        Returns:
            ToolSlotMapping or None if not found
        """
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("""
                    SELECT * FROM tool_slot_mappings WHERE id = ?
                """, (mapping_id,))
                row = cursor.fetchone()

                if not row:
                    return None

                return self._row_to_mapping(row)
        except Exception as e:
            logger.error(f"Failed to get mapping {mapping_id}: {e}", exc_info=True)
            return None

    def get_mappings(
        self,
        slot: Optional[str] = None,
        workspace_id: Optional[str] = None,
        project_id: Optional[str] = None,
        enabled_only: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get mappings with filters

        Args:
            slot: Filter by slot
            workspace_id: Filter by workspace_id
            project_id: Filter by project_id (None = workspace-level only)
            enabled_only: Only return enabled mappings

        Returns:
            List of mapping dictionaries
        """
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row

                conditions = []
                params = []

                if slot:
                    conditions.append("slot = ?")
                    params.append(slot)

                if workspace_id:
                    conditions.append("workspace_id = ?")
                    params.append(workspace_id)

                if project_id is not None:
                    conditions.append("project_id = ?")
                    params.append(project_id)
                elif project_id is None and workspace_id:
                    # Explicitly get workspace-level mappings (project_id IS NULL)
                    conditions.append("project_id IS NULL")

                if enabled_only:
                    conditions.append("enabled = 1")

                where_clause = " AND ".join(conditions) if conditions else "1=1"

                cursor = conn.execute(f"""
                    SELECT * FROM tool_slot_mappings WHERE {where_clause}
                    ORDER BY priority DESC, created_at DESC
                """, params)

                rows = cursor.fetchall()
                return [self._row_to_mapping(row).to_dict() for row in rows]

        except Exception as e:
            logger.error(f"Failed to get mappings: {e}", exc_info=True)
            return []

    def update_mapping(self, mapping_id: str, **updates) -> Optional[ToolSlotMapping]:
        """
        Update mapping

        Args:
            mapping_id: Mapping ID
            **updates: Fields to update

        Returns:
            Updated mapping or None if not found
        """
        try:
            existing = self.get_mapping(mapping_id)
            if not existing:
                return None

            # Build update query
            allowed_updates = ['tool_id', 'priority', 'enabled', 'metadata']
            set_clauses = []
            params = []

            for key, value in updates.items():
                if key in allowed_updates:
                    if key == 'metadata':
                        set_clauses.append(f"{key} = ?")
                        params.append(json.dumps(value))
                    elif key == 'enabled':
                        set_clauses.append(f"{key} = ?")
                        params.append(1 if value else 0)
                    else:
                        set_clauses.append(f"{key} = ?")
                        params.append(value)

            if not set_clauses:
                return existing

            set_clauses.append("updated_at = ?")
            params.append(datetime.utcnow().isoformat())
            params.append(mapping_id)

            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute(f"""
                    UPDATE tool_slot_mappings
                    SET {', '.join(set_clauses)}
                    WHERE id = ?
                """, params)
                conn.commit()

            return self.get_mapping(mapping_id)

        except Exception as e:
            logger.error(f"Failed to update mapping {mapping_id}: {e}", exc_info=True)
            return None

    def delete_mapping(self, mapping_id: str) -> bool:
        """
        Delete mapping

        Args:
            mapping_id: Mapping ID

        Returns:
            True if deleted, False if not found
        """
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.execute("DELETE FROM tool_slot_mappings WHERE id = ?", (mapping_id,))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to delete mapping {mapping_id}: {e}", exc_info=True)
            return False

    def _row_to_mapping(self, row: sqlite3.Row) -> ToolSlotMapping:
        """Convert database row to ToolSlotMapping"""
        # sqlite3.Row supports both index and column name access
        # Use column name access which works for both dict-like and Row objects
        metadata_str = row['metadata'] if 'metadata' in row.keys() else None
        metadata = {}
        if metadata_str:
            try:
                metadata = json.loads(metadata_str)
            except Exception:
                pass

        created_at_str = row['created_at'] if 'created_at' in row.keys() else None
        created_at = None
        if created_at_str:
            try:
                created_at = datetime.fromisoformat(created_at_str)
            except Exception:
                created_at = datetime.utcnow()

        updated_at_str = row['updated_at'] if 'updated_at' in row.keys() else None
        updated_at = None
        if updated_at_str:
            try:
                updated_at = datetime.fromisoformat(updated_at_str)
            except Exception:
                updated_at = datetime.utcnow()

        project_id = row['project_id'] if 'project_id' in row.keys() else None
        priority = row['priority'] if 'priority' in row.keys() else 0
        enabled = bool(row['enabled'] if 'enabled' in row.keys() else 1)

        return ToolSlotMapping(
            id=row['id'],
            workspace_id=row['workspace_id'],
            project_id=project_id,
            slot=row['slot'],
            tool_id=row['tool_id'],
            priority=priority,
            enabled=enabled,
            created_at=created_at,
            updated_at=updated_at,
            metadata=metadata
        )

