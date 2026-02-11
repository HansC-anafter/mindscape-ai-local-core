"""
UserPlaybookMeta store for managing user-specific playbook metadata
"""

import logging
import json
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
from typing import Optional, Dict, Any
from backend.app.services.stores.base import StoreBase
import uuid

logger = logging.getLogger(__name__)


class UserPlaybookMetaStore(StoreBase):
    """Store for managing user-specific playbook metadata"""

    def get_user_meta(
        self,
        profile_id: str,
        playbook_code: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get user meta for a playbook

        Args:
            profile_id: User profile ID
            playbook_code: Playbook code

        Returns:
            User meta dict or None if not found
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT favorite, use_count, last_used_at, custom_tags, user_notes
                FROM user_playbook_meta
                WHERE profile_id = ? AND playbook_code = ?
            ''', (profile_id, playbook_code))

            row = cursor.fetchone()
            if not row:
                return None

            return {
                "favorite": bool(row[0]),
                "use_count": row[1] or 0,
                "last_used_at": row[2],
                "custom_tags": json.loads(row[3]) if row[3] else [],
                "user_notes": row[4]
            }

    def update_user_meta(
        self,
        profile_id: str,
        playbook_code: str,
        updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update user meta for a playbook

        Args:
            profile_id: User profile ID
            playbook_code: Playbook code
            updates: Dict with fields to update (favorite, use_count, custom_tags, user_notes)

        Returns:
            Updated user meta dict
        """
        with self.transaction() as conn:
            cursor = conn.cursor()

            # Check if record exists
            cursor.execute('''
                SELECT id FROM user_playbook_meta
                WHERE profile_id = ? AND playbook_code = ?
            ''', (profile_id, playbook_code))

            existing = cursor.fetchone()
            now = self.to_isoformat(_utc_now())

            if existing:
                # Update existing record
                record_id = existing[0]
                update_fields = ["updated_at = ?"]
                update_values = [now]

                if "favorite" in updates:
                    update_fields.append("favorite = ?")
                    update_values.append(1 if updates["favorite"] else 0)

                if "use_count" in updates:
                    update_fields.append("use_count = ?")
                    update_values.append(updates["use_count"])
                elif "increment_use_count" in updates and updates["increment_use_count"]:
                    update_fields.append("use_count = use_count + 1")
                    update_fields.append("last_used_at = ?")
                    update_values.append(now)

                if "custom_tags" in updates:
                    update_fields.append("custom_tags = ?")
                    update_values.append(json.dumps(updates["custom_tags"]))

                if "user_notes" in updates:
                    update_fields.append("user_notes = ?")
                    update_values.append(updates["user_notes"])

                update_values.append(record_id)

                cursor.execute(f'''
                    UPDATE user_playbook_meta
                    SET {", ".join(update_fields)}
                    WHERE id = ?
                ''', update_values)
            else:
                # Create new record
                record_id = str(uuid.uuid4())
                favorite = 1 if updates.get("favorite", False) else 0
                use_count = updates.get("use_count", 0)
                if "increment_use_count" in updates and updates["increment_use_count"]:
                    use_count = 1

                cursor.execute('''
                    INSERT INTO user_playbook_meta (
                        id, profile_id, playbook_code, favorite, use_count,
                        last_used_at, custom_tags, user_notes, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    record_id,
                    profile_id,
                    playbook_code,
                    favorite,
                    use_count,
                    now if use_count > 0 else None,
                    json.dumps(updates.get("custom_tags", [])),
                    updates.get("user_notes"),
                    now,
                    now
                ))

            logger.info(f"Updated user meta for playbook {playbook_code} (profile: {profile_id})")

            # Return updated meta
            return self.get_user_meta(profile_id, playbook_code) or {
                "favorite": False,
                "use_count": 0,
                "last_used_at": None,
                "custom_tags": [],
                "user_notes": None
            }

    def list_favorites(self, profile_id: str) -> list[str]:
        """
        List favorite playbook codes for a user

        Args:
            profile_id: User profile ID

        Returns:
            List of playbook codes
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT playbook_code
                FROM user_playbook_meta
                WHERE profile_id = ? AND favorite = 1
                ORDER BY updated_at DESC
            ''', (profile_id,))

            return [row[0] for row in cursor.fetchall()]

    def list_recent(self, profile_id: str, limit: int = 20) -> list[str]:
        """
        List recently used playbook codes for a user

        Args:
            profile_id: User profile ID
            limit: Maximum number of results

        Returns:
            List of playbook codes (ordered by last_used_at DESC)
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT playbook_code
                FROM user_playbook_meta
                WHERE profile_id = ? AND last_used_at IS NOT NULL
                ORDER BY last_used_at DESC
                LIMIT ?
            ''', (profile_id, limit))

            return [row[0] for row in cursor.fetchall()]

