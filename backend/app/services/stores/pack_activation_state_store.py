"""Postgres-backed store for pack activation state."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from backend.app.services.stores.postgres_base import PostgresStoreBase


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PackActivationStateStore(PostgresStoreBase):
    """Persist pack activation/install state independently from installed_packs."""

    _NON_REGRESSING_INSTALL_STATES = {"installed", "validation_failed"}

    def __init__(self, db_role: str = "core"):
        super().__init__(db_role=db_role)

    def _row_to_dict(self, row: Any) -> Dict[str, Any]:
        return {
            "pack_id": row.pack_id,
            "pack_family": row.pack_family,
            "enabled": bool(row.enabled) if row.enabled is not None else False,
            "install_state": row.install_state,
            "migration_state": row.migration_state,
            "activation_state": row.activation_state,
            "activation_mode": row.activation_mode,
            "embedding_state": row.embedding_state,
            "embedding_error": row.embedding_error,
            "embeddings_updated_at": self.to_isoformat(row.embeddings_updated_at),
            "manifest_hash": row.manifest_hash,
            "registered_prefixes": self.deserialize_json(row.registered_prefixes, []),
            "last_error": row.last_error,
            "activated_at": self.to_isoformat(row.activated_at),
            "updated_at": self.to_isoformat(row.updated_at),
        }

    def get_state(self, pack_id: str) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT pack_id, pack_family, enabled, install_state, migration_state,
                           activation_state, activation_mode, embedding_state,
                           embedding_error, embeddings_updated_at, manifest_hash,
                           registered_prefixes, last_error, activated_at, updated_at
                    FROM pack_activation_state
                    WHERE pack_id = :pack_id
                    """
                ),
                {"pack_id": pack_id},
            ).fetchone()
            if not row:
                return None
            return self._row_to_dict(row)

    def list_states_by_pack_id(self) -> Dict[str, Dict[str, Any]]:
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT pack_id, pack_family, enabled, install_state, migration_state,
                           activation_state, activation_mode, embedding_state,
                           embedding_error, embeddings_updated_at, manifest_hash,
                           registered_prefixes, last_error, activated_at, updated_at
                    FROM pack_activation_state
                    """
                )
            ).fetchall()
            return {row.pack_id: self._row_to_dict(row) for row in rows}

    def upsert_state(
        self,
        *,
        pack_id: str,
        pack_family: str,
        enabled: bool,
        install_state: str,
        migration_state: str,
        activation_state: str,
        activation_mode: str,
        embedding_state: str,
        embedding_error: Optional[str] = None,
        embeddings_updated_at: Optional[datetime] = None,
        manifest_hash: Optional[str] = None,
        registered_prefixes: Optional[List[str]] = None,
        last_error: Optional[str] = None,
        activated_at: Optional[datetime] = None,
        allow_install_state_regression: bool = True,
    ) -> Dict[str, Any]:
        updated_at = _utc_now()
        with self.transaction() as conn:
            existing_row = conn.execute(
                text(
                    """
                    SELECT install_state, manifest_hash
                    FROM pack_activation_state
                    WHERE pack_id = :pack_id
                    FOR UPDATE
                    """
                ),
                {"pack_id": pack_id},
            ).fetchone()
            install_state = self._resolve_install_state_for_upsert(
                existing_install_state=existing_row.install_state if existing_row else None,
                existing_manifest_hash=existing_row.manifest_hash if existing_row else None,
                incoming_install_state=install_state,
                incoming_manifest_hash=manifest_hash,
                allow_install_state_regression=allow_install_state_regression,
            )
            conn.execute(
                text(
                    """
                    INSERT INTO pack_activation_state (
                        pack_id, pack_family, enabled, install_state, migration_state,
                        activation_state, activation_mode, embedding_state,
                        embedding_error, embeddings_updated_at, manifest_hash,
                        registered_prefixes, last_error, activated_at, updated_at
                    )
                    VALUES (
                        :pack_id, :pack_family, :enabled, :install_state, :migration_state,
                        :activation_state, :activation_mode, :embedding_state,
                        :embedding_error, :embeddings_updated_at, :manifest_hash,
                        :registered_prefixes, :last_error, :activated_at, :updated_at
                    )
                    ON CONFLICT (pack_id) DO UPDATE SET
                        pack_family = EXCLUDED.pack_family,
                        enabled = EXCLUDED.enabled,
                        install_state = EXCLUDED.install_state,
                        migration_state = EXCLUDED.migration_state,
                        activation_state = EXCLUDED.activation_state,
                        activation_mode = EXCLUDED.activation_mode,
                        embedding_state = EXCLUDED.embedding_state,
                        embedding_error = EXCLUDED.embedding_error,
                        embeddings_updated_at = EXCLUDED.embeddings_updated_at,
                        manifest_hash = EXCLUDED.manifest_hash,
                        registered_prefixes = EXCLUDED.registered_prefixes,
                        last_error = EXCLUDED.last_error,
                        activated_at = EXCLUDED.activated_at,
                        updated_at = EXCLUDED.updated_at
                    """
                ),
                {
                    "pack_id": pack_id,
                    "pack_family": pack_family,
                    "enabled": enabled,
                    "install_state": install_state,
                    "migration_state": migration_state,
                    "activation_state": activation_state,
                    "activation_mode": activation_mode,
                    "embedding_state": embedding_state,
                    "embedding_error": embedding_error,
                    "embeddings_updated_at": embeddings_updated_at,
                    "manifest_hash": manifest_hash,
                    "registered_prefixes": self.serialize_json(
                        registered_prefixes or []
                    ),
                    "last_error": last_error,
                    "activated_at": activated_at,
                    "updated_at": updated_at,
                },
            )
        state = self.get_state(pack_id)
        if state is None:
            raise RuntimeError(f"Failed to persist activation state for {pack_id}")
        return state

    @classmethod
    def _resolve_install_state_for_upsert(
        cls,
        *,
        existing_install_state: Optional[str],
        existing_manifest_hash: Optional[str],
        incoming_install_state: str,
        incoming_manifest_hash: Optional[str],
        allow_install_state_regression: bool,
    ) -> str:
        if allow_install_state_regression:
            return incoming_install_state
        if incoming_install_state != "validation_pending":
            return incoming_install_state
        if existing_install_state not in cls._NON_REGRESSING_INSTALL_STATES:
            return incoming_install_state
        if not existing_manifest_hash or not incoming_manifest_hash:
            return incoming_install_state
        if existing_manifest_hash != incoming_manifest_hash:
            return incoming_install_state
        return existing_install_state
