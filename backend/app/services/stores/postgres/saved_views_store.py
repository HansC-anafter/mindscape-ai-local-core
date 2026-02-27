"""PostgreSQL implementation of SavedViewsStore."""

import json
import uuid
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from sqlalchemy import text
from backend.app.services.stores.postgres_base import PostgresStoreBase

logger = logging.getLogger(__name__)


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


class PostgresSavedViewsStore(PostgresStoreBase):
    """Postgres implementation of SavedViewsStore."""

    def list_by_user(self, user_id: str) -> List[Dict[str, Any]]:
        """List all Saved Views for a user."""
        query = text(
            "SELECT * FROM saved_views WHERE user_id = :user_id "
            "ORDER BY created_at DESC"
        )
        with self.get_connection() as conn:
            result = conn.execute(query, {"user_id": user_id})
            rows = result.fetchall()
            return [self._row_to_dict(row) for row in rows]

    def get(self, view_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Get a single Saved View."""
        query = text("SELECT * FROM saved_views WHERE id = :id AND user_id = :user_id")
        with self.get_connection() as conn:
            result = conn.execute(query, {"id": view_id, "user_id": user_id})
            row = result.fetchone()
            return self._row_to_dict(row) if row else None

    def create(self, user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create Saved View."""
        view_id = str(uuid.uuid4())
        now = _utc_now()

        query = text(
            """
            INSERT INTO saved_views (
                id, user_id, name, scope, view, tab, filters,
                sort_by, sort_order, is_default, created_at, updated_at
            ) VALUES (
                :id, :user_id, :name, :scope, :view, :tab, :filters,
                :sort_by, :sort_order, :is_default, :created_at, :updated_at
            )
        """
        )
        with self.transaction() as conn:
            conn.execute(
                query,
                {
                    "id": view_id,
                    "user_id": user_id,
                    "name": data.get("name", "Untitled"),
                    "scope": data.get("scope", "global"),
                    "view": data.get("view", "my_work"),
                    "tab": data.get("tab", "inbox"),
                    "filters": json.dumps(data.get("filters", {})),
                    "sort_by": data.get("sort_by", "auto"),
                    "sort_order": data.get("sort_order", "desc"),
                    "is_default": data.get("is_default", False),
                    "created_at": now,
                    "updated_at": now,
                },
            )

        return self.get(view_id, user_id)

    def delete(self, view_id: str, user_id: str) -> bool:
        """Delete Saved View."""
        query = text("DELETE FROM saved_views WHERE id = :id AND user_id = :user_id")
        with self.transaction() as conn:
            result = conn.execute(query, {"id": view_id, "user_id": user_id})
            return result.rowcount > 0

    def _row_to_dict(self, row) -> Dict[str, Any]:
        """Convert database row to dictionary."""
        return {
            "id": row.id,
            "name": row.name,
            "scope": row.scope,
            "view": row.view,
            "tab": row.tab,
            "filters": json.loads(row.filters or "{}"),
            "sort_by": row.sort_by,
            "sort_order": row.sort_order,
            "is_default": bool(row.is_default),
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
