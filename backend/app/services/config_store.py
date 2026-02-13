"""
Configuration Store
Manages user configuration settings (backend preferences, etc.)
"""

from typing import Optional
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


import logging

from sqlalchemy import text

from backend.app.models.config import UserConfig, AgentBackendConfig, IntentConfig
from backend.app.services.stores.postgres_base import PostgresStoreBase

logger = logging.getLogger(__name__)


class ConfigStore(PostgresStoreBase):
    """PostgreSQL-based configuration store"""

    def __init__(self, db_path: str = None):
        super().__init__()
        if db_path is not None:
            logger.warning("ConfigStore ignores db_path in Postgres-only mode.")
        if self.factory.get_db_type(self.db_role) != "postgres":
            raise RuntimeError(
                "SQLite is no longer supported for ConfigStore. Configure PostgreSQL."
            )
        self._ensure_schema()

    def _ensure_schema(self):
        """Ensure user_configs table exists (managed by Alembic)."""
        with self.get_connection() as conn:
            result = conn.execute(
                text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = 'user_configs'"
                )
            )
            if result.fetchone() is None:
                logger.warning(
                    "Missing PostgreSQL table: user_configs. "
                    "Will be created by migration orchestrator in startup_event."
                )

    def get_config(self, profile_id: str) -> Optional[UserConfig]:
        """Get user configuration"""
        with self.get_connection() as conn:
            row = (
                conn.execute(
                    text("SELECT * FROM user_configs WHERE profile_id = :profile_id"),
                    {"profile_id": profile_id},
                )
                .mappings()
                .fetchone()
            )

        if not row:
            return None

        metadata = self.deserialize_json(row["metadata"], default={})

        intent_config_data = metadata.get("intent_config", {})
        intent_config = IntentConfig(
            use_llm=intent_config_data.get("use_llm", True),
            rule_priority=intent_config_data.get("rule_priority", True),
        )

        return UserConfig(
            profile_id=row["profile_id"],
            agent_backend=AgentBackendConfig(
                mode=row["agent_backend_mode"] or "local",
                remote_crs_url=row["remote_crs_url"],
                remote_crs_token=row["remote_crs_token"],
                openai_api_key=row["openai_api_key"],
                anthropic_api_key=row["anthropic_api_key"],
                vertex_api_key=row["vertex_api_key"],
                vertex_project_id=row["vertex_project_id"],
                vertex_location=row["vertex_location"],
            ),
            intent_config=intent_config,
            metadata=metadata,
        )

    def save_config(self, config: UserConfig) -> UserConfig:
        """Save user configuration"""
        metadata = dict(config.metadata)
        metadata["intent_config"] = {
            "use_llm": config.intent_config.use_llm,
            "rule_priority": config.intent_config.rule_priority,
        }
        if "profile_model_mapping" in config.metadata:
            metadata["profile_model_mapping"] = config.metadata["profile_model_mapping"]
        if "custom_model_provider_mapping" in config.metadata:
            metadata["custom_model_provider_mapping"] = config.metadata[
                "custom_model_provider_mapping"
            ]

        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO user_configs
                    (profile_id, agent_backend_mode, remote_crs_url, remote_crs_token,
                     openai_api_key, anthropic_api_key, vertex_api_key, vertex_project_id,
                     vertex_location, metadata, updated_at)
                    VALUES
                    (:profile_id, :agent_backend_mode, :remote_crs_url, :remote_crs_token,
                     :openai_api_key, :anthropic_api_key, :vertex_api_key, :vertex_project_id,
                     :vertex_location, :metadata, :updated_at)
                    ON CONFLICT (profile_id) DO UPDATE SET
                        agent_backend_mode = EXCLUDED.agent_backend_mode,
                        remote_crs_url = EXCLUDED.remote_crs_url,
                        remote_crs_token = EXCLUDED.remote_crs_token,
                        openai_api_key = EXCLUDED.openai_api_key,
                        anthropic_api_key = EXCLUDED.anthropic_api_key,
                        vertex_api_key = EXCLUDED.vertex_api_key,
                        vertex_project_id = EXCLUDED.vertex_project_id,
                        vertex_location = EXCLUDED.vertex_location,
                        metadata = EXCLUDED.metadata,
                        updated_at = EXCLUDED.updated_at
                    """
                ),
                {
                    "profile_id": config.profile_id,
                    "agent_backend_mode": config.agent_backend.mode,
                    "remote_crs_url": config.agent_backend.remote_crs_url,
                    "remote_crs_token": config.agent_backend.remote_crs_token,
                    "openai_api_key": config.agent_backend.openai_api_key,
                    "anthropic_api_key": config.agent_backend.anthropic_api_key,
                    "vertex_api_key": config.agent_backend.vertex_api_key,
                    "vertex_project_id": config.agent_backend.vertex_project_id,
                    "vertex_location": config.agent_backend.vertex_location,
                    "metadata": self.serialize_json(metadata),
                    "updated_at": _utc_now(),
                },
            )

        return config

    def get_or_create_config(self, profile_id: str) -> UserConfig:
        """Get existing config or create default"""
        config = self.get_config(profile_id)
        if not config:
            config = UserConfig(profile_id=profile_id)
            self.save_config(config)
        return config
