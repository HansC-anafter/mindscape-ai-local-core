"""
Tool Slot Mappings Store

Manages tool slot to tool ID mappings at workspace and project levels.
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
import json

from sqlalchemy import text

from app.services.stores.postgres_base import PostgresStoreBase

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
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.id = id
        self.workspace_id = workspace_id
        self.project_id = project_id
        self.slot = slot
        self.tool_id = tool_id
        self.priority = priority
        self.enabled = enabled
        self.created_at = created_at or _utc_now()
        self.updated_at = updated_at or _utc_now()
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "project_id": self.project_id,
            "slot": self.slot,
            "tool_id": self.tool_id,
            "priority": self.priority,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat()
            if isinstance(self.created_at, datetime)
            else self.created_at,
            "updated_at": self.updated_at.isoformat()
            if isinstance(self.updated_at, datetime)
            else self.updated_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolSlotMapping":
        """Create from dictionary"""
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        updated_at = data.get("updated_at")
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)

        return cls(
            id=data["id"],
            workspace_id=data["workspace_id"],
            slot=data["slot"],
            tool_id=data["tool_id"],
            priority=data.get("priority", 0),
            enabled=data.get("enabled", True),
            project_id=data.get("project_id"),
            created_at=created_at,
            updated_at=updated_at,
            metadata=data.get("metadata", {}),
        )


class ToolSlotMappingsStore(PostgresStoreBase):
    """Store for tool slot mappings (Postgres)."""

    def __init__(self, db_path: Optional[str] = None, db_role: str = "core"):
        super().__init__(db_role=db_role)
        self.db_path = db_path

    def create_mapping(self, mapping: ToolSlotMapping) -> ToolSlotMapping:
        """Create or replace a mapping"""
        try:
            with self.transaction() as conn:
                conn.execute(
                    text(
                        """
                        INSERT INTO tool_slot_mappings
                        (id, workspace_id, project_id, slot, tool_id, priority, enabled, metadata, created_at, updated_at)
                        VALUES
                        (:id, :workspace_id, :project_id, :slot, :tool_id, :priority, :enabled, :metadata, :created_at, :updated_at)
                        ON CONFLICT (workspace_id, project_id, slot) DO UPDATE SET
                            tool_id = EXCLUDED.tool_id,
                            priority = EXCLUDED.priority,
                            enabled = EXCLUDED.enabled,
                            metadata = EXCLUDED.metadata,
                            updated_at = EXCLUDED.updated_at
                    """
                    ),
                    {
                        "id": mapping.id,
                        "workspace_id": mapping.workspace_id,
                        "project_id": mapping.project_id,
                        "slot": mapping.slot,
                        "tool_id": mapping.tool_id,
                        "priority": mapping.priority,
                        "enabled": mapping.enabled,
                        "metadata": json.dumps(mapping.metadata),
                        "created_at": mapping.created_at,
                        "updated_at": mapping.updated_at,
                    },
                )

            logger.info(
                f"Created tool slot mapping: {mapping.slot} -> {mapping.tool_id}"
            )
            return mapping
        except Exception as e:
            logger.error(f"Failed to create mapping: {e}", exc_info=True)
            raise

    def get_mapping(self, mapping_id: str) -> Optional[ToolSlotMapping]:
        """Get mapping by ID"""
        try:
            with self.get_connection() as conn:
                row = conn.execute(
                    text("SELECT * FROM tool_slot_mappings WHERE id = :id"),
                    {"id": mapping_id},
                ).fetchone()

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
        enabled_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """Get mappings with filters"""
        try:
            with self.get_connection() as conn:
                conditions = []
                params: Dict[str, Any] = {}

                if slot:
                    conditions.append("slot = :slot")
                    params["slot"] = slot

                if workspace_id:
                    conditions.append("workspace_id = :workspace_id")
                    params["workspace_id"] = workspace_id

                if project_id is not None:
                    conditions.append("project_id = :project_id")
                    params["project_id"] = project_id
                elif project_id is None and workspace_id:
                    conditions.append("project_id IS NULL")

                if enabled_only:
                    conditions.append("enabled = TRUE")

                where_clause = " AND ".join(conditions) if conditions else "1=1"

                rows = conn.execute(
                    text(
                        f"""
                        SELECT * FROM tool_slot_mappings WHERE {where_clause}
                        ORDER BY priority DESC, created_at DESC
                    """
                    ),
                    params,
                ).fetchall()

                return [self._row_to_mapping(row).to_dict() for row in rows]

        except Exception as e:
            logger.error(f"Failed to get mappings: {e}", exc_info=True)
            return []

    def update_mapping(self, mapping_id: str, **updates) -> Optional[ToolSlotMapping]:
        """Update mapping"""
        if not updates:
            return self.get_mapping(mapping_id)

        update_fields = []
        params: Dict[str, Any] = {"id": mapping_id}

        if "tool_id" in updates:
            update_fields.append("tool_id = :tool_id")
            params["tool_id"] = updates["tool_id"]

        if "priority" in updates:
            update_fields.append("priority = :priority")
            params["priority"] = updates["priority"]

        if "enabled" in updates:
            update_fields.append("enabled = :enabled")
            params["enabled"] = updates["enabled"]

        if "metadata" in updates:
            update_fields.append("metadata = :metadata")
            params["metadata"] = json.dumps(updates["metadata"]) if updates["metadata"] else None

        update_fields.append("updated_at = :updated_at")
        params["updated_at"] = _utc_now()

        with self.transaction() as conn:
            result = conn.execute(
                text(
                    f"UPDATE tool_slot_mappings SET {', '.join(update_fields)} WHERE id = :id"
                ),
                params,
            )
            if result.rowcount == 0:
                return None

        return self.get_mapping(mapping_id)

    def delete_mapping(self, mapping_id: str) -> bool:
        """Delete mapping by ID"""
        with self.transaction() as conn:
            result = conn.execute(
                text("DELETE FROM tool_slot_mappings WHERE id = :id"),
                {"id": mapping_id},
            )
            return result.rowcount > 0

    def _row_to_mapping(self, row) -> ToolSlotMapping:
        """Convert database row to ToolSlotMapping"""
        data = row._mapping if hasattr(row, "_mapping") else row

        metadata = {}
        if data["metadata"]:
            try:
                metadata = json.loads(data["metadata"])
            except Exception:
                metadata = {}

        return ToolSlotMapping(
            id=data["id"],
            workspace_id=data["workspace_id"],
            project_id=data["project_id"],
            slot=data["slot"],
            tool_id=data["tool_id"],
            priority=data["priority"],
            enabled=bool(data["enabled"]),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            metadata=metadata,
        )
