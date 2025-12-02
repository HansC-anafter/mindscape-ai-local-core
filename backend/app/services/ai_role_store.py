"""
AI Role Store Service
Manages persistent storage for AI role configurations
"""

import sqlite3
import json
from datetime import datetime
from typing import List, Optional, Dict, Any
from pathlib import Path

from backend.app.models.ai_role import AIRoleConfig, AIRoleUsageRecord


class AIRoleStore:
    """
    Store for AI role configurations

    Manages which AI roles a user has enabled and their configurations.
    """

    def __init__(self, db_path: str = "data/my_agent_console.db"):
        self.db_path = db_path
        self._ensure_tables()

    def _ensure_tables(self):
        """Create tables if they don't exist"""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # AI role configurations table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ai_role_configs (
                id TEXT PRIMARY KEY,
                profile_id TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                agent_type TEXT NOT NULL,
                icon TEXT DEFAULT '🤖',
                playbooks TEXT DEFAULT '[]',
                suggested_tasks TEXT DEFAULT '[]',
                tools TEXT DEFAULT '[]',
                mindscape_profile_override TEXT,
                usage_count INTEGER DEFAULT 0,
                last_used_at TEXT,
                is_enabled INTEGER DEFAULT 1,
                is_custom INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                x_platform TEXT,
                FOREIGN KEY (profile_id) REFERENCES mindscape_profiles(id)
            )
        """)

        # AI role usage records table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ai_role_usage_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role_id TEXT NOT NULL,
                profile_id TEXT NOT NULL,
                execution_id TEXT NOT NULL,
                task TEXT NOT NULL,
                used_at TEXT NOT NULL,
                FOREIGN KEY (role_id) REFERENCES ai_role_configs(id),
                FOREIGN KEY (profile_id) REFERENCES mindscape_profiles(id)
            )
        """)

        # Role-capability mappings table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS role_capabilities (
                role_id TEXT NOT NULL,
                capability_id TEXT NOT NULL,
                profile_id TEXT NOT NULL,
                label TEXT NOT NULL,
                blurb TEXT NOT NULL,
                entry_prompt TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (role_id, capability_id, profile_id),
                FOREIGN KEY (role_id) REFERENCES ai_role_configs(id),
                FOREIGN KEY (profile_id) REFERENCES mindscape_profiles(id)
            )
        """)

        # Indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_ai_role_configs_profile
            ON ai_role_configs(profile_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_ai_role_configs_enabled
            ON ai_role_configs(is_enabled)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_ai_role_usage_profile
            ON ai_role_usage_records(profile_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_role_capabilities_role
            ON role_capabilities(role_id, profile_id)
        """)

        conn.commit()
        conn.close()

    def save_role_config(self, role: AIRoleConfig) -> AIRoleConfig:
        """Save or update an AI role configuration"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        role.updated_at = datetime.utcnow()

        cursor.execute("""
            INSERT OR REPLACE INTO ai_role_configs (
                id, profile_id, name, description, agent_type, icon,
                playbooks, suggested_tasks, tools, mindscape_profile_override,
                usage_count, last_used_at, is_enabled, is_custom,
                created_at, updated_at, x_platform
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            role.id,
            role.profile_id,
            role.name,
            role.description,
            role.agent_type,
            role.icon,
            json.dumps(role.playbooks),
            json.dumps(role.suggested_tasks),
            json.dumps(role.tools),
            json.dumps(role.mindscape_profile_override) if role.mindscape_profile_override else None,
            role.usage_count,
            role.last_used_at.isoformat() if role.last_used_at else None,
            1 if role.is_enabled else 0,
            1 if role.is_custom else 0,
            role.created_at.isoformat(),
            role.updated_at.isoformat(),
            json.dumps(role.x_platform) if role.x_platform else None,
        ))

        conn.commit()
        conn.close()

        return role

    def get_role_config(self, role_id: str, profile_id: str) -> Optional[AIRoleConfig]:
        """Get a specific AI role configuration"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM ai_role_configs
            WHERE id = ? AND profile_id = ?
        """, (role_id, profile_id))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return self._row_to_role_config(row)

    def get_enabled_roles(self, profile_id: str) -> List[AIRoleConfig]:
        """Get all enabled AI roles for a profile"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM ai_role_configs
            WHERE profile_id = ? AND is_enabled = 1
            ORDER BY usage_count DESC, name ASC
        """, (profile_id,))

        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_role_config(row) for row in rows]

    def get_all_roles(self, profile_id: str) -> List[AIRoleConfig]:
        """Get all AI roles (enabled and disabled) for a profile"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM ai_role_configs
            WHERE profile_id = ?
            ORDER BY usage_count DESC, name ASC
        """, (profile_id,))

        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_role_config(row) for row in rows]

    def record_role_usage(self, role_id: str, profile_id: str, execution_id: str, task: str):
        """Record that a role was used"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Update usage count and last_used_at
        cursor.execute("""
            UPDATE ai_role_configs
            SET usage_count = usage_count + 1,
                last_used_at = ?
            WHERE id = ? AND profile_id = ?
        """, (datetime.utcnow().isoformat(), role_id, profile_id))

        # Insert usage record
        cursor.execute("""
            INSERT INTO ai_role_usage_records (
                role_id, profile_id, execution_id, task, used_at
            ) VALUES (?, ?, ?, ?, ?)
        """, (role_id, profile_id, execution_id, task, datetime.utcnow().isoformat()))

        conn.commit()
        conn.close()

    def delete_role_config(self, role_id: str, profile_id: str) -> bool:
        """Delete an AI role configuration"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            DELETE FROM ai_role_configs
            WHERE id = ? AND profile_id = ?
        """, (role_id, profile_id))

        deleted = cursor.rowcount > 0
        conn.commit()
        conn.close()

        return deleted

    def _row_to_role_config(self, row: sqlite3.Row) -> AIRoleConfig:
        """Convert database row to AIRoleConfig model"""
        return AIRoleConfig(
            id=row["id"],
            profile_id=row["profile_id"],
            name=row["name"],
            description=row["description"],
            agent_type=row["agent_type"],
            icon=row["icon"],
            playbooks=json.loads(row["playbooks"]) if row["playbooks"] else [],
            suggested_tasks=json.loads(row["suggested_tasks"]) if row["suggested_tasks"] else [],
            tools=json.loads(row["tools"]) if row["tools"] else [],
            mindscape_profile_override=json.loads(row["mindscape_profile_override"]) if row["mindscape_profile_override"] else None,
            usage_count=row["usage_count"],
            last_used_at=datetime.fromisoformat(row["last_used_at"]) if row["last_used_at"] else None,
            is_enabled=bool(row["is_enabled"]),
            is_custom=bool(row["is_custom"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            x_platform=json.loads(row["x_platform"]) if row["x_platform"] else None,
        )
