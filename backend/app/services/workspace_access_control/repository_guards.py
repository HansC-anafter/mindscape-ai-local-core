"""Revision, active-grant, last-owner, and audit mutation primitives."""

from uuid import uuid4

from sqlalchemy import text

from .errors import (
    AccessRevisionConflictError,
    LastAdministratorError,
    LastOwnerError,
)


class AccessMutationGuardMixin:
    @staticmethod
    def _lock_scope(
        conn,
        *,
        scope_type: str,
        scope_id: str,
        expected_revision: int,
    ) -> int:
        row = conn.execute(
            text(
                """
                SELECT revision FROM access_scope_policies
                WHERE scope_type = :scope_type AND scope_id = :scope_id
                FOR UPDATE
                """
            ),
            {"scope_type": scope_type, "scope_id": scope_id},
        ).fetchone()
        if row is None:
            if expected_revision != 0:
                raise AccessRevisionConflictError()
            conn.execute(
                text(
                    """
                    INSERT INTO access_scope_policies
                        (scope_type, scope_id, revision)
                    VALUES (:scope_type, :scope_id, 1)
                    """
                ),
                {"scope_type": scope_type, "scope_id": scope_id},
            )
            return 1
        revision = int(row.revision)
        if revision != expected_revision:
            raise AccessRevisionConflictError()
        return revision

    @staticmethod
    def _lock_active_grant(
        conn,
        *,
        principal_id: str,
        scope_type: str,
        scope_id: str,
    ):
        return conn.execute(
            text(
                """
                SELECT role_key FROM access_grants
                WHERE principal_id = :principal_id
                  AND scope_type = :scope_type
                  AND scope_id = :scope_id
                  AND status = 'active'
                FOR UPDATE
                """
            ),
            {
                "principal_id": principal_id,
                "scope_type": scope_type,
                "scope_id": scope_id,
            },
        ).fetchone()

    @staticmethod
    def _require_another_owner(conn, scope_id: str, principal_id: str) -> None:
        count = conn.execute(
            text(
                """
                SELECT COUNT(*) FROM access_grants
                WHERE scope_type = 'workspace'
                  AND scope_id = :scope_id
                  AND role_key = 'workspace_owner'
                  AND status = 'active'
                  AND principal_id <> :principal_id
                  AND (expires_at IS NULL OR expires_at > NOW())
                """
            ),
            {"scope_id": scope_id, "principal_id": principal_id},
        ).scalar_one()
        if int(count) < 1:
            raise LastOwnerError()

    @staticmethod
    def _require_another_local_core_super_admin(
        conn,
        principal_id: str,
    ) -> None:
        count = conn.execute(
            text(
                """
                SELECT COUNT(*) FROM access_grants
                WHERE scope_type = 'local_core'
                  AND scope_id = 'local-core'
                  AND role_key = 'local_core_super_admin'
                  AND status = 'active'
                  AND principal_id <> :principal_id
                  AND (expires_at IS NULL OR expires_at > NOW())
                """
            ),
            {"principal_id": principal_id},
        ).scalar_one()
        if int(count) < 1:
            raise LastAdministratorError()

    def _record_mutation(
        self,
        conn,
        *,
        revision: int,
        scope_type: str,
        scope_id: str,
        actor_principal_id: str,
        action: str,
        target_principal_id: str | None,
        metadata: dict | None = None,
    ) -> int:
        new_revision = revision + 1
        conn.execute(
            text(
                """
                WITH bumped AS (
                    UPDATE access_scope_policies
                    SET revision = :revision, updated_at = NOW()
                    WHERE scope_type = :scope_type AND scope_id = :scope_id
                    RETURNING revision
                )
                INSERT INTO access_audit_events
                    (id, scope_type, scope_id, actor_principal_id, action,
                     target_principal_id, metadata_json)
                SELECT
                    :id, :scope_type, :scope_id, :actor, :action, :target,
                    CAST(:metadata AS jsonb)
                FROM bumped
                """
            ),
            {
                "revision": new_revision,
                "scope_type": scope_type,
                "scope_id": scope_id,
                "id": uuid4().hex,
                "actor": actor_principal_id,
                "action": action,
                "target": target_principal_id,
                "metadata": self.serialize_json(metadata or {}),
            },
        )
        return new_revision
