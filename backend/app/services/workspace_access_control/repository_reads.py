"""Bounded single-statement effective and management projections."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text


_PRINCIPAL_CTE = """
WITH principal AS (
    SELECT binding.principal_id
    FROM access_identity_bindings AS binding
    JOIN access_principals AS principal
      ON principal.id = binding.principal_id
    WHERE binding.provider = :provider
      AND binding.issuer = :issuer
      AND binding.subject = :subject
      AND binding.status = 'active'
      AND principal.status = 'active'
    LIMIT 1
)
"""


class AccessReadRepositoryMixin:
    def resolve_effective_access(
        self,
        *,
        provider: str,
        issuer: str,
        subject: str,
        workspace_id: str | None,
    ) -> dict[str, Any]:
        sql = _PRINCIPAL_CTE + """
        , effective_grants AS (
            SELECT grant_row.role_key
            FROM access_grants AS grant_row
            JOIN principal
              ON principal.principal_id = grant_row.principal_id
            WHERE grant_row.status = 'active'
              AND (grant_row.expires_at IS NULL OR grant_row.expires_at > NOW())
              AND (
                  (grant_row.scope_type = 'local_core'
                   AND grant_row.scope_id = 'local-core')
                  OR (:workspace_id IS NOT NULL
                      AND grant_row.scope_type = 'workspace'
                      AND grant_row.scope_id = :workspace_id)
              )
        )
        SELECT
            (SELECT principal_id FROM principal) AS principal_id,
            COALESCE(
                (SELECT jsonb_agg(role_key ORDER BY role_key)
                 FROM effective_grants),
                '[]'::jsonb
            ) AS roles,
            COALESCE(
                (
                    SELECT revision
                    FROM access_scope_policies
                    WHERE scope_type = CASE
                        WHEN :workspace_id IS NULL THEN 'local_core'
                        ELSE 'workspace'
                    END
                      AND scope_id = COALESCE(:workspace_id, 'local-core')
                ),
                0
            ) AS scope_revision
        """
        with self.get_connection() as conn:
            row = conn.execute(
                text(sql),
                {
                    "provider": provider,
                    "issuer": issuer,
                    "subject": subject,
                    "workspace_id": workspace_id,
                },
            ).fetchone()
        return {
            "principal_id": getattr(row, "principal_id", None),
            "roles": self.deserialize_json(getattr(row, "roles", None), []),
            "scope_revision": int(getattr(row, "scope_revision", 0) or 0),
        }

    def list_authorized_workspace_ids(
        self,
        *,
        provider: str,
        issuer: str,
        subject: str,
        limit: int = 200,
    ) -> list[str]:
        sql = _PRINCIPAL_CTE + """
        , global_access AS (
            SELECT EXISTS (
                SELECT 1
                FROM access_grants AS grant_row
                JOIN principal
                  ON principal.principal_id = grant_row.principal_id
                WHERE grant_row.scope_type = 'local_core'
                  AND grant_row.scope_id = 'local-core'
                  AND grant_row.status = 'active'
                  AND (
                      grant_row.expires_at IS NULL
                      OR grant_row.expires_at > NOW()
                  )
            ) AS allowed
        )
        SELECT workspace.id
        FROM workspaces AS workspace
        CROSS JOIN global_access
        WHERE global_access.allowed
           OR EXISTS (
               SELECT 1
               FROM access_grants AS grant_row
               JOIN principal
                 ON principal.principal_id = grant_row.principal_id
               WHERE grant_row.scope_type = 'workspace'
                 AND grant_row.scope_id = workspace.id
                 AND grant_row.status = 'active'
                 AND (
                     grant_row.expires_at IS NULL
                     OR grant_row.expires_at > NOW()
                 )
           )
        ORDER BY workspace.updated_at DESC, workspace.id
        LIMIT :limit
        """
        with self.get_connection() as conn:
            rows = conn.execute(
                text(sql),
                {
                    "provider": provider,
                    "issuer": issuer,
                    "subject": subject,
                    "limit": limit,
                },
            ).fetchall()
        return [str(row.id) for row in rows]

    def read_scope_projection(
        self,
        *,
        scope_type: str,
        scope_id: str,
        limit: int,
    ) -> dict[str, Any]:
        with self.get_connection() as conn:
            row = conn.execute(
                text(_SCOPE_PROJECTION_SQL),
                {
                    "scope_type": scope_type,
                    "scope_id": scope_id,
                    "limit": limit,
                },
            ).fetchone()
        if row is None:
            return {
                "revision": 0,
                "members": [],
                "invitations": [],
                "audit_events": [],
            }
        return {
            "revision": int(row.revision),
            "members": self.deserialize_json(row.members, []),
            "invitations": self.deserialize_json(row.invitations, []),
            "audit_events": self.deserialize_json(row.audit_events, []),
        }

    def read_remote_identity_projection(self, *, workspace_id: str) -> dict[str, Any]:
        with self.get_connection() as conn:
            row = conn.execute(
                text(_REMOTE_IDENTITY_PROJECTION_SQL),
                {"workspace_id": workspace_id},
            ).fetchone()
        return {
            "identities": self.deserialize_json(row.identities, []),
            "revision": int(row.revision or 0),
        }


_SCOPE_PROJECTION_SQL = """
SELECT
    COALESCE(policy.revision, 0) AS revision,
    COALESCE(
        (
            SELECT jsonb_agg(member ORDER BY
                member ->> 'role_key', member ->> 'principal_id')
            FROM (
                SELECT jsonb_build_object(
                    'principal_id', principal.id,
                    'email', principal.display_email,
                    'role_key', grant_row.role_key,
                    'expires_at', grant_row.expires_at,
                    'identities', COALESCE(
                        (
                            SELECT jsonb_agg(jsonb_build_object(
                                'provider', binding.provider,
                                'issuer', binding.issuer,
                                'subject', binding.subject,
                                'verified_email', binding.verified_email
                            ) ORDER BY binding.provider, binding.issuer,
                                       binding.subject)
                            FROM access_identity_bindings AS binding
                            WHERE binding.principal_id = principal.id
                              AND binding.status = 'active'
                        ),
                        '[]'::jsonb
                    )
                ) AS member
                FROM access_grants AS grant_row
                JOIN access_principals AS principal
                  ON principal.id = grant_row.principal_id
                WHERE grant_row.scope_type = :scope_type
                  AND grant_row.scope_id = :scope_id
                  AND grant_row.status = 'active'
                  AND (
                      grant_row.expires_at IS NULL
                      OR grant_row.expires_at > NOW()
                  )
                ORDER BY grant_row.created_at, grant_row.id
                LIMIT :limit
            ) AS members
        ),
        '[]'::jsonb
    ) AS members,
    COALESCE(
        (
            SELECT jsonb_agg(invite ORDER BY invite ->> 'created_at' DESC)
            FROM (
                SELECT jsonb_build_object(
                    'invitation_id', invitation.id,
                    'email', invitation.email,
                    'role_key', invitation.role_key,
                    'status', invitation.status,
                    'expires_at', invitation.expires_at,
                    'created_at', invitation.created_at
                ) AS invite
                FROM access_invitations AS invitation
                WHERE invitation.scope_type = :scope_type
                  AND invitation.scope_id = :scope_id
                ORDER BY invitation.created_at DESC
                LIMIT :limit
            ) AS invitations
        ),
        '[]'::jsonb
    ) AS invitations,
    COALESCE(
        (
            SELECT jsonb_agg(event ORDER BY event ->> 'created_at' DESC)
            FROM (
                SELECT jsonb_build_object(
                    'event_id', audit.id,
                    'action', audit.action,
                    'actor_principal_id', audit.actor_principal_id,
                    'target_principal_id', audit.target_principal_id,
                    'created_at', audit.created_at
                ) AS event
                FROM access_audit_events AS audit
                WHERE audit.scope_type = :scope_type
                  AND audit.scope_id = :scope_id
                ORDER BY audit.created_at DESC
                LIMIT :limit
            ) AS events
        ),
        '[]'::jsonb
    ) AS audit_events
