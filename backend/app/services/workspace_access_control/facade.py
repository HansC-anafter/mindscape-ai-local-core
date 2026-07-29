"""Application facade for access decisions and atomic management commands."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import secrets
from uuid import uuid4

from .catalog import (
    ROLE_CATALOG_VERSION,
    permissions_for_role,
    validate_role_scope,
)
from .contracts import (
    EffectiveAccessContext,
    GrantChangeCommand,
    InvitationCreateCommand,
    InvitationCreated,
    ScopeAccessProjection,
    VerifiedIdentity,
)
from .repository import WorkspaceAccessControlRepository
from .errors import InvitationInvalidError


class WorkspaceAccessControlFacade:
    """The sole human authorization reader and writer."""

    def __init__(
        self,
        repository: WorkspaceAccessControlRepository | None = None,
    ):
        self.repository = repository or WorkspaceAccessControlRepository()

    def bootstrap_local_state(self, *, local_user_id: str) -> dict[str, int | str]:
        principal_id = self.repository.ensure_local_recovery_owner(
            local_user_id=local_user_id
        )
        owners_created = self.repository.backfill_workspace_owners(
            actor_id=principal_id
        )
        return {
            "principal_id": principal_id,
            "workspace_owner_grants_created": owners_created,
        }

    def resolve_effective_access(
        self,
        *,
        identity: VerifiedIdentity,
        workspace_id: str | None,
    ) -> EffectiveAccessContext:
        state = self.repository.resolve_effective_access(
            provider=identity.provider,
            issuer=identity.issuer,
            subject=identity.subject,
            workspace_id=workspace_id,
        )
        roles = tuple(str(role) for role in state["roles"])
        permissions: set[str] = set()
        for role in roles:
            permissions.update(permissions_for_role(role))
        return EffectiveAccessContext(
            principal_id=state["principal_id"],
            workspace_id=workspace_id,
            roles=roles,
            permissions=frozenset(permissions),
            scope_revision=state["scope_revision"],
            identity_bound=state["principal_id"] is not None,
        )

    def list_authorized_workspace_ids(
        self,
        *,
        identity: VerifiedIdentity,
        limit: int = 200,
    ) -> list[str]:
        return self.repository.list_authorized_workspace_ids(
            provider=identity.provider,
            issuer=identity.issuer,
            subject=identity.subject,
            limit=limit,
        )

    def import_verified_grant(
        self,
        *,
        identity: VerifiedIdentity,
        scope_type: str,
        scope_id: str,
        role_key: str,
        actor_id: str,
    ) -> bool:
        validate_role_scope(role_key, scope_type)
        stable_key = "|".join(
            (
                identity.provider,
                identity.issuer,
                identity.subject,
            )
        )
        principal_id = sha256(
            f"principal|{stable_key}".encode("utf-8")
        ).hexdigest()
        binding_id = sha256(
            f"binding|{stable_key}".encode("utf-8")
        ).hexdigest()
        grant_id = sha256(
            (
                f"grant|{stable_key}|{scope_type}|{scope_id}|{role_key}"
            ).encode("utf-8")
        ).hexdigest()
        return self.repository.import_verified_grant(
            principal_id=principal_id,
            binding_id=binding_id,
            grant_id=grant_id,
            identity_provider=identity.provider,
            identity_issuer=identity.issuer,
            identity_subject=identity.subject,
            verified_email=identity.verified_email,
            scope_type=scope_type,
            scope_id=scope_id,
            role_key=role_key,
            actor_id=actor_id,
        )

    def read_scope(
        self,
        *,
        scope_type: str,
        scope_id: str,
        limit: int = 64,
    ) -> ScopeAccessProjection:
        state = self.repository.read_scope_projection(
            scope_type=scope_type,
            scope_id=scope_id,
            limit=min(max(limit, 1), 64),
        )
        return ScopeAccessProjection(
            scope_type=scope_type,
            scope_id=scope_id,
            revision=state["revision"],
            members=state["members"],
            invitations=state["invitations"],
            audit_events=state["audit_events"],
            role_catalog_version=ROLE_CATALOG_VERSION,
        )

    def read_remote_identity_projection(self, *, workspace_id: str) -> dict:
        projection = self.repository.read_remote_identity_projection(
            workspace_id=workspace_id
        )
        identities = []
        for identity in projection["identities"]:
            role_keys = tuple(identity.get("role_keys") or ())
            permissions: set[str] = set()
            for role_key in role_keys:
                permissions.update(permissions_for_role(str(role_key)))
            identities.append(
                {
                    **identity,
                    "role_keys": list(role_keys),
                    "permissions": sorted(permissions),
                }
            )
        return {
            "workspace_id": workspace_id,
            "revision": projection["revision"],
            "identities": identities,
            "role_catalog_version": ROLE_CATALOG_VERSION,
        }

    def create_invitation(
        self,
        *,
        command: InvitationCreateCommand,
        actor_principal_id: str,
    ) -> InvitationCreated:
        command.validate_semantics()
        raw_token = secrets.token_urlsafe(32)
        token_hash = sha256(raw_token.encode("utf-8")).hexdigest()
        invitation_id = uuid4().hex
        expires_at = datetime.now(timezone.utc) + timedelta(
            days=command.expires_in_days
        )
        revision = self.repository.create_invitation(
            invitation_id=invitation_id,
            scope_type=command.scope_type,
            scope_id=command.scope_id,
            email=command.email,
            role_key=command.role_key,
            token_hash=token_hash,
            expires_at=expires_at,
            actor_principal_id=actor_principal_id,
            expected_revision=command.expected_revision,
        )
        return InvitationCreated(
            invitation_id=invitation_id,
            invitation_token=raw_token,
            scope_type=command.scope_type,
            scope_id=command.scope_id,
            email=command.email,
            role_key=command.role_key,
            expires_at=expires_at,
            revision=revision,
        )

    def accept_invitation(
        self,
        *,
        raw_token: str,
        identity: VerifiedIdentity,
    ) -> dict:
        if not identity.verified_email:
            raise InvitationInvalidError("verified_email_required")
        token_hash = sha256(raw_token.encode("utf-8")).hexdigest()
        return self.repository.accept_invitation(
            token_hash=token_hash,
            provider=identity.provider,
            issuer=identity.issuer,
            subject=identity.subject,
            verified_email=identity.verified_email,
        )

    def change_grant(
        self,
        *,
        command: GrantChangeCommand,
        actor_principal_id: str,
    ) -> int:
        command.validate_semantics()
        return self.repository.upsert_grant(
            principal_id=command.principal_id,
            scope_type=command.scope_type,
            scope_id=command.scope_id,
            role_key=command.role_key,
            actor_principal_id=actor_principal_id,
            expected_revision=command.expected_revision,
        )

    def revoke_grant(
        self,
        *,
        principal_id: str,
        scope_type: str,
        scope_id: str,
        expected_revision: int,
        actor_principal_id: str,
    ) -> int:
        return self.repository.revoke_grant(
            principal_id=principal_id,
            scope_type=scope_type,
            scope_id=scope_id,
            actor_principal_id=actor_principal_id,
            expected_revision=expected_revision,
        )
