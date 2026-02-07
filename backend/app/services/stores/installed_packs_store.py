"""
Installed Packs Store
Manages installed capability pack metadata.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from app.services.stores.postgres_base import PostgresStoreBase


class InstalledPacksStore(PostgresStoreBase):
    """Postgres-backed store for installed packs."""

    def __init__(self, db_role: str = "core"):
        super().__init__(db_role=db_role)

    def list_installed_pack_ids(self) -> List[str]:
        with self.get_connection() as conn:
            rows = conn.execute(text("SELECT pack_id FROM installed_packs")).fetchall()
            return [row.pack_id for row in rows]

    def list_enabled_pack_ids(self) -> List[str]:
        with self.get_connection() as conn:
            rows = conn.execute(
                text("SELECT pack_id FROM installed_packs WHERE enabled = true")
            ).fetchall()
            return [row.pack_id for row in rows]

    def list_installed_metadata(self) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            rows = conn.execute(
                text("SELECT pack_id, installed_at, enabled, metadata FROM installed_packs")
            ).fetchall()
            results = []
            for row in rows:
                installed_at = row.installed_at
                if isinstance(installed_at, datetime):
                    installed_at_value = installed_at.isoformat()
                else:
                    installed_at_value = installed_at
                results.append(
                    {
                        "pack_id": row.pack_id,
                        "installed_at": installed_at_value,
                        "enabled": bool(row.enabled) if row.enabled is not None else False,
                        "metadata": self.deserialize_json(row.metadata, {}),
                    }
                )
            return results

    def get_pack(self, pack_id: str) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            row = conn.execute(
                text(
                    "SELECT pack_id, installed_at, enabled, metadata FROM installed_packs WHERE pack_id = :pack_id"
                ),
                {"pack_id": pack_id},
            ).fetchone()
            if not row:
                return None
            installed_at = row.installed_at
            if isinstance(installed_at, datetime):
                installed_at_value = installed_at.isoformat()
            else:
                installed_at_value = installed_at
            return {
                "pack_id": row.pack_id,
                "installed_at": installed_at_value,
                "enabled": bool(row.enabled) if row.enabled is not None else False,
                "metadata": self.deserialize_json(row.metadata, {}),
            }

    def upsert_pack(
        self,
        pack_id: str,
        installed_at: Optional[datetime] = None,
        enabled: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO installed_packs (pack_id, installed_at, enabled, metadata)
                    VALUES (:pack_id, :installed_at, :enabled, :metadata)
                    ON CONFLICT (pack_id) DO UPDATE SET
                        installed_at = EXCLUDED.installed_at,
                        enabled = EXCLUDED.enabled,
                        metadata = EXCLUDED.metadata
                """
                ),
                {
                    "pack_id": pack_id,
                    "installed_at": installed_at or datetime.utcnow(),
                    "enabled": enabled,
                    "metadata": self.serialize_json(metadata or {}),
                },
            )

    def set_enabled(self, pack_id: str, enabled: bool) -> bool:
        with self.transaction() as conn:
            result = conn.execute(
                text(
                    "UPDATE installed_packs SET enabled = :enabled WHERE pack_id = :pack_id"
                ),
                {"enabled": enabled, "pack_id": pack_id},
            )
            return result.rowcount > 0
