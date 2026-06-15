"""CRUD and serialization methods for SystemSettingsStore."""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from sqlalchemy import text

from backend.app.models.system_settings import SystemSetting, SettingType
from backend.app.services.system_settings_utils import _utc_now

logger = logging.getLogger(__name__)


class SystemSettingsCRUDMixin:
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
        if not self._tables_ready:
            return None
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
