"""
System Settings Store

Manages system-level settings storage in SQLite database.
Supports key-value pairs with type information and categories.
"""

import json
import sqlite3
from typing import Optional, Dict, Any, List, Union
from pathlib import Path
from datetime import datetime
import logging

from backend.app.models.system_settings import SystemSetting, SettingType

logger = logging.getLogger(__name__)


class SystemSettingsStore:
    """SQLite-based system settings store"""

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize system settings store

        Args:
            db_path: Path to SQLite database (default: ./data/mindscape.db)
        """
        if db_path is None:
            db_path = Path("./data/mindscape.db")
        else:
            db_path = Path(db_path)

        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize system_settings table"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                value_type TEXT NOT NULL,
                category TEXT DEFAULT 'general',
                description TEXT,
                is_sensitive INTEGER DEFAULT 0,
                is_user_editable INTEGER DEFAULT 1,
                default_value TEXT,
                metadata TEXT,
                updated_at TEXT NOT NULL
            )
        """)

        # Create index for category lookups
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_system_settings_category
            ON system_settings(category)
        """)

        conn.commit()
        conn.close()

        # Initialize default settings
        self._init_default_settings()

        # Migrate existing settings (e.g., enable_capability_profile)
        self._migrate_settings()

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
                "default_value": "zh-TW"
            },
            {
                "key": "default_llm_provider",
                "value": "openai",
                "value_type": SettingType.STRING,
                "category": "llm",
                "description": "Default LLM provider (openai, anthropic, etc.)",
                "is_sensitive": False,
                "is_user_editable": True,
                "default_value": "openai"
            },
            {
                "key": "enable_capability_profile",
                "value": "true",
                "value_type": SettingType.BOOLEAN,
                "category": "llm",
                "description": "Enable capability profile system for staged model switching (default: true)",
                "is_sensitive": False,
                "is_user_editable": True,
                "default_value": "true"
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
                    "is_latest": True
                }
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
                    "dimensions": 3072
                }
            },
            {
                "key": "enable_analytics",
                "value": False,
                "value_type": SettingType.BOOLEAN,
                "category": "general",
                "description": "Enable usage analytics",
                "is_sensitive": False,
                "is_user_editable": True,
                "default_value": False
            },
            {
                "key": "auto_save_enabled",
                "value": True,
                "value_type": SettingType.BOOLEAN,
                "category": "ui",
                "description": "Enable auto-save for workspaces",
                "is_sensitive": False,
                "is_user_editable": True,
                "default_value": True
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
                                "provider_type": {"type": "string", "enum": ["official", "generic_http", "custom"]},
                                "enabled": {"type": "boolean"},
                                "config": {"type": "object"}
                            },
                            "required": ["provider_id", "provider_type", "enabled", "config"]
                        }
                    }
                }
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
                "default_value": ""
            },
            {
                "key": "google_oauth_client_secret",
                "value": "",
                "value_type": SettingType.STRING,
                "category": "oauth",
                "description": "Google OAuth 2.0 Client Secret for Google Drive integration",
                "is_sensitive": True,
                "is_user_editable": True,
                "default_value": ""
            },
            {
                "key": "google_oauth_redirect_uri",
                "value": "",
                "value_type": SettingType.STRING,
                "category": "oauth",
                "description": "Google OAuth Redirect URI (default: auto-generated from BACKEND_URL)",
                "is_sensitive": False,
                "is_user_editable": True,
                "default_value": ""
            },
            {
                "key": "backend_url",
                "value": "",
                "value_type": SettingType.STRING,
                "category": "oauth",
                "description": "Backend URL for OAuth callback construction",
                "is_sensitive": False,
                "is_user_editable": True,
                "default_value": ""
            }
        ]

        for setting_data in default_settings:
            try:
                existing = self.get_setting(setting_data["key"])
                if not existing:
                    setting = SystemSetting(**setting_data)
                    self.save_setting(setting)
            except Exception as e:
                logger.warning(f"Failed to initialize default setting {setting_data['key']}: {e}")

    def _migrate_settings(self):
        """Migrate existing settings to ensure compatibility"""
        try:
            # Migrate enable_capability_profile: if not set or False, set to True
            enable_flag = self.get_setting("enable_capability_profile")
            if not enable_flag or str(enable_flag.value).lower() not in ["true", "1"]:
                logger.info("Migrating enable_capability_profile: setting to True (default)")
                self.set_setting(
                    key="enable_capability_profile",
                    value=True,
                    value_type=SettingType.BOOLEAN,
                    category="llm",
                    description="Enable capability profile system for staged model switching (default: true)",
                    is_user_editable=True
                )
        except Exception as e:
            logger.warning(f"Failed to migrate settings: {e}", exc_info=True)

    def _serialize_value(self, value: Union[str, int, float, bool, Dict[str, Any], List[Any]], value_type: SettingType) -> str:
        """Serialize value to string for storage"""
        if value_type == SettingType.JSON or isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    def _deserialize_value(self, value_str: str, value_type: SettingType) -> Union[str, int, float, bool, Dict[str, Any], List[Any]]:
        """Deserialize value from string"""
        if value_type == SettingType.JSON or value_type == SettingType.ARRAY:
            try:
                return json.loads(value_str)
            except json.JSONDecodeError:
                return value_str
        elif value_type == SettingType.INTEGER:
            try:
                return int(value_str)
            except ValueError:
                return 0
        elif value_type == SettingType.FLOAT:
            try:
                return float(value_str)
            except ValueError:
                return 0.0
        elif value_type == SettingType.BOOLEAN:
            return value_str.lower() in ('true', '1', 'yes', 'on')
        else:
            return value_str

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get setting value by key (convenience method)

        Args:
            key: Setting key
            default: Default value if setting not found

        Returns:
            Setting value or default
        """
        setting = self.get_setting(key)
        if setting is None:
            return default
        return setting.value

    def get_setting(self, key: str) -> Optional[SystemSetting]:
        """Get a single setting by key"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM system_settings WHERE key = ?
        """, (key,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        value = self._deserialize_value(row["value"], SettingType(row["value_type"]))

        default_value = None
        if row["default_value"]:
            default_value = self._deserialize_value(row["default_value"], SettingType(row["value_type"]))

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
            updated_at=datetime.fromisoformat(row["updated_at"])
        )

    def get_settings_by_category(self, category: str) -> List[SystemSetting]:
        """Get all settings in a category"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM system_settings WHERE category = ? ORDER BY key
        """, (category,))

        rows = cursor.fetchall()
        conn.close()

        settings = []
        for row in rows:
            value = self._deserialize_value(row["value"], SettingType(row["value_type"]))

            default_value = None
            if row["default_value"]:
                default_value = self._deserialize_value(row["default_value"], SettingType(row["value_type"]))

            metadata = {}
            if row["metadata"]:
                try:
                    metadata = json.loads(row["metadata"])
                except json.JSONDecodeError:
                    pass

            settings.append(SystemSetting(
                key=row["key"],
                value=value,
                value_type=SettingType(row["value_type"]),
                category=row["category"],
                description=row["description"],
                is_sensitive=bool(row["is_sensitive"]),
                is_user_editable=bool(row["is_user_editable"]),
                default_value=default_value,
                metadata=metadata,
                updated_at=datetime.fromisoformat(row["updated_at"])
            ))

        return settings

    def get_all_settings(self, include_sensitive: bool = False) -> Dict[str, Any]:
        """Get all settings as dictionary"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM system_settings ORDER BY category, key
        """)

        rows = cursor.fetchall()
        conn.close()

        settings = {}
        for row in rows:
            is_sensitive = bool(row["is_sensitive"])
            if is_sensitive and not include_sensitive:
                settings[row["key"]] = "***"  # Mask sensitive values
            else:
                value = self._deserialize_value(row["value"], SettingType(row["value_type"]))
                settings[row["key"]] = value

        return settings

    def get_categories(self) -> List[str]:
        """Get list of all setting categories"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT DISTINCT category FROM system_settings ORDER BY category
        """)

        categories = [row[0] for row in cursor.fetchall()]
        conn.close()

        return categories

    def save_setting(self, setting: SystemSetting) -> SystemSetting:
        """Save or update a setting"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        value_str = self._serialize_value(setting.value, setting.value_type)
        default_value_str = None
        if setting.default_value is not None:
            default_value_str = self._serialize_value(setting.default_value, setting.value_type)

        metadata_str = json.dumps(setting.metadata, ensure_ascii=False) if setting.metadata else None

        cursor.execute("""
            INSERT OR REPLACE INTO system_settings
            (key, value, value_type, category, description, is_sensitive, is_user_editable, default_value, metadata, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            setting.key,
            value_str,
            setting.value_type.value,
            setting.category,
            setting.description,
            1 if setting.is_sensitive else 0,
            1 if setting.is_user_editable else 0,
            default_value_str,
            metadata_str,
            datetime.utcnow().isoformat()
        ))

        conn.commit()

        # Verify the save was successful
        cursor.execute("SELECT value FROM system_settings WHERE key = ?", (setting.key,))
        saved_row = cursor.fetchone()
        saved_value = saved_row[0] if saved_row else None

        conn.close()

        if saved_value != value_str:
            logger.error(f"WARNING: Saved value mismatch for {setting.key}. Expected: {value_str[:50]}..., Got: {saved_value[:50] if saved_value else 'None'}...")
        else:
            logger.info(f"Saved system setting: {setting.key} (value length: {len(value_str) if value_str else 0})")

        return setting

    def update_settings(self, settings: Dict[str, Union[str, int, float, bool, Dict[str, Any], List[Any]]]) -> Dict[str, SystemSetting]:
        """Update multiple settings at once"""
        updated = {}

        for key, value in settings.items():
            existing = self.get_setting(key)

            if not existing:
                # Infer type from value
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
                    category="general"
                )
            else:
                # Update existing setting
                setting = SystemSetting(
                    key=existing.key,
                    value=value,
                    value_type=existing.value_type,
                    category=existing.category,
                    description=existing.description,
                    is_sensitive=existing.is_sensitive,
                    is_user_editable=existing.is_user_editable,
                    default_value=existing.default_value,
                    metadata=existing.metadata
                )

            updated[key] = self.save_setting(setting)

        return updated

    def delete_setting(self, key: str) -> bool:
        """Delete a setting"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("DELETE FROM system_settings WHERE key = ?", (key,))
        deleted = cursor.rowcount > 0

        conn.commit()
        conn.close()

        if deleted:
            logger.info(f"Deleted system setting: {key}")

        return deleted

    def set_capability_profile_mapping(self, mapping: Dict[str, str]) -> None:
        """
        Set stage to capability profile mapping

        Args:
            mapping: Dictionary mapping stage names to capability profile names
                    Example: {"intent_analysis": "fast", "plan_generation": "precise"}
        """
        self.set_setting(
            key="capability_profile_mapping",
            value=mapping,
            value_type=SettingType.JSON,
            category="llm",
            description="Stage to capability profile mapping for staged model switching"
        )

    def get_capability_profile_mapping(self) -> Dict[str, str]:
        """
        Get stage to capability profile mapping

        Returns:
            Dictionary mapping stage names to capability profile names
            Returns empty dict if not set
        """
        setting = self.get_setting("capability_profile_mapping")
        if setting and isinstance(setting.value, dict):
            return setting.value
        return {}

    def set_profile_model_mapping(self, mapping: Dict[str, List[str]]) -> None:
        """
        Set capability profile to model list mapping

        Args:
            mapping: Dictionary mapping profile names to model candidate lists
                    Example: {"fast": ["gpt-3.5-turbo", "gpt-4o-mini"], "precise": ["gpt-4", "claude-3-opus"]}
        """
        self.set_setting(
            key="profile_model_mapping",
            value=mapping,
            value_type=SettingType.JSON,
            category="llm",
            description="Capability profile to model candidate list mapping"
        )

    def get_profile_model_mapping(self) -> Dict[str, List[str]]:
        """
        Get capability profile to model list mapping

        Returns:
            Dictionary mapping profile names to model candidate lists
            Returns empty dict if not set
        """
        setting = self.get_setting("profile_model_mapping")
        if setting and isinstance(setting.value, dict):
            return setting.value
        return {}

    def set_custom_model_provider_mapping(self, mapping: Dict[str, str]) -> None:
        """
        Set custom model name to provider mapping

        Args:
            mapping: Dictionary mapping custom model names to provider names
                    Example: {"custom-model-1": "openai", "my-claude-model": "anthropic"}
        """
        self.set_setting(
            key="custom_model_provider_mapping",
            value=mapping,
            value_type=SettingType.JSON,
            category="llm",
            description="Custom model name to provider mapping for tenant-specific models"
        )

    def get_custom_model_provider_mapping(self) -> Dict[str, str]:
        """
        Get custom model name to provider mapping

        Returns:
            Dictionary mapping custom model names to provider names
            Returns empty dict if not set
        """
        setting = self.get_setting("custom_model_provider_mapping")
        if setting:
            if isinstance(setting.value, dict):
                return setting.value
            elif isinstance(setting.value, str):
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
        default_value: Optional[Union[str, int, float, bool, Dict[str, Any], List[Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> SystemSetting:
        """
        Set a system setting (convenience method)

        Args:
            key: Setting key
            value: Setting value
            value_type: Value type
            category: Setting category
            description: Setting description
            is_sensitive: Whether the setting is sensitive
            is_user_editable: Whether the setting is user-editable
            default_value: Default value
            metadata: Additional metadata

        Returns:
            Saved SystemSetting instance
        """
        setting = SystemSetting(
            key=key,
            value=value,
            value_type=value_type,
            category=category,
            description=description,
            is_sensitive=is_sensitive,
            is_user_editable=is_user_editable,
            default_value=default_value,
            metadata=metadata or {}
        )
        return self.save_setting(setting)
