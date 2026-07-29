"""Identity, local-owner bootstrap, and provider-adapter import writes."""

from sqlalchemy import text


class AccessIdentityRepositoryMixin:
    def ensure_local_recovery_owner(self, *, local_user_id: str) -> str:
        principal_id = f"local-{local_user_id}"
        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO access_principals
                        (id, principal_kind, display_email, status)
                    VALUES (:principal_id, 'local', NULL, 'active')
                    ON CONFLICT (id) DO UPDATE
                    SET status = 'active', updated_at = NOW()
                    """
                ),
                {"principal_id": principal_id},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO access_identity_bindings
                        (id, principal_id, provider, issuer, subject, status)
                    VALUES
                        (:binding_id, :principal_id, 'local', 'local-core',
                         :subject, 'active')
                    ON CONFLICT (provider, issuer, subject) DO UPDATE
                    SET principal_id = EXCLUDED.principal_id, status = 'active'
                    """
                ),
                {
                    "binding_id": f"local-binding-{local_user_id}",
                    "principal_id": principal_id,
                    "subject": local_user_id,
                },
            )
            conn.execute(
                text(
                    """
                    INSERT INTO access_scope_policies
                        (scope_type, scope_id, revision)
                    VALUES ('local_core', 'local-core', 1)
                    ON CONFLICT (scope_type, scope_id) DO NOTHING
                    """
                )
            )
            conn.execute(
                text(
                    """
                    INSERT INTO access_grants
                        (id, principal_id, scope_type, scope_id, role_key,
                         status, created_by)
                    VALUES
                        (:grant_id, :principal_id, 'local_core', 'local-core',
                         'local_core_super_admin', 'active', 'host-bootstrap')
                    ON CONFLICT (principal_id, scope_type, scope_id)
                        WHERE status = 'active'
                    DO UPDATE SET role_key = EXCLUDED.role_key,
                                  expires_at = NULL,
                                  updated_at = NOW()
                    """
                ),
                {
                    "grant_id": f"local-grant-{local_user_id}",
                    "principal_id": principal_id,
                },
            )
        return principal_id

    def backfill_workspace_owners(self, *, actor_id: str) -> int:
        with self.transaction() as conn:
            rows = conn.execute(
                text(
                    """
                    WITH owners AS (
                        SELECT id AS workspace_id, owner_user_id
                        FROM workspaces
                        WHERE COALESCE(owner_user_id, '') <> ''
                    ),
                    principals AS (
                        INSERT INTO access_principals
                            (id, principal_kind, status)
                        SELECT 'local-' || owner_user_id, 'local', 'active'
                        FROM owners GROUP BY owner_user_id
                        ON CONFLICT (id) DO UPDATE
                        SET status = 'active', updated_at = NOW()
                    ),
                    bindings AS (
                        INSERT INTO access_identity_bindings
                            (id, principal_id, provider, issuer, subject, status)
                        SELECT
                            'local-binding-' || owner_user_id,
                            'local-' || owner_user_id,
                            'local',
                            'local-core',
                            owner_user_id,
                            'active'
                        FROM owners GROUP BY owner_user_id
                        ON CONFLICT (provider, issuer, subject) DO UPDATE
                        SET principal_id = EXCLUDED.principal_id,
                            status = 'active'
                    ),
                    policies AS (
                        INSERT INTO access_scope_policies
                            (scope_type, scope_id, revision)
                        SELECT 'workspace', workspace_id, 1 FROM owners
                        ON CONFLICT (scope_type, scope_id) DO NOTHING
                    )
                    INSERT INTO access_grants
                        (id, principal_id, scope_type, scope_id, role_key,
                         status, created_by)
                    SELECT
                        md5('owner:' || owner_user_id || ':' || workspace_id),
                        'local-' || owner_user_id,
                        'workspace',
                        workspace_id,
                        'workspace_owner',
                        'active',
                        :actor_id
                    FROM owners
                    ON CONFLICT (principal_id, scope_type, scope_id)
                        WHERE status = 'active'
                    DO NOTHING
                    RETURNING id
                    """
                ),
                {"actor_id": actor_id},
            ).fetchall()
        return len(rows)

    def import_verified_grant(
        self,
        *,
        principal_id: str,
        binding_id: str,
        grant_id: str,
        identity_provider: str,
        identity_issuer: str,
        identity_subject: str,
        verified_email: str | None,
        scope_type: str,
        scope_id: str,
        role_key: str,
        actor_id: str,
    ) -> bool:
        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO access_principals
                        (id, principal_kind, display_email, status)
                    VALUES (:id, 'human', :email, 'active')
                    ON CONFLICT (id) DO UPDATE
                    SET display_email = COALESCE(
                            EXCLUDED.display_email,
                            access_principals.display_email
                        ),
                        status = 'active',
                        updated_at = NOW()
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
                    ON CONFLICT (provider, issuer, subject) DO UPDATE
                    SET verified_email = COALESCE(
                            EXCLUDED.verified_email,
                            access_identity_bindings.verified_email
                        ),
                        status = 'active'
                    """
                ),
                {
                    "id": binding_id,
                    "principal_id": principal_id,
                    "provider": identity_provider,
                    "issuer": identity_issuer,
                    "subject": identity_subject,
                    "email": verified_email,
                },
            )
            conn.execute(
                text(
                    """
                    INSERT INTO access_scope_policies
                        (scope_type, scope_id, revision)
                    VALUES (:scope_type, :scope_id, 1)
                    ON CONFLICT (scope_type, scope_id) DO NOTHING
                    """
                ),
                {"scope_type": scope_type, "scope_id": scope_id},
            )
            result = conn.execute(
                text(
                    """
                    INSERT INTO access_grants
                        (id, principal_id, scope_type, scope_id, role_key,
                         status, created_by)
                    VALUES
                        (:id, :principal_id, :scope_type, :scope_id, :role_key,
                         'active', :actor_id)
                    ON CONFLICT (principal_id, scope_type, scope_id)
                        WHERE status = 'active'
                    DO NOTHING
                    RETURNING id
                    """
                ),
                {
                    "id": grant_id,
                    "principal_id": principal_id,
                    "scope_type": scope_type,
                    "scope_id": scope_id,
                    "role_key": role_key,
                    "actor_id": actor_id,
                },
            ).fetchone()
        return result is not None
