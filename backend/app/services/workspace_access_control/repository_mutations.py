"""Invitation and grant transactions with revision and last-owner guards."""

from __future__ import annotations
from datetime import datetime
from uuid import uuid4
from sqlalchemy import text
from .repository_guards import AccessMutationGuardMixin
from .errors import (
    InvitationEmailMismatchError,
    InvitationExpiredError,
    InvitationInvalidError,
)


class AccessMutationRepositoryMixin(AccessMutationGuardMixin):
    def create_invitation(
        self,
        *,
        invitation_id: str,
        scope_type: str,
        scope_id: str,
        email: str,
        role_key: str,
        token_hash: str,
        expires_at: datetime,
        actor_principal_id: str,
        expected_revision: int,
    ) -> int:
        with self.transaction() as conn:
            revision = self._lock_scope(
                conn,
                scope_type=scope_type,
                scope_id=scope_id,
                expected_revision=expected_revision,
            )
            conn.execute(
                text(
                    """
                    INSERT INTO access_invitations
                        (id, scope_type, scope_id, email, role_key, token_hash,
                         status, expires_at, created_by)
                    VALUES
                        (:id, :scope_type, :scope_id, :email, :role_key,
                         :token_hash, 'pending', :expires_at, :actor)
                    """
                ),
                {
                    "id": invitation_id,
                    "scope_type": scope_type,
                    "scope_id": scope_id,
                    "email": email,
                    "role_key": role_key,
                    "token_hash": token_hash,
                    "expires_at": expires_at,
                    "actor": actor_principal_id,
                },
            )
            return self._record_mutation(
                conn,
                revision=revision,
                scope_type=scope_type,
                scope_id=scope_id,
                actor_principal_id=actor_principal_id,
                action="invitation.created",
                target_principal_id=None,
                metadata={"invitation_id": invitation_id},
            )

    def accept_invitation(
        self,
        *,
        token_hash: str,
        provider: str,
        issuer: str,
        subject: str,
        verified_email: str,
    ) -> dict:
        with self.transaction() as conn:
            invitation = conn.execute(
                text(
                    """
                    SELECT id, scope_type, scope_id, email, role_key,
                           status, expires_at
                    FROM access_invitations
                    WHERE token_hash = :token_hash
                    FOR UPDATE
                    """
                ),
                {"token_hash": token_hash},
            ).fetchone()
            self._validate_invitation(invitation, verified_email)
            binding = conn.execute(
                text(
                    """
                    SELECT principal_id
                    FROM access_identity_bindings
                    WHERE provider = :provider
                      AND issuer = :issuer
                      AND subject = :subject
                      AND status = 'active'
                    FOR UPDATE
                    """
                ),
                {"provider": provider, "issuer": issuer, "subject": subject},
            ).fetchone()
            principal_id = (
                str(binding.principal_id) if binding is not None else uuid4().hex
            )
            if binding is None:
                self._insert_principal_binding(
                    conn,
                    principal_id=principal_id,
                    provider=provider,
                    issuer=issuer,
                    subject=subject,
                    verified_email=verified_email,
                )
            conn.execute(
                text(
                    """
                    INSERT INTO access_grants
                        (id, principal_id, scope_type, scope_id, role_key,
                         status, created_by)
                    VALUES
                        (:id, :principal_id, :scope_type, :scope_id, :role_key,
                         'active', :principal_id)
                    ON CONFLICT (principal_id, scope_type, scope_id)
                        WHERE status = 'active'
                    DO UPDATE SET role_key = EXCLUDED.role_key,
                                  expires_at = NULL,
                                  updated_at = NOW()
                    """
                ),
                {
                    "id": uuid4().hex,
                    "principal_id": principal_id,
                    "scope_type": invitation.scope_type,
                    "scope_id": invitation.scope_id,
                    "role_key": invitation.role_key,
                },
            )
            revision = self._consume_invitation(
                conn,
                invitation_id=invitation.id,
                principal_id=principal_id,
                scope_type=invitation.scope_type,
                scope_id=invitation.scope_id,
            )
        return {
            "principal_id": principal_id,
            "scope_type": invitation.scope_type,
            "scope_id": invitation.scope_id,
            "role_key": invitation.role_key,
            "revision": revision,
        }

    def upsert_grant(
        self,
        *,
        principal_id: str,
        scope_type: str,
        scope_id: str,
        role_key: str,
        actor_principal_id: str,
        expected_revision: int,
    ) -> int:
        with self.transaction() as conn:
            revision = self._lock_scope(
                conn,
                scope_type=scope_type,
                scope_id=scope_id,
                expected_revision=expected_revision,
            )
            existing = self._lock_active_grant(
                conn,
                principal_id=principal_id,
                scope_type=scope_type,
                scope_id=scope_id,
            )
            if (
                scope_type == "workspace"
                and existing is not None
                and existing.role_key == "workspace_owner"
                and role_key != "workspace_owner"
            ):
                self._require_another_owner(conn, scope_id, principal_id)
            conn.execute(
                text(
                    """
                    INSERT INTO access_grants
                        (id, principal_id, scope_type, scope_id, role_key,
                         status, created_by)
                    VALUES
                        (:id, :principal_id, :scope_type, :scope_id, :role_key,
                         'active', :actor)
                    ON CONFLICT (principal_id, scope_type, scope_id)
                        WHERE status = 'active'
                    DO UPDATE SET role_key = EXCLUDED.role_key,
                                  expires_at = NULL,
                                  updated_at = NOW()
                    """
                ),
                {
                    "id": uuid4().hex,
                    "principal_id": principal_id,
                    "scope_type": scope_type,
                    "scope_id": scope_id,
                    "role_key": role_key,
                    "actor": actor_principal_id,
                },
            )
            return self._record_mutation(
                conn,
                revision=revision,
                scope_type=scope_type,
                scope_id=scope_id,
                actor_principal_id=actor_principal_id,
                action="grant.changed",
                target_principal_id=principal_id,
            )

    def revoke_grant(
        self,
        *,
        principal_id: str,
        scope_type: str,
        scope_id: str,
        actor_principal_id: str,
        expected_revision: int,
    ) -> int:
        with self.transaction() as conn:
            revision = self._lock_scope(
                conn,
                scope_type=scope_type,
                scope_id=scope_id,
                expected_revision=expected_revision,
            )
            existing = self._lock_active_grant(
                conn,
                principal_id=principal_id,
                scope_type=scope_type,
                scope_id=scope_id,
            )
            if existing is not None and existing.role_key == "workspace_owner":
                self._require_another_owner(conn, scope_id, principal_id)
            if (
                existing is not None
                and existing.role_key == "local_core_super_admin"
            ):
                self._require_another_local_core_super_admin(
                    conn,
                    principal_id,
                )
            conn.execute(
                text(
                    """
                    UPDATE access_grants
                    SET status = 'revoked', updated_at = NOW()
                    WHERE principal_id = :principal_id
                      AND scope_type = :scope_type
                      AND scope_id = :scope_id
                      AND status = 'active'
                    """
                ),
                {
                    "principal_id": principal_id,
                    "scope_type": scope_type,
                    "scope_id": scope_id,
                },
            )
            return self._record_mutation(
                conn,
                revision=revision,
                scope_type=scope_type,
                scope_id=scope_id,
                actor_principal_id=actor_principal_id,
                action="grant.revoked",
                target_principal_id=principal_id,
            )

    @staticmethod
    def _validate_invitation(invitation, verified_email: str) -> None:
        if invitation is None or invitation.status != "pending":
            raise InvitationInvalidError()
        now = datetime.now(invitation.expires_at.tzinfo)
        if invitation.expires_at <= now:
            raise InvitationExpiredError()
        if invitation.email.lower() != verified_email.lower():
            raise InvitationEmailMismatchError()

    @staticmethod
    def _insert_principal_binding(
        conn,
        *,
        principal_id: str,
        provider: str,
        issuer: str,
        subject: str,
        verified_email: str,
    ) -> None:
        conn.execute(
            text(
                """
                INSERT INTO access_principals
                    (id, principal_kind, display_email, status)
                VALUES (:id, 'human', :email, 'active')
                """
            ),
            {"id": principal_id, "email": verified_email},
        )
        conn.execute(
            text(
                """
                INSERT INTO access_identity_bindings
                    (id, principal_id, provider, issuer, subject,
                     verified_email, status)
                VALUES
                    (:id, :principal_id, :provider, :issuer, :subject,
                     :email, 'active')
                """
            ),
            {
                "id": uuid4().hex,
                "principal_id": principal_id,
                "provider": provider,
                "issuer": issuer,
                "subject": subject,
                "email": verified_email,
            },
        )

    @staticmethod
    def _consume_invitation(
        conn,
        *,
        invitation_id: str,
        principal_id: str,
        scope_type: str,
        scope_id: str,
    ) -> int:
        row = conn.execute(
            text(
                """
                WITH consumed AS (
                    UPDATE access_invitations
                    SET status = 'accepted',
                        accepted_principal_id = :principal_id,
                        accepted_at = NOW()
                    WHERE id = :invitation_id AND status = 'pending'
                    RETURNING id
                ),
                bumped AS (
                    UPDATE access_scope_policies
                    SET revision = revision + 1, updated_at = NOW()
                    WHERE scope_type = :scope_type AND scope_id = :scope_id
                      AND EXISTS (SELECT 1 FROM consumed)
                    RETURNING revision
                ),
                audited AS (
                    INSERT INTO access_audit_events
                        (id, scope_type, scope_id, actor_principal_id, action,
                         target_principal_id, metadata_json)
                    SELECT
                        :audit_id, :scope_type, :scope_id, :principal_id,
                        'invitation.accepted', :principal_id,
                        jsonb_build_object('invitation_id', :invitation_id)
                    FROM consumed
                    RETURNING id
                )
                SELECT revision FROM bumped
                """
            ),
            {
                "principal_id": principal_id,
                "invitation_id": invitation_id,
                "scope_type": scope_type,
                "scope_id": scope_id,
                "audit_id": uuid4().hex,
            },
        ).fetchone()
        if row is None:
            raise InvitationInvalidError()
        return int(row.revision)
