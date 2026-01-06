"""
Saved Views storage service
"""

import uuid
import json
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any

from .stores.base import StoreBase

logger = logging.getLogger(__name__)


class SavedViewsStore(StoreBase):
    """
    Saved Views storage

    Table structure:
    CREATE TABLE saved_views (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        name TEXT NOT NULL,
        scope TEXT NOT NULL DEFAULT 'global',
        view TEXT NOT NULL DEFAULT 'my_work',
        tab TEXT NOT NULL DEFAULT 'inbox',
        filters TEXT DEFAULT '{}',
        sort_by TEXT DEFAULT 'auto',
        sort_order TEXT DEFAULT 'desc',
        is_default INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE INDEX idx_saved_views_user ON saved_views(user_id);
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._ensure_table()

    def _ensure_table(self):
        """Ensure table exists"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS saved_views (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    scope TEXT NOT NULL DEFAULT 'global',
                    view TEXT NOT NULL DEFAULT 'my_work',
                    tab TEXT NOT NULL DEFAULT 'inbox',
                    filters TEXT DEFAULT '{}',
                    sort_by TEXT DEFAULT 'auto',
                    sort_order TEXT DEFAULT 'desc',
                    is_default INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_saved_views_user ON saved_views(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_saved_views_user_tab ON saved_views(user_id, tab)")
            conn.commit()

    def list_by_user(self, user_id: str) -> List[Dict[str, Any]]:
        """List all Saved Views for a user"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM saved_views WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,)
            )
            rows = cursor.fetchall()
            return [self._row_to_dict(row) for row in rows]

    def get(self, view_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Get a single Saved View"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM saved_views WHERE id = ? AND user_id = ?",
                (view_id, user_id)
            )
            row = cursor.fetchone()
            return self._row_to_dict(row) if row else None

    def create(self, user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create Saved View"""
        view_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO saved_views
                (id, user_id, name, scope, view, tab, filters, sort_by, sort_order, is_default, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                view_id,
                user_id,
                data.get("name", "Untitled"),
                data.get("scope", "global"),
                data.get("view", "my_work"),
                data.get("tab", "inbox"),
                json.dumps(data.get("filters", {})),
                data.get("sort_by", "auto"),
                data.get("sort_order", "desc"),
                1 if data.get("is_default") else 0,
                now,
                now,
            ))

        return self.get(view_id, user_id)

    def delete(self, view_id: str, user_id: str) -> bool:
        """Delete Saved View"""
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM saved_views WHERE id = ? AND user_id = ?",
                (view_id, user_id)
            )
            return cursor.rowcount > 0

    def _row_to_dict(self, row) -> Dict[str, Any]:
        """Convert database row to dictionary"""
        return {
            "id": row["id"],
            "name": row["name"],
            "scope": row["scope"],
            "view": row["view"],
            "tab": row["tab"],
            "filters": json.loads(row["filters"] or "{}"),
            "sort_by": row["sort_by"],
            "sort_order": row["sort_order"],
            "is_default": bool(row["is_default"]),
            "created_at": datetime.fromisoformat(row["created_at"]),
            "updated_at": datetime.fromisoformat(row["updated_at"]),
        }
