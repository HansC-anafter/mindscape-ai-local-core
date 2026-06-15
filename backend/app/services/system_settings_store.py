"""
System Settings Store

Manages system-level settings storage in PostgreSQL.
Supports key-value pairs with type information and categories.
"""

import logging
from typing import Optional

from sqlalchemy import text

from backend.app.services.stores.postgres_base import PostgresStoreBase
from backend.app.services.system_settings_crud import SystemSettingsCRUDMixin
from backend.app.services.system_settings_defaults import SystemSettingsDefaultsMixin
from backend.app.services.system_settings_profile_bindings import (
    SystemSettingsProfileBindingsMixin,
)
from backend.app.services.system_settings_utils import _utc_now

logger = logging.getLogger(__name__)


class SystemSettingsStore(
    SystemSettingsDefaultsMixin,
    SystemSettingsCRUDMixin,
    SystemSettingsProfileBindingsMixin,
    PostgresStoreBase,
):
    """PostgreSQL-based system settings store"""

    _schema_ensured = False
    _defaults_initialized = False

    def __init__(self, db_path: Optional[str] = None):
        super().__init__()
        self._tables_ready = False
        # (Silenced db_path warning to avoid spam across multiple processes)
        if self.factory.get_db_type(self.db_role) != "postgres":
            raise RuntimeError(
                "SQLite is no longer supported for SystemSettingsStore. Configure PostgreSQL."
            )

        if not SystemSettingsStore._schema_ensured:
            self._ensure_schema()
        else:
            self._tables_ready = True

        if self._tables_ready and not SystemSettingsStore._defaults_initialized:
            self._init_default_settings()
            self._migrate_settings()
            SystemSettingsStore._defaults_initialized = True

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
            self._tables_ready = True
            SystemSettingsStore._schema_ensured = True
