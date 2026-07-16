"""Commit pack installation truth and job terminal state in one transaction."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from sqlalchemy import text

from backend.app.services.stores.postgres_base import PostgresStoreBase


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PackInstallTruthCommitter(PostgresStoreBase):
    """Single writer for installed metadata, activation, receipt, and job success."""

    def commit(
        self,
        *,
        install_id: str,
        pack_id: str,
        version: str,
        manifest_hash: str,
        artifact_sha256: Optional[str],
        migration_receipt: Mapping[str, Any],
        commit_metadata: Mapping[str, Any],
        activation: Mapping[str, Any],
        result_payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        committed_at = _utc_now()
        commit_receipt = {
            "install_id": install_id,
            "pack_id": pack_id,
            "version": version,
            "manifest_hash": manifest_hash,
            "artifact_sha256": artifact_sha256,
            "committed_at": committed_at.isoformat(),
        }
        terminal_payload = dict(result_payload)
        terminal_payload["commit_receipt"] = commit_receipt
        terminal_payload["install_commit_receipt"] = {
            **dict(terminal_payload.get("install_commit_receipt") or {}),
            "install_id": install_id,
            "capability_code": pack_id,
            "state": "committed",
            "truth_committed": True,
        }
        with self.transaction() as conn:
            existing = conn.execute(
                text(
                    """
                    SELECT
                        pack_id,
                        version,
                        manifest_hash,
                        artifact_sha256,
                        committed_at
                    FROM pack_install_commit_receipts
                    WHERE install_id = :install_id
                    FOR UPDATE
                    """
                ),
                {"install_id": install_id},
            ).fetchone()
            if existing is not None and (
                existing.pack_id != pack_id
                or existing.version != version
                or existing.manifest_hash != manifest_hash
                or existing.artifact_sha256 != artifact_sha256
            ):
                raise RuntimeError("install_commit_receipt_idempotency_conflict")
            if existing is not None:
                terminal_state = conn.execute(
                    text(
                        """
                        SELECT state
                        FROM capability_install_jobs
                        WHERE install_id = :install_id
                        """
                    ),
                    {"install_id": install_id},
                ).scalar()
                if terminal_state != "succeeded":
                    raise RuntimeError("install_commit_terminal_state_mismatch")
                return {
                    "install_id": install_id,
                    "pack_id": existing.pack_id,
                    "version": existing.version,
                    "manifest_hash": existing.manifest_hash,
                    "artifact_sha256": existing.artifact_sha256,
                    "committed_at": existing.committed_at.isoformat(),
                }

            conn.execute(
                text(
                    """
                    INSERT INTO installed_packs (pack_id, installed_at, enabled, metadata)
                    VALUES (:pack_id, :committed_at, TRUE, CAST(:metadata AS JSONB))
                    ON CONFLICT (pack_id) DO UPDATE SET
                        installed_at = EXCLUDED.installed_at,
                        enabled = EXCLUDED.enabled,
                        metadata = EXCLUDED.metadata
                    """
                ),
                {
                    "pack_id": pack_id,
                    "committed_at": committed_at,
                    "metadata": self.serialize_json(dict(commit_metadata)),
                },
            )
            activation_payload = dict(activation)
            conn.execute(
                text(
                    """
                    INSERT INTO pack_activation_state (
                        pack_id, pack_family, enabled, install_state, migration_state,
                        activation_state, activation_mode, embedding_state,
                        embedding_error, embeddings_updated_at, manifest_hash,
                        registered_prefixes, last_error, activated_at, updated_at
                    ) VALUES (
                        :pack_id, :pack_family, TRUE, 'installed', :migration_state,
                        'active', :activation_mode, :embedding_state,
                        :embedding_error, :embeddings_updated_at, :manifest_hash,
                        CAST(:registered_prefixes AS JSONB), NULL, :activated_at, :updated_at
                    )
                    ON CONFLICT (pack_id) DO UPDATE SET
                        pack_family = EXCLUDED.pack_family,
                        enabled = TRUE,
                        install_state = 'installed',
                        migration_state = EXCLUDED.migration_state,
                        activation_state = 'active',
                        activation_mode = EXCLUDED.activation_mode,
                        embedding_state = EXCLUDED.embedding_state,
                        embedding_error = EXCLUDED.embedding_error,
                        embeddings_updated_at = EXCLUDED.embeddings_updated_at,
                        manifest_hash = EXCLUDED.manifest_hash,
                        registered_prefixes = EXCLUDED.registered_prefixes,
                        last_error = NULL,
                        activated_at = EXCLUDED.activated_at,
                        updated_at = EXCLUDED.updated_at
                    """
                ),
                {
                    "pack_id": pack_id,
                    "pack_family": activation_payload.get("pack_family") or pack_id,
                    "migration_state": activation_payload.get("migration_state")
                    or "applied",
                    "activation_mode": activation_payload.get("activation_mode")
                    or "install_commit",
                    "embedding_state": activation_payload.get("embedding_state")
                    or "not_required",
                    "embedding_error": activation_payload.get("embedding_error"),
                    "embeddings_updated_at": activation_payload.get(
                        "embeddings_updated_at"
                    ),
                    "manifest_hash": manifest_hash,
                    "registered_prefixes": self.serialize_json(
                        activation_payload.get("registered_prefixes") or []
                    ),
                    "activated_at": committed_at,
                    "updated_at": committed_at,
                },
            )
            conn.execute(
                text(
                    """
                    INSERT INTO pack_install_commit_receipts (
                        install_id, pack_id, version, manifest_hash, artifact_sha256,
                        migration_receipt, commit_metadata, committed_at
                    ) VALUES (
                        :install_id, :pack_id, :version, :manifest_hash, :artifact_sha256,
                        CAST(:migration_receipt AS JSONB), CAST(:commit_metadata AS JSONB),
                        :committed_at
                    )
                    ON CONFLICT (install_id) DO NOTHING
                    """
                ),
                {
                    "install_id": install_id,
                    "pack_id": pack_id,
                    "version": version,
                    "manifest_hash": manifest_hash,
                    "artifact_sha256": artifact_sha256,
                    "migration_receipt": self.serialize_json(dict(migration_receipt)),
                    "commit_metadata": self.serialize_json(dict(commit_metadata)),
                    "committed_at": committed_at,
                },
            )
            terminal = conn.execute(
                text(
                    """
                    UPDATE capability_install_jobs
                    SET state = 'succeeded',
                        result_payload = CAST(:result_payload AS JSONB),
                        error = NULL,
                        retry_after_seconds = NULL,
                        not_before = NULL,
                        finished_at = COALESCE(finished_at, :committed_at),
                        updated_at = :committed_at
                    WHERE install_id = :install_id
                    RETURNING install_id
                    """
                ),
                {
                    "install_id": install_id,
                    "result_payload": self.serialize_json(terminal_payload),
                    "committed_at": committed_at,
                },
            ).fetchone()
            if terminal is None:
                raise RuntimeError("capability_install_job_missing_during_truth_commit")
        return commit_receipt
