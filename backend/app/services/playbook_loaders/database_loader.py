"""
Playbook Database Loader
Loads playbooks from PostgreSQL database
"""

import json
import logging
from typing import List, Optional, Any, Dict
from datetime import datetime

from sqlalchemy import text

from backend.app.models.playbook import Playbook, PlaybookMetadata
from backend.app.services.stores.postgres_base import PostgresStoreBase

logger = logging.getLogger(__name__)


class PlaybookDatabaseLoader(PostgresStoreBase):
    """Loads playbooks from PostgreSQL database"""

    @staticmethod
    def _deserialize_json(value: Any, default: Any):
        if value is None:
            return default
        if isinstance(value, (dict, list)):
            return value
        if isinstance(value, str):
            if not value.strip():
                return default
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return default
        return default

    @staticmethod
    def _to_datetime(value: Any) -> datetime:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            return datetime.fromisoformat(value)
        raise ValueError(f"Unsupported datetime value: {value}")

    @classmethod
    def _row_to_playbook(cls, row: Dict[str, Any]) -> Playbook:
        """Convert database row to Playbook"""
        return Playbook(
            metadata=PlaybookMetadata(
                playbook_code=row["playbook_code"],
                version=row.get("version"),
                locale=row.get("locale") or "zh-TW",
                name=row.get("name") or "",
                description=row.get("description") or "",
                tags=cls._deserialize_json(row.get("tags"), []),
                entry_agent_type=row.get("entry_agent_type"),
                onboarding_task=row.get("onboarding_task"),
                icon=row.get("icon"),
                required_tools=cls._deserialize_json(row.get("required_tools"), []),
                scope=cls._deserialize_json(row.get("scope"), None),
                owner=cls._deserialize_json(row.get("owner"), None),
                created_at=cls._to_datetime(row.get("created_at")),
                updated_at=cls._to_datetime(row.get("updated_at")),
            ),
            sop_content=row.get("sop_content") or "",
            user_notes=row.get("user_notes"),
        )

    @classmethod
    def load_playbooks_from_db(
        cls,
        db_path: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> List[Playbook]:
        """List all playbooks from database, optionally filtered by tags"""
        loader = cls()
        with loader.get_connection() as conn:
            if tags:
                tag_conditions = []
                params: Dict[str, Any] = {}
                for idx, tag in enumerate(tags):
                    key = f"tag_{idx}"
                    tag_conditions.append(f"tags::text LIKE :{key}")
                    params[key] = f'%"{tag}"%'
                query = (
                    "SELECT * FROM playbooks WHERE "
                    + " OR ".join(tag_conditions)
                    + " ORDER BY name"
                )
                rows = conn.execute(text(query), params).mappings().all()
            else:
                rows = conn.execute(
                    text("SELECT * FROM playbooks ORDER BY name")
                ).mappings().all()

        return [cls._row_to_playbook(dict(row)) for row in rows]
