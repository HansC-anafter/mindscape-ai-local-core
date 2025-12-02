"""
Workspaces store for Mindscape data persistence
Handles workspace CRUD operations
"""

from datetime import datetime
from typing import List, Optional
from backend.app.services.stores.base import StoreBase
from ...models.workspace import Workspace
import logging

logger = logging.getLogger(__name__)


class WorkspacesStore(StoreBase):
    """Store for managing workspaces"""

    def create_workspace(self, workspace: Workspace) -> Workspace:
        """Create a new workspace"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO workspaces (
                    id, owner_user_id, title, description, primary_project_id,
                    default_playbook_id, default_locale, mode, data_sources,
                    playbook_auto_execution_config, suggestion_history,
                    storage_base_path, artifacts_dir, uploads_dir, storage_config,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                workspace.id,
                workspace.owner_user_id,
                workspace.title,
                workspace.description,
                workspace.primary_project_id,
                workspace.default_playbook_id,
                workspace.default_locale,
                workspace.mode,
                self.serialize_json(workspace.data_sources) if workspace.data_sources else None,
                self.serialize_json(workspace.playbook_auto_execution_config) if workspace.playbook_auto_execution_config else None,
                self.serialize_json(workspace.suggestion_history) if workspace.suggestion_history else None,
                workspace.storage_base_path,
                workspace.artifacts_dir,
                workspace.uploads_dir,
                self.serialize_json(workspace.storage_config) if workspace.storage_config else None,
                self.to_isoformat(workspace.created_at),
                self.to_isoformat(workspace.updated_at)
            ))
            conn.commit()
            return workspace

    def get_workspace(self, workspace_id: str) -> Optional[Workspace]:
        """Get workspace by ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM workspaces WHERE id = ?', (workspace_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_workspace(row)

    def list_workspaces(
        self,
        owner_user_id: str,
        primary_project_id: Optional[str] = None,
        limit: int = 50
    ) -> List[Workspace]:
        """
        List workspaces for a user

        Args:
            owner_user_id: Owner user ID
            primary_project_id: Optional project filter
            limit: Maximum number of workspaces to return

        Returns:
            List of Workspace objects, ordered by updated_at DESC
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = 'SELECT * FROM workspaces WHERE owner_user_id = ?'
            params = [owner_user_id]

            if primary_project_id:
                query += ' AND primary_project_id = ?'
                params.append(primary_project_id)

            query += ' ORDER BY updated_at DESC LIMIT ?'
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [self._row_to_workspace(row) for row in rows]

    def update_workspace(self, workspace: Workspace) -> Workspace:
        """Update an existing workspace"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            workspace.updated_at = datetime.utcnow()
            cursor.execute('''
                UPDATE workspaces SET
                    title = ?,
                    description = ?,
                    primary_project_id = ?,
                    default_playbook_id = ?,
                    default_locale = ?,
                    mode = ?,
                    data_sources = ?,
                    playbook_auto_execution_config = ?,
                    suggestion_history = ?,
                    storage_base_path = ?,
                    artifacts_dir = ?,
                    uploads_dir = ?,
                    storage_config = ?,
                    updated_at = ?
                WHERE id = ?
            ''', (
                workspace.title,
                workspace.description,
                workspace.primary_project_id,
                workspace.default_playbook_id,
                workspace.default_locale,
                workspace.mode,
                self.serialize_json(workspace.data_sources) if workspace.data_sources else None,
                self.serialize_json(workspace.playbook_auto_execution_config) if workspace.playbook_auto_execution_config else None,
                self.serialize_json(workspace.suggestion_history) if workspace.suggestion_history else None,
                workspace.storage_base_path,
                workspace.artifacts_dir,
                workspace.uploads_dir,
                self.serialize_json(workspace.storage_config) if workspace.storage_config else None,
                self.to_isoformat(workspace.updated_at),
                workspace.id
            ))
            conn.commit()
            return workspace

    def delete_workspace(self, workspace_id: str) -> bool:
        """Delete a workspace"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM workspaces WHERE id = ?', (workspace_id,))
            conn.commit()
            return cursor.rowcount > 0

    def _row_to_workspace(self, row) -> Workspace:
        """Convert database row to Workspace"""
        # sqlite3.Row supports dict-like access: row['key']
        # For NULL values, SQLite returns None, so direct access is safe
        # Handle mode field - it may not exist in older database rows
        try:
            mode = row['mode'] if row['mode'] else None
        except (KeyError, IndexError):
            mode = None

        # Handle data_sources field - it may not exist in older database rows
        try:
            data_sources = self.deserialize_json(row['data_sources'], None) if row['data_sources'] else None
        except (KeyError, IndexError):
            data_sources = None

        # Handle playbook_auto_execution_config field - it may not exist in older database rows
        try:
            playbook_auto_execution_config = self.deserialize_json(row['playbook_auto_execution_config'], None) if row['playbook_auto_execution_config'] else None
        except (KeyError, IndexError):
            playbook_auto_execution_config = None

        # Handle suggestion_history field - it may not exist in older database rows
        try:
            suggestion_history = self.deserialize_json(row['suggestion_history'], None) if row['suggestion_history'] else None
        except (KeyError, IndexError):
            suggestion_history = None

        # Handle storage configuration fields - they may not exist in older database rows
        try:
            storage_base_path = row['storage_base_path'] if row['storage_base_path'] else None
        except (KeyError, IndexError):
            storage_base_path = None

        try:
            artifacts_dir = row['artifacts_dir'] if row['artifacts_dir'] else None
        except (KeyError, IndexError):
            artifacts_dir = None

        try:
            uploads_dir = row['uploads_dir'] if row['uploads_dir'] else None
        except (KeyError, IndexError):
            uploads_dir = None

        try:
            storage_config = self.deserialize_json(row['storage_config'], None) if row['storage_config'] else None
        except (KeyError, IndexError):
            storage_config = None

        return Workspace(
            id=row['id'],
            owner_user_id=row['owner_user_id'],
            title=row['title'],
            description=row['description'] if row['description'] else None,
            primary_project_id=row['primary_project_id'] if row['primary_project_id'] else None,
            default_playbook_id=row['default_playbook_id'] if row['default_playbook_id'] else None,
            default_locale=row['default_locale'] if row['default_locale'] else None,
            mode=mode,
            data_sources=data_sources,
            playbook_auto_execution_config=playbook_auto_execution_config,
            suggestion_history=suggestion_history,
            storage_base_path=storage_base_path,
            artifacts_dir=artifacts_dir,
            uploads_dir=uploads_dir,
            storage_config=storage_config,
            created_at=self.from_isoformat(row['created_at']),
            updated_at=self.from_isoformat(row['updated_at'])
        )
