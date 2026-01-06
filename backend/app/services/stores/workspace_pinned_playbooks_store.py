"""
WorkspacePinnedPlaybooks store for managing workspace pinned playbooks
"""

import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from backend.app.services.stores.base import StoreBase
import uuid

logger = logging.getLogger(__name__)


class WorkspacePinnedPlaybooksStore(StoreBase):
    """Store for managing workspace pinned playbooks"""

    def pin_playbook(
        self,
        workspace_id: str,
        playbook_code: str,
        pinned_by: Optional[str] = None
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
        with self.transaction() as conn:
            cursor = conn.cursor()

            # Check if already pinned
            cursor.execute('''
                SELECT id FROM workspace_pinned_playbooks
                WHERE workspace_id = ? AND playbook_code = ?
            ''', (workspace_id, playbook_code))

            existing = cursor.fetchone()
            if existing:
                # Update pinned_at timestamp
                cursor.execute('''
                    UPDATE workspace_pinned_playbooks
                    SET pinned_at = ?, pinned_by = ?
                    WHERE id = ?
                ''', (
                    self.to_isoformat(datetime.utcnow()),
                    pinned_by,
                    existing[0]
                ))
                record_id = existing[0]
            else:
                # Create new record
                record_id = str(uuid.uuid4())
                cursor.execute('''
                    INSERT INTO workspace_pinned_playbooks (
                        id, workspace_id, playbook_code, pinned_at, pinned_by
                    ) VALUES (?, ?, ?, ?, ?)
                ''', (
                    record_id,
                    workspace_id,
                    playbook_code,
                    self.to_isoformat(datetime.utcnow()),
                    pinned_by
                ))

            logger.info(f"Pinned playbook {playbook_code} to workspace {workspace_id}")

            return {
                "id": record_id,
                "workspace_id": workspace_id,
                "playbook_code": playbook_code,
                "pinned_at": datetime.utcnow().isoformat(),
                "pinned_by": pinned_by
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
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM workspace_pinned_playbooks
                WHERE workspace_id = ? AND playbook_code = ?
            ''', (workspace_id, playbook_code))

            if cursor.rowcount > 0:
                logger.info(f"Unpinned playbook {playbook_code} from workspace {workspace_id}")
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
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, workspace_id, playbook_code, pinned_at, pinned_by
                FROM workspace_pinned_playbooks
                WHERE workspace_id = ?
                ORDER BY pinned_at DESC
            ''', (workspace_id,))

            results = []
            for row in cursor.fetchall():
                results.append({
                    "id": row[0],
                    "workspace_id": row[1],
                    "playbook_code": row[2],
                    "pinned_at": row[3],
                    "pinned_by": row[4]
                })
            return results

    def get_pinned_workspaces_for_playbook(self, playbook_code: str, limit: int = 3) -> List[Dict[str, Any]]:
        """
        Get workspaces that have pinned this playbook

        Args:
            playbook_code: Playbook code
            limit: Maximum number of workspaces to return

        Returns:
            List of workspace info with pinned_at timestamp
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT wpp.workspace_id, w.title, wpp.pinned_at
                FROM workspace_pinned_playbooks wpp
                LEFT JOIN workspaces w ON wpp.workspace_id = w.id
                WHERE wpp.playbook_code = ?
                ORDER BY wpp.pinned_at DESC
                LIMIT ?
            ''', (playbook_code, limit))

            results = []
            for row in cursor.fetchall():
                results.append({
                    "id": row[0],
                    "title": row[1] or "Unknown Workspace",
                    "pinned_at": row[2]
                })
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
            cursor = conn.cursor()
            cursor.execute('''
                SELECT COUNT(*) FROM workspace_pinned_playbooks
                WHERE workspace_id = ? AND playbook_code = ?
            ''', (workspace_id, playbook_code))

            return cursor.fetchone()[0] > 0

