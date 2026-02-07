"""
ThreadReferences store for managing thread reference records

ThreadReferences represent external resources (Obsidian notes, Notion pages,
WordPress posts, local files, URLs) pinned to conversation threads.
"""

import logging
from datetime import datetime
from typing import List, Optional
from backend.app.services.stores.base import StoreBase
from backend.app.models.workspace import ThreadReference

logger = logging.getLogger(__name__)


class ThreadReferencesStore(StoreBase):
    """Store for managing thread reference records"""

    def create_reference(self, reference: ThreadReference) -> ThreadReference:
        """
        Create a new thread reference

        Args:
            reference: ThreadReference model instance

        Returns:
            Created thread reference
        """
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO thread_references (
                    id, workspace_id, thread_id, source_type, uri, title,
                    snippet, reason, pinned_by, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                reference.id,
                reference.workspace_id,
                reference.thread_id,
                reference.source_type,
                reference.uri,
                reference.title,
                reference.snippet,
                reference.reason,
                reference.pinned_by,
                self.to_isoformat(reference.created_at),
                self.to_isoformat(reference.updated_at)
            ))
            logger.info(f"Created thread reference: {reference.id} (thread: {reference.thread_id}, type: {reference.source_type})")
            return reference

    def get_reference(self, reference_id: str) -> Optional[ThreadReference]:
        """
        Get reference by ID

        Args:
            reference_id: Reference ID

        Returns:
            ThreadReference model or None if not found
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM thread_references WHERE id = ?', (reference_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_reference(row)

    def get_by_thread(
        self,
        workspace_id: str,
        thread_id: str,
        limit: Optional[int] = 100
    ) -> List[ThreadReference]:
        """
        Get references for a specific conversation thread

        Args:
            workspace_id: Workspace ID
            thread_id: Thread ID
            limit: Maximum number of references to return (default: 100)

        Returns:
            List of references for the thread, ordered by created_at DESC
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = 'SELECT * FROM thread_references WHERE workspace_id = ? AND thread_id = ? ORDER BY created_at DESC'
            params = [workspace_id, thread_id]

            if limit:
                query += ' LIMIT ?'
                params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [self._row_to_reference(row) for row in rows]

    def update_reference(self, reference_id: str, **kwargs) -> bool:
        """
        Update reference fields

        Args:
            reference_id: Reference ID
            **kwargs: Fields to update (title, snippet, reason, etc.)

        Returns:
            True if update successful, False otherwise
        """
        try:
            with self.transaction() as conn:
                cursor = conn.cursor()
                updates = []
                params = []

                for key, value in kwargs.items():
                    if key == 'updated_at':
                        updates.append('updated_at = ?')
                        params.append(self.to_isoformat(value) if isinstance(value, datetime) else value)
                    elif key not in ['id', 'workspace_id', 'thread_id', 'created_at']:
                        updates.append(f'{key} = ?')
                        params.append(value)

                if updates:
                    params.append(reference_id)
                    query = f'UPDATE thread_references SET {", ".join(updates)} WHERE id = ?'
                    cursor.execute(query, params)
                    return cursor.rowcount > 0
                return False
        except Exception as e:
            logger.error(f"Failed to update reference {reference_id}: {e}")
            return False

    def delete_reference(self, reference_id: str) -> bool:
        """
        Delete reference by ID

        Args:
            reference_id: Reference ID

        Returns:
            True if deletion successful, False otherwise
        """
        try:
            with self.transaction() as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM thread_references WHERE id = ?', (reference_id,))
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to delete reference {reference_id}: {e}")
            return False

    def _row_to_reference(self, row) -> ThreadReference:
        """Convert database row to ThreadReference model"""
        return ThreadReference(
            id=row['id'],
            workspace_id=row['workspace_id'],
            thread_id=row['thread_id'],
            source_type=row['source_type'],
            uri=row['uri'],
            title=row['title'],
            snippet=row['snippet'] if 'snippet' in row.keys() and row['snippet'] else None,
            reason=row['reason'] if 'reason' in row.keys() and row['reason'] else None,
            pinned_by=row['pinned_by'] if 'pinned_by' in row.keys() and row['pinned_by'] else 'user',
            created_at=self.from_isoformat(row['created_at']),
            updated_at=self.from_isoformat(row['updated_at'])
        )
