"""
Playbook Database Loader
Loads playbooks from SQLite database
"""

import json
import sqlite3
import logging
from typing import List, Optional
from contextlib import contextmanager
from datetime import datetime

from backend.app.models.playbook import Playbook, PlaybookMetadata

logger = logging.getLogger(__name__)


class PlaybookDatabaseLoader:
    """Loads playbooks from database"""

    @staticmethod
    @contextmanager
    def _get_connection(db_path: str):
        """Get database connection with proper cleanup"""
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    @staticmethod
    def _row_to_playbook(row) -> Playbook:
        """Convert database row to Playbook"""
        return Playbook(
            metadata=PlaybookMetadata(
                playbook_code=row['playbook_code'],
                version=row['version'],
                locale=row.get('locale', 'zh-TW'),
                name=row['name'],
                description=row['description'] or '',
                tags=json.loads(row['tags'] or '[]'),
                entry_agent_type=row.get('entry_agent_type'),
                onboarding_task=row.get('onboarding_task'),
                icon=row.get('icon'),
                required_tools=json.loads(row.get('required_tools') or '[]'),
                scope=json.loads(row['scope']) if row.get('scope') else None,
                owner=json.loads(row['owner']) if row.get('owner') else None,
                created_at=datetime.fromisoformat(row['created_at']),
                updated_at=datetime.fromisoformat(row['updated_at'])
            ),
            sop_content=row['sop_content'] or '',
            user_notes=row['user_notes']
        )

    @staticmethod
    def load_playbooks_from_db(db_path: str, tags: Optional[List[str]] = None) -> List[Playbook]:
        """List all playbooks from database, optionally filtered by tags"""
        with PlaybookDatabaseLoader._get_connection(db_path) as conn:
            cursor = conn.cursor()

            if tags:
                query = 'SELECT * FROM playbooks WHERE '
                conditions = []
                params = []
                for tag in tags:
                    conditions.append('tags LIKE ?')
                    params.append(f'%"{tag}"%')
                query += ' OR '.join(conditions)
                query += ' ORDER BY name'
                cursor.execute(query, params)
            else:
                cursor.execute('SELECT * FROM playbooks ORDER BY name')

            rows = cursor.fetchall()
            return [PlaybookDatabaseLoader._row_to_playbook(row) for row in rows]

