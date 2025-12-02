"""
Configuration Store
Manages user configuration settings (backend preferences, etc.)
"""

import json
import sqlite3
from typing import Optional, Dict, Any
from contextlib import contextmanager
import logging

from backend.app.models.config import UserConfig, AgentBackendConfig, IntentConfig

logger = logging.getLogger(__name__)


class ConfigStore:
    """Local SQLite-based configuration store"""

    def __init__(self, db_path: str = None):
        # Use the same database as MindscapeStore
        if db_path is None:
            import os
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
        """Initialize configuration table"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_configs (
                    profile_id TEXT PRIMARY KEY,
                    agent_backend_mode TEXT DEFAULT 'local',
                    remote_crs_url TEXT,
                    remote_crs_token TEXT,
                    openai_api_key TEXT,
                    anthropic_api_key TEXT,
                    vertex_api_key TEXT,
                    vertex_project_id TEXT,
                    vertex_location TEXT,
                    metadata TEXT,
                    updated_at TEXT NOT NULL
                )
            ''')
            # Add new columns if they don't exist (for existing databases)
            try:
                cursor.execute('ALTER TABLE user_configs ADD COLUMN openai_api_key TEXT')
            except sqlite3.OperationalError:
                pass  # Column already exists
            try:
                cursor.execute('ALTER TABLE user_configs ADD COLUMN anthropic_api_key TEXT')
            except sqlite3.OperationalError:
                pass  # Column already exists
            try:
                cursor.execute('ALTER TABLE user_configs ADD COLUMN vertex_api_key TEXT')
            except sqlite3.OperationalError:
                pass  # Column already exists
            try:
                cursor.execute('ALTER TABLE user_configs ADD COLUMN vertex_project_id TEXT')
            except sqlite3.OperationalError:
                pass  # Column already exists
            try:
                cursor.execute('ALTER TABLE user_configs ADD COLUMN vertex_location TEXT')
            except sqlite3.OperationalError:
                pass  # Column already exists
            conn.commit()

    def get_config(self, profile_id: str) -> Optional[UserConfig]:
        """Get user configuration"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM user_configs WHERE profile_id = ?', (profile_id,))
            row = cursor.fetchone()

            if not row:
                return None

            # Helper function to safely get column value
            def get_col(key, default=None):
                try:
                    val = row[key]
                    return val if val else default
                except (KeyError, IndexError):
                    return default

            metadata = json.loads(row['metadata'] or '{}')

            # Extract intent_config from metadata (backward compatible)
            intent_config_data = metadata.get('intent_config', {})
            intent_config = IntentConfig(
                use_llm=intent_config_data.get('use_llm', True),
                rule_priority=intent_config_data.get('rule_priority', True)
            )

            return UserConfig(
                profile_id=row['profile_id'],
                agent_backend=AgentBackendConfig(
                    mode=row['agent_backend_mode'] or 'local',
                    remote_crs_url=get_col('remote_crs_url'),
                    remote_crs_token=get_col('remote_crs_token'),
                    openai_api_key=get_col('openai_api_key'),
                    anthropic_api_key=get_col('anthropic_api_key'),
                    vertex_api_key=get_col('vertex_api_key'),
                    vertex_project_id=get_col('vertex_project_id'),
                    vertex_location=get_col('vertex_location')
                ),
                intent_config=intent_config,
                metadata=metadata
            )

    def save_config(self, config: UserConfig) -> UserConfig:
        """Save user configuration"""
        from datetime import datetime

        # Merge intent_config into metadata for storage
        metadata = config.metadata.copy()
        metadata['intent_config'] = {
            'use_llm': config.intent_config.use_llm,
            'rule_priority': config.intent_config.rule_priority
        }

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO user_configs
                (profile_id, agent_backend_mode, remote_crs_url, remote_crs_token, openai_api_key, anthropic_api_key, vertex_api_key, vertex_project_id, vertex_location, metadata, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                config.profile_id,
                config.agent_backend.mode,
                config.agent_backend.remote_crs_url,
                config.agent_backend.remote_crs_token,
                config.agent_backend.openai_api_key,
                config.agent_backend.anthropic_api_key,
                config.agent_backend.vertex_api_key,
                config.agent_backend.vertex_project_id,
                config.agent_backend.vertex_location,
                json.dumps(metadata),
                datetime.utcnow().isoformat()
            ))
            conn.commit()
            return config

    def get_or_create_config(self, profile_id: str) -> UserConfig:
        """Get existing config or create default"""
        config = self.get_config(profile_id)
        if not config:
            config = UserConfig(profile_id=profile_id)
            self.save_config(config)
        return config
