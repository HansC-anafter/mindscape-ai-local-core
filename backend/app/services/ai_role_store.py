"""
AI Role Store Service
Manages persistent storage for AI role configurations.
"""

import json
import logging
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
from typing import List, Optional

from sqlalchemy import text

from backend.app.models.ai_role import AIRoleConfig
from backend.app.services.stores.postgres_base import PostgresStoreBase

logger = logging.getLogger(__name__)


class AIRoleStore(PostgresStoreBase):
    """
    Store for AI role configurations.

    Manages which AI roles a user has enabled and their configurations.
    """

    def __init__(self, db_path: str = "data/my_agent_console.db", db_role: str = "core"):
        super().__init__(db_role=db_role)
        self.db_path = db_path
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        """Validate required tables exist (managed by Alembic migrations)."""
        required_tables = {
            "ai_role_configs",
            "ai_role_usage_records",
            "role_capabilities",
        }
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
                )
            ).fetchall()
            existing = {row.table_name for row in rows}

        missing = required_tables - existing
        if missing:
            missing_str = ", ".join(sorted(missing))
            raise RuntimeError(
                "Missing PostgreSQL tables: "
                f"{missing_str}. Run: alembic -c backend/alembic.ini upgrade head"
            )

    def save_role_config(self, role: AIRoleConfig) -> AIRoleConfig:
        """Save or update an AI role configuration."""
        role.updated_at = _utc_now()

        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO ai_role_configs (
                        id, profile_id, name, description, agent_type, icon,
                        playbooks, suggested_tasks, tools, mindscape_profile_override,
                        usage_count, last_used_at, is_enabled, is_custom,
                        created_at, updated_at, x_platform
                    ) VALUES (
                        :id, :profile_id, :name, :description, :agent_type, :icon,
                        :playbooks, :suggested_tasks, :tools, :mindscape_profile_override,
                        :usage_count, :last_used_at, :is_enabled, :is_custom,
                        :created_at, :updated_at, :x_platform
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        profile_id = EXCLUDED.profile_id,
                        name = EXCLUDED.name,
                        description = EXCLUDED.description,
                        agent_type = EXCLUDED.agent_type,
                        icon = EXCLUDED.icon,
                        playbooks = EXCLUDED.playbooks,
                        suggested_tasks = EXCLUDED.suggested_tasks,
                        tools = EXCLUDED.tools,
                        mindscape_profile_override = EXCLUDED.mindscape_profile_override,
                        usage_count = EXCLUDED.usage_count,
                        last_used_at = EXCLUDED.last_used_at,
                        is_enabled = EXCLUDED.is_enabled,
                        is_custom = EXCLUDED.is_custom,
                        created_at = EXCLUDED.created_at,
                        updated_at = EXCLUDED.updated_at,
                        x_platform = EXCLUDED.x_platform
                """
                ),
                {
                    "id": role.id,
                    "profile_id": role.profile_id,
                    "name": role.name,
                    "description": role.description,
                    "agent_type": role.agent_type,
                    "icon": role.icon,
                    "playbooks": self.serialize_json(role.playbooks),
                    "suggested_tasks": self.serialize_json(role.suggested_tasks),
                    "tools": self.serialize_json(role.tools),
                    "mindscape_profile_override": self.serialize_json(
                        role.mindscape_profile_override
                    )
                    if role.mindscape_profile_override
                    else None,
                    "usage_count": role.usage_count,
                    "last_used_at": role.last_used_at,
                    "is_enabled": role.is_enabled,
                    "is_custom": role.is_custom,
                    "created_at": role.created_at,
                    "updated_at": role.updated_at,
                    "x_platform": self.serialize_json(role.x_platform)
                    if role.x_platform
                    else None,
                },
            )

        return role

    def get_role_config(self, role_id: str, profile_id: str) -> Optional[AIRoleConfig]:
        """Get a specific AI role configuration."""
        with self.get_connection() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT * FROM ai_role_configs
                    WHERE id = :id AND profile_id = :profile_id
                """
                ),
                {"id": role_id, "profile_id": profile_id},
            ).fetchone()

        if not row:
            return None

        return self._row_to_role_config(row)

    def get_enabled_roles(self, profile_id: str) -> List[AIRoleConfig]:
        """Get all enabled AI roles for a profile."""
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT * FROM ai_role_configs
                    WHERE profile_id = :profile_id AND is_enabled = true
                    ORDER BY usage_count DESC, name ASC
                """
                ),
                {"profile_id": profile_id},
            ).fetchall()

        return [self._row_to_role_config(row) for row in rows]

    def get_all_roles(self, profile_id: str) -> List[AIRoleConfig]:
        """Get all AI roles (enabled and disabled) for a profile."""
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT * FROM ai_role_configs
                    WHERE profile_id = :profile_id
                    ORDER BY usage_count DESC, name ASC
                """
                ),
                {"profile_id": profile_id},
            ).fetchall()

        return [self._row_to_role_config(row) for row in rows]

    def record_role_usage(
        self, role_id: str, profile_id: str, execution_id: str, task: str
    ) -> None:
        """Record that a role was used."""
        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    UPDATE ai_role_configs
                    SET usage_count = usage_count + 1,
                        last_used_at = :last_used_at
                    WHERE id = :id AND profile_id = :profile_id
                """
                ),
                {
                    "last_used_at": _utc_now(),
                    "id": role_id,
                    "profile_id": profile_id,
                },
            )

            conn.execute(
                text(
                    """
                    INSERT INTO ai_role_usage_records (
                        role_id, profile_id, execution_id, task, used_at
                    ) VALUES (
                        :role_id, :profile_id, :execution_id, :task, :used_at
                    )
                """
                ),
                {
                    "role_id": role_id,
                    "profile_id": profile_id,
                    "execution_id": execution_id,
                    "task": task,
                    "used_at": _utc_now(),
                },
            )

    def delete_role_config(self, role_id: str, profile_id: str) -> bool:
        """Delete an AI role configuration."""
        with self.transaction() as conn:
            result = conn.execute(
                text(
                    """
                    DELETE FROM ai_role_configs
                    WHERE id = :id AND profile_id = :profile_id
                """
                ),
                {"id": role_id, "profile_id": profile_id},
            )
            return result.rowcount > 0

    def _row_to_role_config(self, row) -> AIRoleConfig:
        """Convert database row to AIRoleConfig model."""
        def _coerce_datetime(value: Optional[datetime]) -> Optional[datetime]:
            if value is None:
                return None
            if isinstance(value, datetime):
                return value
            return self.from_isoformat(value)

        return AIRoleConfig(
            id=row.id,
            profile_id=row.profile_id,
            name=row.name,
            description=row.description,
            agent_type=row.agent_type,
            icon=row.icon,
            playbooks=self.deserialize_json(row.playbooks, []),
            suggested_tasks=self.deserialize_json(row.suggested_tasks, []),
            tools=self.deserialize_json(row.tools, []),
            mindscape_profile_override=self.deserialize_json(
                row.mindscape_profile_override, None
            ),
            usage_count=row.usage_count or 0,
            last_used_at=_coerce_datetime(row.last_used_at),
            is_enabled=bool(row.is_enabled) if row.is_enabled is not None else True,
            is_custom=bool(row.is_custom) if row.is_custom is not None else False,
            created_at=_coerce_datetime(row.created_at) or _utc_now(),
            updated_at=_coerce_datetime(row.updated_at) or _utc_now(),
            x_platform=self.deserialize_json(row.x_platform, None),
        )
