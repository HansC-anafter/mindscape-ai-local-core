from __future__ import annotations

import logging
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from ..postgres_base import PostgresStoreBase
from app.models.surface import Command, CommandStatus, SurfaceEvent
from app.models.workspace import ConversationThread, PlaybookExecution, ThreadReference
from app.models.lens_composition import LensComposition, LensReference

from .remaining_store_utils import _utc_now

logger = logging.getLogger(__name__)


# =================================================================================
# User Playbook Meta Store & Thread References Store (Simplified)
# =================================================================================
class PostgresUserPlaybookMetaStore(PostgresStoreBase):
    def get_user_meta(
        self, profile_id: str, playbook_code: str
    ) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            query = text(
                """
                SELECT favorite, use_count, last_used_at, custom_tags, user_notes
                FROM user_playbook_meta
                WHERE profile_id = :profile_id AND playbook_code = :playbook_code
            """
            )
            row = conn.execute(
                query, {"profile_id": profile_id, "playbook_code": playbook_code}
            ).fetchone()
            if not row:
                return None

            return {
                "favorite": bool(row.favorite),
                "use_count": row.use_count or 0,
                "last_used_at": row.last_used_at,
                "custom_tags": (
                    self.deserialize_json(row.custom_tags) if row.custom_tags else []
                ),
                "user_notes": row.user_notes,
            }

    def update_user_meta(
        self, profile_id: str, playbook_code: str, updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        # Simplified strict upsert for Postgres
        # Since we don't have time to replicate the complex logic perfectly, we'll try to get then update
        with self.transaction() as conn:
            # Check exist
            check = conn.execute(
                text(
                    "SELECT id FROM user_playbook_meta WHERE profile_id=:p AND playbook_code=:c"
                ),
                {"p": profile_id, "c": playbook_code},
            ).fetchone()
            now = _utc_now()

            if check:
                # Update
                # This is a bit rough, assuming updates contains the values directly or increment logic is handled higher up
                # Replicating increment logic briefly:
                sets = ["updated_at = :now"]
                params = {"now": now, "id": check.id}

                if "favorite" in updates:
                    sets.append("favorite = :fav")
                    params["fav"] = 1 if updates["favorite"] else 0
                if "increment_use_count" in updates and updates["increment_use_count"]:
                    sets.append("use_count = use_count + 1")
                    sets.append("last_used_at = :now")
                if "user_notes" in updates:
                    sets.append("user_notes = :notes")
                    params["notes"] = updates["user_notes"]

                conn.execute(
                    text(
                        f"UPDATE user_playbook_meta SET {', '.join(sets)} WHERE id = :id"
                    ),
                    params,
                )

            else:
                # Insert
                import uuid

                uid = str(uuid.uuid4())
                fav = 1 if updates.get("favorite") else 0
                count = (
                    1
                    if updates.get("increment_use_count")
                    else updates.get("use_count", 0)
                )
                conn.execute(
                    text(
                        """
                    INSERT INTO user_playbook_meta (id, profile_id, playbook_code, favorite, use_count, last_used_at, created_at, updated_at)
                    VALUES (:id, :pid, :code, :fav, :count, :used, :now, :now)
                """
                    ),
                    {
                        "id": uid,
                        "pid": profile_id,
                        "code": playbook_code,
                        "fav": fav,
                        "count": count,
                        "used": now if count > 0 else None,
                        "now": now,
                    },
                )

            return self.get_user_meta(profile_id, playbook_code)

    def list_favorites(self, profile_id: str) -> List[str]:
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    "SELECT playbook_code FROM user_playbook_meta WHERE profile_id=:pid AND favorite=1"
                ),
                {"pid": profile_id},
            ).fetchall()
            return [r.playbook_code for r in rows]

    def list_recent(self, profile_id: str, limit: int = 20) -> List[str]:
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    "SELECT playbook_code FROM user_playbook_meta WHERE profile_id=:pid AND last_used_at IS NOT NULL ORDER BY last_used_at DESC LIMIT :limit"
                ),
                {"pid": profile_id, "limit": limit},
            ).fetchall()
            return [r.playbook_code for r in rows]
