"""
IntentTags Store Service

Handles storage and retrieval of IntentTag records for candidate/confirmed intent tracking.
"""

import json
import sqlite3
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

from ...models.mindscape import IntentTag, IntentTagStatus, IntentSource

logger = logging.getLogger(__name__)


class IntentTagsStore:
    """Store for IntentTag records"""

    def __init__(self, db_path: str):
        """
        Initialize IntentTagsStore

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path

    def create_intent_tag(self, intent_tag: IntentTag) -> IntentTag:
        """
        Create a new IntentTag record

        Args:
            intent_tag: IntentTag model instance

        Returns:
            Created IntentTag
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                cursor.execute('''
                    INSERT INTO intent_tags (
                        id, workspace_id, profile_id, label, confidence,
                        status, source, execution_id, playbook_code, message_id,
                        metadata, created_at, updated_at, confirmed_at, rejected_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    intent_tag.id,
                    intent_tag.workspace_id,
                    intent_tag.profile_id,
                    intent_tag.label,
                    intent_tag.confidence,
                    intent_tag.status.value,
                    intent_tag.source.value,
                    intent_tag.execution_id,
                    intent_tag.playbook_code,
                    intent_tag.message_id,
                    json.dumps(intent_tag.metadata),
                    intent_tag.created_at.isoformat(),
                    intent_tag.updated_at.isoformat(),
                    intent_tag.confirmed_at.isoformat() if intent_tag.confirmed_at else None,
                    intent_tag.rejected_at.isoformat() if intent_tag.rejected_at else None
                ))

                conn.commit()
                logger.info(f"Created IntentTag {intent_tag.id} with status {intent_tag.status.value}")
                return intent_tag
        except Exception as e:
            logger.error(f"Failed to create IntentTag: {e}", exc_info=True)
            raise

    def get_intent_tag(self, intent_tag_id: str) -> Optional[IntentTag]:
        """
        Get IntentTag by ID

        Args:
            intent_tag_id: IntentTag ID

        Returns:
            IntentTag or None if not found
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                cursor.execute('SELECT * FROM intent_tags WHERE id = ?', (intent_tag_id,))
                row = cursor.fetchone()

                if not row:
                    return None

                return self._row_to_intent_tag(row)
        except Exception as e:
            logger.error(f"Failed to get IntentTag {intent_tag_id}: {e}", exc_info=True)
            return None

    def list_intent_tags(
        self,
        workspace_id: Optional[str] = None,
        profile_id: Optional[str] = None,
        status: Optional[IntentTagStatus] = None,
        execution_id: Optional[str] = None,
        limit: int = 100
    ) -> List[IntentTag]:
        """
        List IntentTags with filters

        Args:
            workspace_id: Filter by workspace ID
            profile_id: Filter by profile ID
            status: Filter by status
            execution_id: Filter by execution ID
            limit: Maximum number of results

        Returns:
            List of IntentTags
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                query = 'SELECT * FROM intent_tags WHERE 1=1'
                params = []

                if workspace_id:
                    query += ' AND workspace_id = ?'
                    params.append(workspace_id)
                if profile_id:
                    query += ' AND profile_id = ?'
                    params.append(profile_id)
                if status:
                    query += ' AND status = ?'
                    params.append(status.value)
                if execution_id:
                    query += ' AND execution_id = ?'
                    params.append(execution_id)

                query += ' ORDER BY created_at DESC LIMIT ?'
                params.append(limit)

                cursor.execute(query, params)
                rows = cursor.fetchall()

                return [self._row_to_intent_tag(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to list IntentTags: {e}", exc_info=True)
            return []

    def update_intent_tag_status(
        self,
        intent_tag_id: str,
        status: IntentTagStatus,
        updated_at: Optional[datetime] = None
    ) -> bool:
        """
        Update IntentTag status

        Args:
            intent_tag_id: IntentTag ID
            status: New status
            updated_at: Update timestamp (defaults to now)

        Returns:
            True if update succeeded
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                update_time = updated_at or datetime.utcnow()

                # Set confirmed_at or rejected_at based on status
                confirmed_at = None
                rejected_at = None
                if status == IntentTagStatus.CONFIRMED:
                    confirmed_at = update_time
                    # Check if confirmed_at is already set
                    cursor.execute('SELECT confirmed_at FROM intent_tags WHERE id = ?', (intent_tag_id,))
                    row = cursor.fetchone()
                    if row and row['confirmed_at']:
                        confirmed_at = datetime.fromisoformat(row['confirmed_at'])
                elif status == IntentTagStatus.REJECTED:
                    rejected_at = update_time
                    # Check if rejected_at is already set
                    cursor.execute('SELECT rejected_at FROM intent_tags WHERE id = ?', (intent_tag_id,))
                    row = cursor.fetchone()
                    if row and row['rejected_at']:
                        rejected_at = datetime.fromisoformat(row['rejected_at'])

                cursor.execute('''
                    UPDATE intent_tags
                    SET status = ?, updated_at = ?,
                        confirmed_at = COALESCE(?, confirmed_at),
                        rejected_at = COALESCE(?, rejected_at)
                    WHERE id = ?
                ''', (
                    status.value,
                    update_time.isoformat(),
                    confirmed_at.isoformat() if confirmed_at else None,
                    rejected_at.isoformat() if rejected_at else None,
                    intent_tag_id
                ))

                conn.commit()
                logger.info(f"Updated IntentTag {intent_tag_id} status to {status.value}")
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to update IntentTag status: {e}", exc_info=True)
            return False

    def confirm_intent(self, intent_tag_id: str) -> bool:
        """
        Confirm an intent tag (candidate -> confirmed)

        Args:
            intent_tag_id: IntentTag ID

        Returns:
            True if confirmation succeeded
        """
        return self.update_intent_tag_status(intent_tag_id, IntentTagStatus.CONFIRMED)

    def reject_intent(self, intent_tag_id: str) -> bool:
        """
        Reject an intent tag (candidate -> rejected)

        Args:
            intent_tag_id: IntentTag ID

        Returns:
            True if rejection succeeded
        """
        return self.update_intent_tag_status(intent_tag_id, IntentTagStatus.REJECTED)

    def update_intent_tag_label(self, intent_tag_id: str, new_label: str) -> bool:
        """
        Update intent tag label

        Args:
            intent_tag_id: IntentTag ID
            new_label: New label text

        Returns:
            True if update succeeded
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                cursor.execute('''
                    UPDATE intent_tags
                    SET label = ?, updated_at = ?
                    WHERE id = ?
                ''', (
                    new_label,
                    datetime.utcnow().isoformat(),
                    intent_tag_id
                ))

                conn.commit()
                logger.info(f"Updated IntentTag {intent_tag_id} label to: {new_label}")
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to update IntentTag label: {e}", exc_info=True)
            return False

    def _row_to_intent_tag(self, row: sqlite3.Row) -> IntentTag:
        """Convert database row to IntentTag model"""
        metadata = {}
        if row['metadata']:
            try:
                metadata = json.loads(row['metadata'])
            except Exception:
                pass

        return IntentTag(
            id=row['id'],
            workspace_id=row['workspace_id'],
            profile_id=row['profile_id'],
            label=row['label'],
            confidence=row['confidence'],
            status=IntentTagStatus(row['status']),
            source=IntentSource(row['source']),
            execution_id=row['execution_id'],
            playbook_code=row['playbook_code'],
            message_id=row['message_id'],
            metadata=metadata,
            created_at=datetime.fromisoformat(row['created_at']),
            updated_at=datetime.fromisoformat(row['updated_at']),
            confirmed_at=datetime.fromisoformat(row['confirmed_at']) if row['confirmed_at'] else None,
            rejected_at=datetime.fromisoformat(row['rejected_at']) if row['rejected_at'] else None
        )

