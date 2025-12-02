"""
Playbook Store
Local storage for Playbook library
"""

import os
import json
import sqlite3
from datetime import datetime
from typing import List, Optional, Dict, Any
from contextlib import contextmanager
import logging

from backend.app.models.playbook import Playbook, PlaybookMetadata, PlaybookAssociation

logger = logging.getLogger(__name__)


class PlaybookStore:
    """Local SQLite-based Playbook store"""

    def __init__(self, db_path: str = None):
        if db_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
            data_dir = os.path.join(base_dir, "data")
            os.makedirs(data_dir, exist_ok=True)
            db_path = os.path.join(data_dir, "mindscape.db")

        self.db_path = db_path
        self._init_db()

    @contextmanager
    def get_connection(self):
        """Get database connection with proper cleanup"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        """Initialize Playbook tables"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Playbooks table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS playbooks (
                    playbook_code TEXT NOT NULL,
                    version TEXT NOT NULL DEFAULT '1.0.0',
                    locale TEXT NOT NULL DEFAULT 'zh-TW',
                    name TEXT NOT NULL,
                    description TEXT,
                    tags TEXT,
                    entry_agent_type TEXT,
                    onboarding_task TEXT,
                    icon TEXT,
                    required_tools TEXT,
                    scope TEXT,
                    owner TEXT,
                    sop_content TEXT,
                    user_notes TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (playbook_code, version)
                )
            ''')

            # User playbook meta table (personal化)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_playbook_meta (
                    profile_id TEXT NOT NULL,
                    playbook_code TEXT NOT NULL,
                    favorite BOOLEAN DEFAULT 0,
                    hidden BOOLEAN DEFAULT 0,
                    custom_tags TEXT,
                    last_used_at TEXT,
                    use_count INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (profile_id, playbook_code)
                )
            ''')

            # Personalized playbooks table (个人化变体)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS personalized_playbooks (
                    id TEXT PRIMARY KEY,
                    profile_id TEXT NOT NULL,
                    base_playbook_code TEXT NOT NULL,
                    base_version TEXT NOT NULL,
                    variant_name TEXT NOT NULL,
                    variant_description TEXT,
                    personalized_sop_content TEXT,
                    skip_steps TEXT,
                    custom_checklist TEXT,
                    execution_params TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    is_default BOOLEAN DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (profile_id, base_playbook_code) REFERENCES user_playbook_meta(profile_id, playbook_code)
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_personalized_playbooks_profile ON personalized_playbooks(profile_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_personalized_playbooks_base ON personalized_playbooks(base_playbook_code)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_personalized_playbooks_active ON personalized_playbooks(profile_id, base_playbook_code, is_active)')

            # Intent-Playbook associations
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS intent_playbook_associations (
                    intent_id TEXT NOT NULL,
                    playbook_code TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (intent_id, playbook_code),
                    FOREIGN KEY (intent_id) REFERENCES intents (id)
                )
            ''')

            # Create indexes
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_playbooks_code ON playbooks(playbook_code)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_playbooks_locale ON playbooks(locale)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_playbooks_onboarding ON playbooks(onboarding_task)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_meta_profile ON user_playbook_meta(profile_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_intent_playbook_intent ON intent_playbook_associations(intent_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_intent_playbook_playbook ON intent_playbook_associations(playbook_code)')

            conn.commit()

    def create_playbook(self, playbook: Playbook) -> Playbook:
        """Create a new playbook"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO playbooks (
                    playbook_code, version, locale, name, description, tags,
                    entry_agent_type, onboarding_task, icon, required_tools,
                    scope, owner, sop_content, user_notes,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                playbook.metadata.playbook_code,
                playbook.metadata.version,
                playbook.metadata.locale,
                playbook.metadata.name,
                playbook.metadata.description,
                json.dumps(playbook.metadata.tags),
                playbook.metadata.entry_agent_type,
                playbook.metadata.onboarding_task,
                playbook.metadata.icon,
                json.dumps(playbook.metadata.required_tools),
                json.dumps(playbook.metadata.scope) if playbook.metadata.scope else None,
                json.dumps(playbook.metadata.owner) if playbook.metadata.owner else None,
                playbook.sop_content,
                playbook.user_notes,
                playbook.metadata.created_at.isoformat(),
                playbook.metadata.updated_at.isoformat()
            ))
            conn.commit()
            return playbook

    def get_playbook(self, playbook_code: str, version: Optional[str] = None) -> Optional[Playbook]:
        """Get playbook by code and version (latest if version not specified)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if version:
                cursor.execute('SELECT * FROM playbooks WHERE playbook_code = ? AND version = ?',
                             (playbook_code, version))
            else:
                cursor.execute('''
                    SELECT * FROM playbooks
                    WHERE playbook_code = ?
                    ORDER BY version DESC
                    LIMIT 1
                ''', (playbook_code,))

            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_playbook(row)

    def list_playbooks(self, tags: Optional[List[str]] = None) -> List[Playbook]:
        """List all playbooks, optionally filtered by tags"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            if tags:
                # Filter by tags (simple contains check)
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
            return [self._row_to_playbook(row) for row in rows]

    def update_playbook(self, playbook_code: str, updates: Dict[str, Any]) -> Optional[Playbook]:
        """Update playbook"""
        playbook = self.get_playbook(playbook_code)
        if not playbook:
            return None

        # Apply updates
        if 'name' in updates:
            playbook.metadata.name = updates['name']
        if 'description' in updates:
            playbook.metadata.description = updates['description']
        if 'tags' in updates:
            playbook.metadata.tags = updates['tags']
        if 'sop_content' in updates:
            playbook.sop_content = updates['sop_content']
        if 'user_notes' in updates:
            playbook.user_notes = updates['user_notes']

        playbook.metadata.updated_at = datetime.utcnow()

        # Save updated playbook
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE playbooks
                SET name = ?, description = ?, tags = ?, sop_content = ?,
                    user_notes = ?, updated_at = ?
                WHERE playbook_code = ? AND version = ?
            ''', (
                playbook.metadata.name,
                playbook.metadata.description,
                json.dumps(playbook.metadata.tags),
                playbook.sop_content,
                playbook.user_notes,
                playbook.metadata.updated_at.isoformat(),
                playbook.metadata.playbook_code,
                playbook.metadata.version
            ))
            conn.commit()
            return playbook

    def associate_intent_playbook(self, intent_id: str, playbook_code: str) -> PlaybookAssociation:
        """Associate an intent with a playbook"""
        association = PlaybookAssociation(
            intent_id=intent_id,
            playbook_code=playbook_code
        )

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO intent_playbook_associations
                (intent_id, playbook_code, created_at)
                VALUES (?, ?, ?)
            ''', (
                intent_id,
                playbook_code,
                association.created_at.isoformat()
            ))
            conn.commit()
            return association

    def get_intent_playbooks(self, intent_id: str) -> List[str]:
        """Get playbook codes associated with an intent"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT playbook_code FROM intent_playbook_associations
                WHERE intent_id = ?
                ORDER BY created_at
            ''', (intent_id,))
            rows = cursor.fetchall()
            return [row['playbook_code'] for row in rows]

    def get_playbook_intents(self, playbook_code: str) -> List[str]:
        """Get intent IDs associated with a playbook"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT intent_id FROM intent_playbook_associations
                WHERE playbook_code = ?
                ORDER BY created_at
            ''', (playbook_code,))
            rows = cursor.fetchall()
            return [row['intent_id'] for row in rows]

    def remove_intent_playbook_association(self, intent_id: str, playbook_code: str) -> bool:
        """Remove association between intent and playbook"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM intent_playbook_associations
                WHERE intent_id = ? AND playbook_code = ?
            ''', (intent_id, playbook_code))
            conn.commit()
            return cursor.rowcount > 0

    def _row_to_playbook(self, row) -> Playbook:
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

    def get_user_meta(self, profile_id: str, playbook_code: str) -> Optional[Dict]:
        """Get user's meta for a playbook"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM user_playbook_meta
                WHERE profile_id = ? AND playbook_code = ?
            ''', (profile_id, playbook_code))
            row = cursor.fetchone()
            if not row:
                return None
            return dict(row)

    def update_user_meta(self, profile_id: str, playbook_code: str,
                        updates: Dict[str, Any]) -> Dict:
        """Update or create user meta"""
        existing = self.get_user_meta(profile_id, playbook_code)
        now = datetime.utcnow().isoformat()

        if existing:
            # Update
            fields = []
            values = []
            for key, value in updates.items():
                if key in ['favorite', 'hidden', 'custom_tags', 'last_used_at', 'use_count']:
                    fields.append(f"{key} = ?")
                    if key == 'custom_tags':
                        values.append(json.dumps(value) if value else None)
                    else:
                        values.append(value)

            if fields:
                fields.append("updated_at = ?")
                values.append(now)
                values.extend([profile_id, playbook_code])

                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(f'''
                        UPDATE user_playbook_meta
                        SET {", ".join(fields)}
                        WHERE profile_id = ? AND playbook_code = ?
                    ''', values)
                    conn.commit()
        else:
            # Create
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO user_playbook_meta (
                        profile_id, playbook_code, favorite, hidden,
                        custom_tags, last_used_at, use_count,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    profile_id,
                    playbook_code,
                    updates.get('favorite', False),
                    updates.get('hidden', False),
                    json.dumps(updates.get('custom_tags', [])),
                    updates.get('last_used_at'),
                    updates.get('use_count', 0),
                    now,
                    now
                ))
                conn.commit()

        return self.get_user_meta(profile_id, playbook_code)

    def increment_use_count(self, profile_id: str, playbook_code: str):
        """Increment use count when playbook is used"""
        meta = self.get_user_meta(profile_id, playbook_code)
        current_count = meta['use_count'] if meta else 0
        self.update_user_meta(profile_id, playbook_code, {
            'use_count': current_count + 1,
            'last_used_at': datetime.utcnow().isoformat()
        })

    # ==================== Personalized Playbook Variants ====================

    def create_personalized_variant(self, variant_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a personalized Playbook variant"""
        import uuid
        variant_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO personalized_playbooks (
                    id, profile_id, base_playbook_code, base_version,
                    variant_name, variant_description, personalized_sop_content,
                    skip_steps, custom_checklist, execution_params,
                    is_active, is_default, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                variant_id,
                variant_data['profile_id'],
                variant_data['base_playbook_code'],
                variant_data['base_version'],
                variant_data['variant_name'],
                variant_data.get('variant_description'),
                variant_data.get('personalized_sop_content'),
                json.dumps(variant_data.get('skip_steps', [])),
                json.dumps(variant_data.get('custom_checklist', [])),
                json.dumps(variant_data.get('execution_params', {})),
                variant_data.get('is_active', True),
                variant_data.get('is_default', False),
                now,
                now
            ))
            conn.commit()

        # If this is set as default, unset other defaults
        if variant_data.get('is_default'):
            self._unset_other_defaults(variant_data['profile_id'], variant_data['base_playbook_code'], variant_id)

        return self.get_personalized_variant(variant_id)

    def get_personalized_variant(self, variant_id: str) -> Optional[Dict[str, Any]]:
        """Get a personalized variant by ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM personalized_playbooks WHERE id = ?
            ''', (variant_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_variant(row)

    def list_personalized_variants(
        self,
        profile_id: str,
        base_playbook_code: Optional[str] = None,
        active_only: bool = False
    ) -> List[Dict[str, Any]]:
        """List personalized variants for a user"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = 'SELECT * FROM personalized_playbooks WHERE profile_id = ?'
            params = [profile_id]

            if base_playbook_code:
                query += ' AND base_playbook_code = ?'
                params.append(base_playbook_code)

            if active_only:
                query += ' AND is_active = 1'

            query += ' ORDER BY is_default DESC, created_at DESC'

            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [self._row_to_variant(row) for row in rows]

    def get_default_variant(
        self,
        profile_id: str,
        base_playbook_code: str
    ) -> Optional[Dict[str, Any]]:
        """Get the default variant for a Playbook"""
        variants = self.list_personalized_variants(profile_id, base_playbook_code, active_only=True)
        for variant in variants:
            if variant.get('is_default'):
                return variant
        return None

    def update_personalized_variant(
        self,
        variant_id: str,
        updates: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Update a personalized variant"""
        now = datetime.utcnow().isoformat()
        fields = []
        values = []

        for key, value in updates.items():
            if key in ['variant_name', 'variant_description', 'personalized_sop_content', 'is_active', 'is_default']:
                fields.append(f"{key} = ?")
                values.append(value)
            elif key == 'skip_steps':
                fields.append("skip_steps = ?")
                values.append(json.dumps(value))
            elif key == 'custom_checklist':
                fields.append("custom_checklist = ?")
                values.append(json.dumps(value))
            elif key == 'execution_params':
                fields.append("execution_params = ?")
                values.append(json.dumps(value))

        if not fields:
            return self.get_personalized_variant(variant_id)

        fields.append("updated_at = ?")
        values.append(now)
        values.append(variant_id)

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f'''
                UPDATE personalized_playbooks
                SET {", ".join(fields)}
                WHERE id = ?
            ''', values)
            conn.commit()

        # If setting as default, unset other defaults
        if updates.get('is_default'):
            variant = self.get_personalized_variant(variant_id)
            if variant:
                self._unset_other_defaults(
                    variant['profile_id'],
                    variant['base_playbook_code'],
                    variant_id
                )

        return self.get_personalized_variant(variant_id)

    def delete_personalized_variant(self, variant_id: str) -> bool:
        """Delete a personalized variant"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM personalized_playbooks WHERE id = ?', (variant_id,))
            conn.commit()
            return cursor.rowcount > 0

    def _unset_other_defaults(
        self,
        profile_id: str,
        base_playbook_code: str,
        exclude_variant_id: str
    ):
        """Unset is_default for other variants"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE personalized_playbooks
                SET is_default = 0, updated_at = ?
                WHERE profile_id = ? AND base_playbook_code = ? AND id != ?
            ''', (datetime.utcnow().isoformat(), profile_id, base_playbook_code, exclude_variant_id))
            conn.commit()

    def _row_to_variant(self, row) -> Dict[str, Any]:
        """Convert database row to variant dict"""
        return {
            'id': row['id'],
            'profile_id': row['profile_id'],
            'base_playbook_code': row['base_playbook_code'],
            'base_version': row['base_version'],
            'variant_name': row['variant_name'],
            'variant_description': row.get('variant_description'),
            'personalized_sop_content': row.get('personalized_sop_content'),
            'skip_steps': json.loads(row['skip_steps']) if row.get('skip_steps') else [],
            'custom_checklist': json.loads(row['custom_checklist']) if row.get('custom_checklist') else [],
            'execution_params': json.loads(row['execution_params']) if row.get('execution_params') else {},
            'is_active': bool(row.get('is_active', True)),
            'is_default': bool(row.get('is_default', False)),
            'created_at': row['created_at'],
            'updated_at': row['updated_at']
        }

