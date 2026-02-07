"""
ConversationThreads store for managing conversation thread records

ConversationThreads represent separate conversation streams within a workspace,
allowing users to organize conversations similar to ChatGPT threads.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from backend.app.services.stores.base import StoreBase, StoreNotFoundError
from backend.app.models.workspace import ConversationThread

logger = logging.getLogger(__name__)


class ConversationThreadsStore(StoreBase):
    """Store for managing conversation thread records"""

    def create_thread(self, thread: ConversationThread) -> ConversationThread:
        """
        Create a new conversation thread

        Args:
            thread: ConversationThread model instance

        Returns:
            Created conversation thread
        """
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO conversation_threads (
                    id, workspace_id, title, project_id, pinned_scope,
                    created_at, updated_at, last_message_at, message_count,
                    metadata, is_default
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                thread.id,
                thread.workspace_id,
                thread.title,
                thread.project_id,
                thread.pinned_scope,
                self.to_isoformat(thread.created_at),
                self.to_isoformat(thread.updated_at),
                self.to_isoformat(thread.last_message_at),
                thread.message_count,
                self.serialize_json(thread.metadata),
                1 if thread.is_default else 0
            ))
            logger.info(f"Created conversation thread: {thread.id} (workspace: {thread.workspace_id}, title: {thread.title})")
            return thread

    def get_thread(self, thread_id: str) -> Optional[ConversationThread]:
        """
        Get conversation thread by ID

        Args:
            thread_id: Thread ID

        Returns:
            ConversationThread model or None if not found
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM conversation_threads WHERE id = ?', (thread_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_thread(row)

    def list_threads_by_workspace(
        self,
        workspace_id: str,
        limit: Optional[int] = None
    ) -> List[ConversationThread]:
        """
        List conversation threads for a workspace

        Args:
            workspace_id: Workspace ID
            limit: Maximum number of threads to return (optional)

        Returns:
            List of conversation threads, ordered by updated_at DESC
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = 'SELECT * FROM conversation_threads WHERE workspace_id = ? ORDER BY updated_at DESC'
            params = [workspace_id]

            if limit:
                query += ' LIMIT ?'
                params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [self._row_to_thread(row) for row in rows]

    def get_default_thread(self, workspace_id: str) -> Optional[ConversationThread]:
        """
        Get the default thread for a workspace

        Args:
            workspace_id: Workspace ID

        Returns:
            Default ConversationThread or None if not found
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT * FROM conversation_threads WHERE workspace_id = ? AND is_default = 1 LIMIT 1',
                (workspace_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_thread(row)

    def update_thread(
        self,
        thread_id: str,
        title: Optional[str] = None,
        project_id: Optional[str] = None,
        pinned_scope: Optional[str] = None,
        last_message_at: Optional[datetime] = None,
        message_count: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[ConversationThread]:
        """
        Update conversation thread

        Args:
            thread_id: Thread ID
            title: New title (optional)
            project_id: New project ID (optional)
            pinned_scope: New pinned scope (optional)
            last_message_at: New last message timestamp (optional)
            message_count: New message count (optional)
            metadata: New metadata (optional, will be merged with existing)

        Returns:
            Updated ConversationThread or None if not found
        """
        with self.transaction() as conn:
            cursor = conn.cursor()

            updates = []
            params = []

            if title is not None:
                updates.append('title = ?')
                params.append(title)

            if project_id is not None:
                updates.append('project_id = ?')
                params.append(project_id)

            if pinned_scope is not None:
                updates.append('pinned_scope = ?')
                params.append(pinned_scope)

            if last_message_at is not None:
                updates.append('last_message_at = ?')
                params.append(self.to_isoformat(last_message_at))

            if message_count is not None:
                updates.append('message_count = ?')
                params.append(message_count)

            if metadata is not None:
                # Merge with existing metadata
                existing = self.get_thread(thread_id)
                if existing:
                    merged_metadata = {**existing.metadata, **metadata}
                    updates.append('metadata = ?')
                    params.append(self.serialize_json(merged_metadata))

            if not updates:
                return self.get_thread(thread_id)

            updates.append('updated_at = ?')
            params.append(self.to_isoformat(datetime.now(timezone.utc)))
            params.append(thread_id)

            query = f'UPDATE conversation_threads SET {", ".join(updates)} WHERE id = ?'
            cursor.execute(query, params)

            logger.info(f"Updated conversation thread: {thread_id}")
            return self.get_thread(thread_id)

    def delete_thread(self, thread_id: str) -> bool:
        """
        Delete a conversation thread

        Args:
            thread_id: Thread ID

        Returns:
            True if deleted, False if not found
        """
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM conversation_threads WHERE id = ?', (thread_id,))
            deleted = cursor.rowcount > 0
            if deleted:
                logger.info(f"Deleted conversation thread: {thread_id}")
            return deleted

    def _row_to_thread(self, row) -> ConversationThread:
        """Convert database row to ConversationThread"""
        metadata = self.deserialize_json(row['metadata'], {})
        return ConversationThread(
            id=str(row['id']),
            workspace_id=str(row['workspace_id']),
            title=str(row['title']),
            project_id=str(row['project_id']) if row['project_id'] else None,
            pinned_scope=str(row['pinned_scope']) if 'pinned_scope' in row.keys() and row['pinned_scope'] else None,
            created_at=self.from_isoformat(row['created_at']),
            updated_at=self.from_isoformat(row['updated_at']),
            last_message_at=self.from_isoformat(row['last_message_at']),
            message_count=int(row['message_count']) if row['message_count'] else 0,
            metadata=metadata,
            is_default=bool(row['is_default']) if 'is_default' in row.keys() and row['is_default'] else False
        )
