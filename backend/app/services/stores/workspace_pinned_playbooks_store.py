"""
WorkspacePinnedPlaybooks store for managing workspace pinned playbooks
"""

import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
import uuid

from sqlalchemy import text

from app.services.stores.postgres_base import PostgresStoreBase

logger = logging.getLogger(__name__)


class WorkspacePinnedPlaybooksStore(PostgresStoreBase):
    """Store for managing workspace pinned playbooks"""

    def __init__(self, db_path: Optional[str] = None, db_role: str = "core"):
        super().__init__(db_role=db_role)
        self.db_path = db_path

    def pin_playbook(
        self,
        workspace_id: str,
        playbook_code: str,
        pinned_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Pin a playbook to a workspace

        Args:
            workspace_id: Workspace ID
            playbook_code: Playbook code
            pinned_by: User ID who pinned (optional)

        Returns:
            Pinned playbook record
        """
        pinned_at = datetime.utcnow()
        with self.transaction() as conn:
            existing = conn.execute(
                text(
                    """
                    SELECT id FROM workspace_pinned_playbooks
                    WHERE workspace_id = :workspace_id AND playbook_code = :playbook_code
                """
                ),
                {"workspace_id": workspace_id, "playbook_code": playbook_code},
            ).fetchone()

            if existing:
                record_id = existing.id
                conn.execute(
                    text(
                        """
                        UPDATE workspace_pinned_playbooks
                        SET pinned_at = :pinned_at, pinned_by = :pinned_by
                        WHERE id = :id
                    """
                    ),
                    {
                        "pinned_at": pinned_at,
                        "pinned_by": pinned_by,
                        "id": record_id,
                    },
                )
            else:
                record_id = str(uuid.uuid4())
                conn.execute(
                    text(
                        """
                        INSERT INTO workspace_pinned_playbooks (
                            id, workspace_id, playbook_code, pinned_at, pinned_by
                        ) VALUES (
                            :id, :workspace_id, :playbook_code, :pinned_at, :pinned_by
                        )
                    """
                    ),
                    {
                        "id": record_id,
                        "workspace_id": workspace_id,
                        "playbook_code": playbook_code,
                        "pinned_at": pinned_at,
                        "pinned_by": pinned_by,
                    },
                )

            logger.info(
                "Pinned playbook %s to workspace %s", playbook_code, workspace_id
            )

            return {
                "id": record_id,
                "workspace_id": workspace_id,
                "playbook_code": playbook_code,
                "pinned_at": pinned_at.isoformat(),
                "pinned_by": pinned_by,
            }

    def unpin_playbook(self, workspace_id: str, playbook_code: str) -> bool:
        """
        Unpin a playbook from a workspace

        Args:
            workspace_id: Workspace ID
            playbook_code: Playbook code

        Returns:
            True if unpinned, False if not found
        """
        with self.transaction() as conn:
            result = conn.execute(
                text(
                    """
                    DELETE FROM workspace_pinned_playbooks
                    WHERE workspace_id = :workspace_id AND playbook_code = :playbook_code
                """
                ),
                {"workspace_id": workspace_id, "playbook_code": playbook_code},
            )

            if result.rowcount > 0:
                logger.info(
                    "Unpinned playbook %s from workspace %s",
                    playbook_code,
                    workspace_id,
                )
                return True
            return False

    def list_pinned_playbooks(self, workspace_id: str) -> List[Dict[str, Any]]:
        """
        List all pinned playbooks for a workspace

        Args:
            workspace_id: Workspace ID

        Returns:
            List of pinned playbook records
        """
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT id, workspace_id, playbook_code, pinned_at, pinned_by
                    FROM workspace_pinned_playbooks
                    WHERE workspace_id = :workspace_id
                    ORDER BY pinned_at DESC
                """
                ),
                {"workspace_id": workspace_id},
            ).fetchall()

            results = []
            for row in rows:
                pinned_at = row.pinned_at
                if isinstance(pinned_at, datetime):
                    pinned_at_value = pinned_at.isoformat()
                else:
                    pinned_at_value = pinned_at
                results.append(
                    {
                        "id": row.id,
                        "workspace_id": row.workspace_id,
                        "playbook_code": row.playbook_code,
                        "pinned_at": pinned_at_value,
                        "pinned_by": row.pinned_by,
                    }
                )
            return results

    def get_pinned_workspaces_for_playbook(
        self, playbook_code: str, limit: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Get workspaces that have pinned this playbook

        Args:
            playbook_code: Playbook code
            limit: Maximum number of workspaces to return

        Returns:
            List of workspace info with pinned_at timestamp
        """
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT wpp.workspace_id, w.title, wpp.pinned_at
                    FROM workspace_pinned_playbooks wpp
                    LEFT JOIN workspaces w ON wpp.workspace_id = w.id
                    WHERE wpp.playbook_code = :playbook_code
                    ORDER BY wpp.pinned_at DESC
                    LIMIT :limit
                """
                ),
                {"playbook_code": playbook_code, "limit": limit},
            ).fetchall()

            results = []
            for row in rows:
                pinned_at = row.pinned_at
                if isinstance(pinned_at, datetime):
                    pinned_at_value = pinned_at.isoformat()
                else:
                    pinned_at_value = pinned_at
                results.append(
                    {
                        "id": row.workspace_id,
                        "title": row.title or "Unknown Workspace",
                        "pinned_at": pinned_at_value,
                    }
                )
            return results

    def is_pinned(self, workspace_id: str, playbook_code: str) -> bool:
        """
        Check if a playbook is pinned in a workspace

        Args:
            workspace_id: Workspace ID
            playbook_code: Playbook code

        Returns:
            True if pinned, False otherwise
        """
        with self.get_connection() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT COUNT(*) AS pinned_count
                    FROM workspace_pinned_playbooks
                    WHERE workspace_id = :workspace_id AND playbook_code = :playbook_code
                """
                ),
                {"workspace_id": workspace_id, "playbook_code": playbook_code},
            ).fetchone()

            return (row.pinned_count if row else 0) > 0