FROM access_scope_policies AS policy
WHERE policy.scope_type = :scope_type AND policy.scope_id = :scope_id
"""


_REMOTE_IDENTITY_PROJECTION_SQL = """
WITH eligible_grants AS (
    SELECT grant_row.principal_id, grant_row.role_key, grant_row.scope_type
    FROM access_grants AS grant_row
    JOIN access_principals AS principal
      ON principal.id = grant_row.principal_id
    WHERE grant_row.status = 'active'
      AND principal.status = 'active'
      AND (grant_row.expires_at IS NULL OR grant_row.expires_at > NOW())
      AND (
          (grant_row.scope_type = 'local_core'
           AND grant_row.scope_id = 'local-core')
          OR (grant_row.scope_type = 'workspace'
              AND grant_row.scope_id = :workspace_id)
      )
),
identities AS (
    SELECT
        binding.provider,
        binding.issuer,
        binding.subject,
        binding.verified_email,
        binding.principal_id,
        jsonb_agg(DISTINCT eligible.role_key
                  ORDER BY eligible.role_key) AS role_keys,
        bool_or(eligible.scope_type = 'local_core') AS global_access
    FROM eligible_grants AS eligible
    JOIN access_identity_bindings AS binding
      ON binding.principal_id = eligible.principal_id
     AND binding.status = 'active'
    GROUP BY
        binding.provider, binding.issuer, binding.subject,
        binding.verified_email, binding.principal_id
)
SELECT
    COALESCE(
        (
            SELECT jsonb_agg(jsonb_build_object(
                'provider', provider,
                'issuer', issuer,
                'subject', subject,
                'verified_email', verified_email,
                'principal_id', principal_id,
                'role_keys', role_keys,
                'global_access', global_access
            ) ORDER BY issuer, subject)
            FROM identities
        ),
        '[]'::jsonb
    ) AS identities,
    COALESCE(
        (
            SELECT revision
            FROM access_scope_policies
            WHERE scope_type = 'workspace' AND scope_id = :workspace_id
        ),
        0
    ) AS revision
"""
