"""
IntentTags Store Service

Handles storage and retrieval of IntentTag records for candidate/confirmed intent tracking.
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)

from sqlalchemy import text

from app.services.stores.postgres_base import PostgresStoreBase
from ...models.mindscape import IntentTag, IntentTagStatus, IntentSource

logger = logging.getLogger(__name__)


class IntentTagsStore(PostgresStoreBase):
    """Store for IntentTag records (Postgres)."""

    def __init__(self, db_path: Optional[str] = None, db_role: str = "core"):
        super().__init__(db_role=db_role)
        self.db_path = db_path

    def create_intent_tag(self, intent_tag: IntentTag) -> IntentTag:
        """Create a new IntentTag record"""
        try:
            with self.transaction() as conn:
                conn.execute(
                    text(
                        """
                        INSERT INTO intent_tags (
                            id, workspace_id, profile_id, label, confidence,
                            status, source, execution_id, playbook_code, message_id,
                            metadata, created_at, updated_at, confirmed_at, rejected_at
                        ) VALUES (
                            :id, :workspace_id, :profile_id, :label, :confidence,
                            :status, :source, :execution_id, :playbook_code, :message_id,
                            :metadata, :created_at, :updated_at, :confirmed_at, :rejected_at
                        )
                    """
                    ),
                    {
                        "id": intent_tag.id,
                        "workspace_id": intent_tag.workspace_id,
                        "profile_id": intent_tag.profile_id,
                        "label": intent_tag.label,
                        "confidence": intent_tag.confidence,
                        "status": intent_tag.status.value,
                        "source": intent_tag.source.value,
                        "execution_id": intent_tag.execution_id,
                        "playbook_code": intent_tag.playbook_code,
                        "message_id": intent_tag.message_id,
                        "metadata": self.serialize_json(intent_tag.metadata),
                        "created_at": intent_tag.created_at,
                        "updated_at": intent_tag.updated_at,
                        "confirmed_at": intent_tag.confirmed_at,
                        "rejected_at": intent_tag.rejected_at,
                    },
                )
                logger.info(
                    f"Created IntentTag {intent_tag.id} with status {intent_tag.status.value}"
                )
                return intent_tag
        except Exception as e:
            logger.error(f"Failed to create IntentTag: {e}", exc_info=True)
            raise

    def get_intent_tag(self, intent_tag_id: str) -> Optional[IntentTag]:
        """Get IntentTag by ID"""
        try:
            with self.get_connection() as conn:
                row = conn.execute(
                    text("SELECT * FROM intent_tags WHERE id = :id"),
                    {"id": intent_tag_id},
                ).fetchone()

                if not row:
                    return None

                return self._row_to_intent_tag(row)
        except Exception as e:
            logger.error(
                f"Failed to get IntentTag {intent_tag_id}: {e}", exc_info=True
            )
            return None

    def list_intent_tags(
        self,
        workspace_id: Optional[str] = None,
        profile_id: Optional[str] = None,
        status: Optional[IntentTagStatus] = None,
        execution_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[IntentTag]:
        """List IntentTags with filters"""
        try:
            with self.get_connection() as conn:
                query = "SELECT * FROM intent_tags WHERE 1=1"
                params: Dict[str, Any] = {"limit": limit}

                if workspace_id:
                    query += " AND workspace_id = :workspace_id"
                    params["workspace_id"] = workspace_id
                if profile_id:
                    query += " AND profile_id = :profile_id"
                    params["profile_id"] = profile_id
                if status:
                    query += " AND status = :status"
                    params["status"] = status.value
                if execution_id:
                    query += " AND execution_id = :execution_id"
                    params["execution_id"] = execution_id

                query += " ORDER BY created_at DESC LIMIT :limit"

                rows = conn.execute(text(query), params).fetchall()
                return [self._row_to_intent_tag(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to list IntentTags: {e}", exc_info=True)
            return []

    def update_intent_tag_status(
        self,
        intent_tag_id: str,
        status: IntentTagStatus,
        updated_at: Optional[datetime] = None,
    ) -> bool:
        """Update IntentTag status"""
        try:
            with self.transaction() as conn:
                update_time = updated_at or _utc_now()

                confirmed_at = None
                rejected_at = None
                if status == IntentTagStatus.CONFIRMED:
                    row = conn.execute(
                        text("SELECT confirmed_at FROM intent_tags WHERE id = :id"),
                        {"id": intent_tag_id},
                    ).fetchone()
                    if row and row._mapping.get("confirmed_at"):
                        confirmed_at = row._mapping["confirmed_at"]
                    else:
                        confirmed_at = update_time
                elif status == IntentTagStatus.REJECTED:
                    row = conn.execute(
                        text("SELECT rejected_at FROM intent_tags WHERE id = :id"),
                        {"id": intent_tag_id},
                    ).fetchone()
                    if row and row._mapping.get("rejected_at"):
                        rejected_at = row._mapping["rejected_at"]
                    else:
                        rejected_at = update_time

                result = conn.execute(
                    text(
                        """
                        UPDATE intent_tags
                        SET status = :status, updated_at = :updated_at,
                            confirmed_at = COALESCE(:confirmed_at, confirmed_at),
                            rejected_at = COALESCE(:rejected_at, rejected_at)
                        WHERE id = :id
                    """
                    ),
                    {
                        "status": status.value,
                        "updated_at": update_time,
                        "confirmed_at": confirmed_at,
                        "rejected_at": rejected_at,
                        "id": intent_tag_id,
                    },
                )

                logger.info(
                    f"Updated IntentTag {intent_tag_id} status to {status.value}"
                )
                return result.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to update IntentTag status: {e}", exc_info=True)
            return False

    def confirm_intent(self, intent_tag_id: str) -> bool:
        """Confirm an intent tag (candidate -> confirmed)"""
        return self.update_intent_tag_status(intent_tag_id, IntentTagStatus.CONFIRMED)

    def reject_intent(self, intent_tag_id: str) -> bool:
        """Reject an intent tag (candidate -> rejected)"""
        return self.update_intent_tag_status(intent_tag_id, IntentTagStatus.REJECTED)

    def update_intent_tag_label(self, intent_tag_id: str, new_label: str) -> bool:
        """Update intent tag label"""
        try:
            with self.transaction() as conn:
                result = conn.execute(
                    text(
                        """
                        UPDATE intent_tags
                        SET label = :label, updated_at = :updated_at
                        WHERE id = :id
                    """
                    ),
                    {
                        "label": new_label,
                        "updated_at": _utc_now(),
                        "id": intent_tag_id,
                    },
                )
                logger.info(
                    f"Updated IntentTag {intent_tag_id} label to: {new_label}"
                )
                return result.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to update IntentTag label: {e}", exc_info=True)
            return False

    def _row_to_intent_tag(self, row) -> IntentTag:
        """Convert database row to IntentTag model"""
        data = row._mapping if hasattr(row, "_mapping") else row

        metadata = self.deserialize_json(data["metadata"], {})

        return IntentTag(
            id=data["id"],
            workspace_id=data["workspace_id"],
            profile_id=data["profile_id"],
            label=data["label"],
            confidence=data["confidence"],
            status=IntentTagStatus(data["status"]),
            source=IntentSource(data["source"]),
            execution_id=data["execution_id"],
            playbook_code=data["playbook_code"],
            message_id=data["message_id"],
            metadata=metadata,
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            confirmed_at=data["confirmed_at"],
            rejected_at=data["rejected_at"],
        )
