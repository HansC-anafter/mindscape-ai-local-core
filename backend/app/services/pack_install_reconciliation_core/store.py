"""Durable reconciliation state for committed pack installs."""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import text

from backend.app.services.stores.postgres_base import PostgresStoreBase


class PackInstallReconciliationStore(PostgresStoreBase):
    """Read and advance post-commit projection/cleanup receipts."""

    def get(self, install_id: str) -> Optional[dict[str, Any]]:
        with self.get_connection() as conn:
            row = (
                conn.execute(
                    text(
                        """
                        SELECT receipts.*, jobs.result_payload
                        FROM pack_install_commit_receipts AS receipts
                        JOIN capability_install_jobs AS jobs
                          ON jobs.install_id = receipts.install_id
                        WHERE receipts.install_id = :install_id
                        """
                    ),
                    {"install_id": install_id},
                )
                .mappings()
                .first()
            )
        return self._normalize(row) if row else None

    def next_due(self) -> Optional[dict[str, Any]]:
        with self.get_connection() as conn:
            row = (
                conn.execute(
                    text(
                        """
                        SELECT receipts.*, jobs.result_payload
                        FROM pack_install_commit_receipts AS receipts
                        JOIN capability_install_jobs AS jobs
                          ON jobs.install_id = receipts.install_id
                        WHERE (
                            receipts.projection_state <> 'succeeded'
                            OR receipts.filesystem_cleanup_state <> 'succeeded'
                        )
                          AND (
                            receipts.reconcile_not_before IS NULL
                            OR receipts.reconcile_not_before <= now()
                          )
                        ORDER BY receipts.committed_at ASC
                        LIMIT 1
                        """
                    )
                )
                .mappings()
                .first()
            )
        return self._normalize(row) if row else None

    def has_incomplete(self) -> bool:
        with self.get_connection() as conn:
            return bool(
                conn.execute(
                    text(
                        """
                        SELECT EXISTS (
                            SELECT 1
                            FROM pack_install_commit_receipts
                            WHERE projection_state <> 'succeeded'
                               OR filesystem_cleanup_state <> 'succeeded'
                        )
                        """
                    )
                ).scalar()
            )

    def mark_projection(
        self,
        install_id: str,
        *,
        succeeded: bool,
        error: Optional[str] = None,
    ) -> None:
        self._mark_step(
            install_id,
            state_column="projection_state",
            error_column="projection_error",
            succeeded=succeeded,
            error=error,
        )

    def mark_filesystem_cleanup(
        self,
        install_id: str,
        *,
        succeeded: bool,
        error: Optional[str] = None,
    ) -> None:
        self._mark_step(
            install_id,
            state_column="filesystem_cleanup_state",
            error_column="filesystem_cleanup_error",
            succeeded=succeeded,
            error=error,
        )

    def _mark_step(
        self,
        install_id: str,
        *,
        state_column: str,
        error_column: str,
        succeeded: bool,
        error: Optional[str],
    ) -> None:
        if state_column not in {"projection_state", "filesystem_cleanup_state"}:
            raise ValueError("install_reconciliation_state_column_invalid")
        if error_column not in {"projection_error", "filesystem_cleanup_error"}:
            raise ValueError("install_reconciliation_error_column_invalid")
        other_state_column = (
            "filesystem_cleanup_state"
            if state_column == "projection_state"
            else "projection_state"
        )
        state = "succeeded" if succeeded else "failed"
        retry_seconds = 30
        with self.transaction() as conn:
            row = conn.execute(
                text(
                    f"""
                    UPDATE pack_install_commit_receipts
                    SET {state_column} = :state,
                        {error_column} = :error,
                        reconcile_attempts = reconcile_attempts + 1,
                        reconcile_not_before = CASE
                            WHEN :succeeded THEN NULL
                            ELSE now() + (:retry_seconds || ' seconds')::interval
                        END,
                        reconciled_at = CASE
                            WHEN :succeeded
                             AND {other_state_column} = 'succeeded'
                            THEN now()
                            ELSE reconciled_at
                        END
                    WHERE install_id = :install_id
                    RETURNING install_id
                    """
                ),
                {
                    "install_id": install_id,
                    "state": state,
                    "error": (str(error or "")[:500] or None),
                    "succeeded": succeeded,
                    "retry_seconds": retry_seconds,
                },
            ).first()
            if row is None:
                raise RuntimeError("install_reconciliation_receipt_missing")

    def _normalize(self, row: Any) -> dict[str, Any]:
        item = dict(row)
        item["migration_receipt"] = self.deserialize_json(
            item.get("migration_receipt"),
            {},
        )
        item["commit_metadata"] = self.deserialize_json(
            item.get("commit_metadata"),
            {},
        )
        item["result_payload"] = self.deserialize_json(
            item.get("result_payload"),
            {},
        )
        for key in (
            "committed_at",
            "reconcile_not_before",
            "reconciled_at",
        ):
            value = item.get(key)
            if hasattr(value, "isoformat"):
                item[key] = value.isoformat()
        return item
