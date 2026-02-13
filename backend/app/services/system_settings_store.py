"""
System Settings Store

Manages system-level settings storage in PostgreSQL.
Supports key-value pairs with type information and categories.
"""

import json
from typing import Optional, Dict, Any, List, Union
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


import logging

from sqlalchemy import text

from backend.app.models.system_settings import SystemSetting, SettingType
from backend.app.services.stores.postgres_base import PostgresStoreBase

logger = logging.getLogger(__name__)


class SystemSettingsStore(PostgresStoreBase):
    """PostgreSQL-based system settings store"""

    def __init__(self, db_path: Optional[str] = None):
        super().__init__()
        if db_path is not None:
            logger.warning("SystemSettingsStore ignores db_path in Postgres-only mode.")
        if self.factory.get_db_type(self.db_role) != "postgres":
            raise RuntimeError(
                "SQLite is no longer supported for SystemSettingsStore. Configure PostgreSQL."
            )
        self._ensure_schema()
        self._init_default_settings()
        self._migrate_settings()

    def _ensure_schema(self):
        """Ensure system_settings table exists (managed by Alembic)."""
        with self.get_connection() as conn:
            result = conn.execute(
                text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = 'system_settings'"
                )
            )
            if result.fetchone() is None:
                logger.warning(
                    "Missing PostgreSQL table: system_settings. "
                    "Will be created by migration orchestrator in startup_event."
                )
                return

    def _init_default_settings(self):
        """Initialize default system settings"""
        default_settings = [
            {
                "key": "default_language",
                "value": "zh-TW",
                "value_type": SettingType.STRING,
                "category": "ui",
                "description": "Default UI language",
                "is_sensitive": False,
                "is_user_editable": True,
                "default_value": "zh-TW",
            },
            {
                "key": "default_llm_provider",
                "value": "openai",
                "value_type": SettingType.STRING,
                "category": "llm",
                "description": "Default LLM provider (openai, anthropic, etc.)",
                "is_sensitive": False,
                "is_user_editable": True,
                "default_value": "openai",
            },
            {
                "key": "enable_capability_profile",
                "value": "true",
                "value_type": SettingType.BOOLEAN,
                "category": "llm",
                "description": "Enable capability profile system for staged model switching (default: true)",
                "is_sensitive": False,
                "is_user_editable": True,
                "default_value": "true",
            },
            {
                "key": "chat_model",
                "value": "gpt-5.1",
                "value_type": SettingType.STRING,
                "category": "llm",
                "description": "Model for chat/conversation inference (latest: gpt-5.1, gpt-5.1-pro, claude-haiku-4.5)",
                "is_sensitive": False,
                "is_user_editable": True,
                "default_value": "gpt-5.1",
                "metadata": {
                    "provider": "openai",
                    "model_type": "chat",
                    "is_latest": True,
                },
            },
            {
                "key": "embedding_model",
                "value": "text-embedding-3-large",
                "value_type": SettingType.STRING,
                "category": "llm",
                "description": "Model for embeddings/vectorization (latest: text-embedding-3-large, supports adjustable dimensions)",
                "is_sensitive": False,
                "is_user_editable": True,
                "default_value": "text-embedding-3-large",
                "metadata": {
                    "provider": "openai",
                    "model_type": "embedding",
                    "is_latest": True,
                    "dimensions": 3072,
                },
            },
            {
                "key": "enable_analytics",
                "value": False,
                "value_type": SettingType.BOOLEAN,
                "category": "general",
                "description": "Enable usage analytics",
                "is_sensitive": False,
                "is_user_editable": True,
                "default_value": False,
            },
            {
                "key": "auto_save_enabled",
                "value": True,
                "value_type": SettingType.BOOLEAN,
                "category": "ui",
                "description": "Enable auto-save for workspaces",
                "is_sensitive": False,
                "is_user_editable": True,
                "default_value": True,
            },
            # Cloud Extension Settings (Neutral - all providers configured here)
            {
                "key": "cloud_providers",
                "value": [],
                "value_type": SettingType.JSON,
                "category": "cloud",
                "description": "List of cloud playbook providers (all providers, including official, are configured here)",
                "is_sensitive": False,
                "is_user_editable": True,
                "default_value": [],
                "metadata": {
                    "schema": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "provider_id": {"type": "string"},
                                "provider_type": {
                                    "type": "string",
                                    "enum": ["official", "generic_http", "custom"],
                                },
                                "enabled": {"type": "boolean"},
                                "config": {"type": "object"},
                            },
                            "required": [
                                "provider_id",
                                "provider_type",
                                "enabled",
                                "config",
                            ],
                        },
                    }
                },
            },
            # Google OAuth Settings
            {
                "key": "google_oauth_client_id",
                "value": "",
                "value_type": SettingType.STRING,
                "category": "oauth",
                "description": "Google OAuth 2.0 Client ID for Google Drive integration",
                "is_sensitive": False,
                "is_user_editable": True,
                "default_value": "",
            },
            {
                "key": "google_oauth_client_secret",
                "value": "",
                "value_type": SettingType.STRING,
                "category": "oauth",
                "description": "Google OAuth 2.0 Client Secret for Google Drive integration",
                "is_sensitive": True,
                "is_user_editable": True,
                "default_value": "",
            },
            {
                "key": "google_oauth_redirect_uri",
                "value": "",
                "value_type": SettingType.STRING,
                "category": "oauth",
                "description": "Google OAuth Redirect URI (default: auto-generated from BACKEND_URL)",
                "is_sensitive": False,
                "is_user_editable": True,
                "default_value": "",
            },
            {
                "key": "backend_url",
                "value": "",
                "value_type": SettingType.STRING,
                "category": "oauth",
                "description": "Backend URL for OAuth callback construction",
                "is_sensitive": False,
                "is_user_editable": True,
                "default_value": "",
            },
        ]

        for setting_data in default_settings:
            try:
                existing = self.get_setting(setting_data["key"])
                if not existing:
                    setting = SystemSetting(**setting_data)
                    self.save_setting(setting)
            except Exception as exc:
                logger.warning(
                    "Failed to initialize default setting %s: %s",
                    setting_data["key"],
                    exc,
                )

    def _migrate_settings(self):
        """Migrate existing settings to ensure compatibility"""
        try:
            enable_flag = self.get_setting("enable_capability_profile")
            if not enable_flag or str(enable_flag.value).lower() not in ["true", "1"]:
                logger.info(
                    "Migrating enable_capability_profile: setting to True (default)"
                )
                self.set_setting(
                    key="enable_capability_profile",
                    value=True,
                    value_type=SettingType.BOOLEAN,
                    category="llm",
                    description=(
                        "Enable capability profile system for staged model switching (default: true)"
                    ),
                    is_user_editable=True,
                )
        except Exception as exc:
            logger.warning("Failed to migrate settings: %s", exc, exc_info=True)

    def _serialize_value(
        self,
        value: Union[str, int, float, bool, Dict[str, Any], List[Any]],
        value_type: SettingType,
    ) -> str:
        """Serialize value to string for storage"""
        if value_type == SettingType.JSON or isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    def _deserialize_value(
        self, value_str: str, value_type: SettingType
    ) -> Union[str, int, float, bool, Dict[str, Any], List[Any]]:
        """Deserialize value from string"""
        if value_type in {SettingType.JSON, SettingType.ARRAY}:
            try:
                return json.loads(value_str)
            except json.JSONDecodeError:
                return value_str
        if value_type == SettingType.INTEGER:
            try:
                return int(value_str)
            except ValueError:
                return 0
        if value_type == SettingType.FLOAT:
            try:
                return float(value_str)
            except ValueError:
                return 0.0
        if value_type == SettingType.BOOLEAN:
            return str(value_str).lower() in {"true", "1", "yes", "on"}
        return value_str

    def _coerce_datetime(self, value: Any) -> datetime:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str) and value:
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return _utc_now()
        return _utc_now()

    def get(self, key: str, default: Any = None) -> Any:
        setting = self.get_setting(key)
        if setting is None:
            return default
        return setting.value

    def get_setting(self, key: str) -> Optional[SystemSetting]:
        with self.get_connection() as conn:
            row = (
                conn.execute(
                    text("SELECT * FROM system_settings WHERE key = :key"),
                    {"key": key},
                )
                .mappings()
                .fetchone()
            )

        if not row:
            return None

        value = self._deserialize_value(row["value"], SettingType(row["value_type"]))

        default_value = None
        if row["default_value"]:
            default_value = self._deserialize_value(
                row["default_value"], SettingType(row["value_type"])
            )

        metadata = {}
        if row["metadata"]:
            try:
                metadata = json.loads(row["metadata"])
            except json.JSONDecodeError:
                pass

        return SystemSetting(
            key=row["key"],
            value=value,
            value_type=SettingType(row["value_type"]),
            category=row["category"],
            description=row["description"],
            is_sensitive=bool(row["is_sensitive"]),
            is_user_editable=bool(row["is_user_editable"]),
            default_value=default_value,
            metadata=metadata,
            updated_at=self._coerce_datetime(row["updated_at"]),
        )

    def get_settings_by_category(self, category: str) -> List[SystemSetting]:
        with self.get_connection() as conn:
            rows = (
                conn.execute(
                    text(
                        "SELECT * FROM system_settings WHERE category = :category ORDER BY key"
                    ),
                    {"category": category},
                )
                .mappings()
                .fetchall()
            )

        settings: List[SystemSetting] = []
        for row in rows:
            value = self._deserialize_value(
                row["value"], SettingType(row["value_type"])
            )

            default_value = None
            if row["default_value"]:
                default_value = self._deserialize_value(
                    row["default_value"], SettingType(row["value_type"])
                )

            metadata = {}
            if row["metadata"]:
                try:
                    metadata = json.loads(row["metadata"])
                except json.JSONDecodeError:
                    pass

            settings.append(
                SystemSetting(
                    key=row["key"],
                    value=value,
                    value_type=SettingType(row["value_type"]),
                    category=row["category"],
                    description=row["description"],
                    is_sensitive=bool(row["is_sensitive"]),
                    is_user_editable=bool(row["is_user_editable"]),
                    default_value=default_value,
                    metadata=metadata,
                    updated_at=self._coerce_datetime(row["updated_at"]),
                )
            )

        return settings

    def get_all_settings(self, include_sensitive: bool = False) -> Dict[str, Any]:
        with self.get_connection() as conn:
            rows = (
                conn.execute(
                    text("SELECT * FROM system_settings ORDER BY category, key")
                )
                .mappings()
                .fetchall()
            )

        settings: Dict[str, Any] = {}
        for row in rows:
            is_sensitive = bool(row["is_sensitive"])
            if is_sensitive and not include_sensitive:
                settings[row["key"]] = "***"
            else:
                value = self._deserialize_value(
                    row["value"], SettingType(row["value_type"])
                )
                settings[row["key"]] = value

        return settings

    def get_categories(self) -> List[str]:
        with self.get_connection() as conn:
            rows = conn.execute(
                text("SELECT DISTINCT category FROM system_settings ORDER BY category")
            ).fetchall()
        return [row[0] for row in rows]

    def save_setting(self, setting: SystemSetting) -> SystemSetting:
        value_str = self._serialize_value(setting.value, setting.value_type)
        default_value_str = None
        if setting.default_value is not None:
            default_value_str = self._serialize_value(
                setting.default_value, setting.value_type
            )

        metadata_str = (
            json.dumps(setting.metadata, ensure_ascii=False)
            if setting.metadata
            else None
        )

        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO system_settings
                    (key, value, value_type, category, description, is_sensitive,
                     is_user_editable, default_value, metadata, updated_at)
                    VALUES
                    (:key, :value, :value_type, :category, :description, :is_sensitive,
                     :is_user_editable, :default_value, :metadata, :updated_at)
                    ON CONFLICT (key) DO UPDATE SET
                        value = EXCLUDED.value,
                        value_type = EXCLUDED.value_type,
                        category = EXCLUDED.category,
                        description = EXCLUDED.description,
                        is_sensitive = EXCLUDED.is_sensitive,
                        is_user_editable = EXCLUDED.is_user_editable,
                        default_value = EXCLUDED.default_value,
                        metadata = EXCLUDED.metadata,
                        updated_at = EXCLUDED.updated_at
                    """
                ),
                {
                    "key": setting.key,
                    "value": value_str,
                    "value_type": setting.value_type.value,
                    "category": setting.category,
                    "description": setting.description,
                    "is_sensitive": setting.is_sensitive,
                    "is_user_editable": setting.is_user_editable,
                    "default_value": default_value_str,
                    "metadata": metadata_str,
                    "updated_at": _utc_now(),
                },
            )

        logger.info(
            "Saved system setting: %s (value length: %s)",
            setting.key,
            len(value_str) if value_str else 0,
        )

        return setting

    def update_settings(
        self,
        settings: Dict[str, Union[str, int, float, bool, Dict[str, Any], List[Any]]],
    ) -> Dict[str, SystemSetting]:
        updated: Dict[str, SystemSetting] = {}

        for key, value in settings.items():
            existing = self.get_setting(key)

            if not existing:
                if isinstance(value, bool):
                    value_type = SettingType.BOOLEAN
                elif isinstance(value, int):
                    value_type = SettingType.INTEGER
                elif isinstance(value, float):
                    value_type = SettingType.FLOAT
                elif isinstance(value, (dict, list)):
                    value_type = SettingType.JSON
                else:
                    value_type = SettingType.STRING

                setting = SystemSetting(
                    key=key,
                    value=value,
                    value_type=value_type,
                    category="general",
                )
            else:
                setting = SystemSetting(
                    key=existing.key,
                    value=value,
                    value_type=existing.value_type,
                    category=existing.category,
                    description=existing.description,
                    is_sensitive=existing.is_sensitive,
                    is_user_editable=existing.is_user_editable,
                    default_value=existing.default_value,
                    metadata=existing.metadata,
                )

            updated[key] = self.save_setting(setting)

        return updated

    def delete_setting(self, key: str) -> bool:
        with self.transaction() as conn:
            result = conn.execute(
                text("DELETE FROM system_settings WHERE key = :key"),
                {"key": key},
            )
            deleted = result.rowcount > 0

        if deleted:
            logger.info("Deleted system setting: %s", key)

        return deleted

    def set_capability_profile_mapping(self, mapping: Dict[str, str]) -> None:
        self.set_setting(
            key="capability_profile_mapping",
            value=mapping,
            value_type=SettingType.JSON,
            category="llm",
            description="Stage to capability profile mapping for staged model switching",
        )

    def get_capability_profile_mapping(self) -> Dict[str, str]:
        setting = self.get_setting("capability_profile_mapping")
        if setting and isinstance(setting.value, dict):
            return setting.value
        return {}

    def set_profile_model_mapping(self, mapping: Dict[str, List[str]]) -> None:
        self.set_setting(
            key="profile_model_mapping",
            value=mapping,
            value_type=SettingType.JSON,
            category="llm",
            description="Capability profile to model candidate list mapping",
        )

    def get_profile_model_mapping(self) -> Dict[str, List[str]]:
        setting = self.get_setting("profile_model_mapping")
        if setting and isinstance(setting.value, dict):
            return setting.value
        return {}

    def set_custom_model_provider_mapping(self, mapping: Dict[str, str]) -> None:
        self.set_setting(
            key="custom_model_provider_mapping",
            value=mapping,
            value_type=SettingType.JSON,
            category="llm",
            description="Custom model name to provider mapping for tenant-specific models",
        )

    def get_custom_model_provider_mapping(self) -> Dict[str, str]:
        setting = self.get_setting("custom_model_provider_mapping")
        if setting:
            if isinstance(setting.value, dict):
                return setting.value
            if isinstance(setting.value, str):
                try:
                    return json.loads(setting.value)
                except json.JSONDecodeError:
                    return {}
        return {}

    def set_setting(
        self,
        key: str,
        value: Union[str, int, float, bool, Dict[str, Any], List[Any]],
        value_type: SettingType,
        category: str = "general",
        description: Optional[str] = None,
        is_sensitive: bool = False,
        is_user_editable: bool = True,
        default_value: Optional[
            Union[str, int, float, bool, Dict[str, Any], List[Any]]
        ] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SystemSetting:
        setting = SystemSetting(
            key=key,
            value=value,
            value_type=value_type,
            category=category,
            description=description,
            is_sensitive=is_sensitive,
            is_user_editable=is_user_editable,
            default_value=default_value,
            metadata=metadata or {},
        )
        return self.save_setting(setting)
