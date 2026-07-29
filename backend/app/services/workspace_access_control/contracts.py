"""Validated commands and compact projections for access control."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .catalog import validate_role_scope


ScopeType = Literal["local_core", "workspace"]


def normalize_email(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if (
        not normalized
        or len(normalized) > 320
        or normalized.count("@") != 1
        or "." not in normalized.rsplit("@", 1)[1]
    ):
        raise ValueError("invalid_invitation_email")
    return normalized


class VerifiedIdentity(BaseModel):
    provider: str = Field(min_length=1, max_length=64)
    issuer: str = Field(min_length=1, max_length=512)
    subject: str = Field(min_length=1, max_length=255)
    verified_email: str | None = Field(default=None, max_length=320)

    @field_validator("provider", "issuer", "subject")
    @classmethod
    def strip_required(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("identity_field_required")
        return normalized

    @field_validator("verified_email")
    @classmethod
    def normalize_verified_email(cls, value: str | None) -> str | None:
        return normalize_email(value) if value else None


class EffectiveAccessContext(BaseModel):
    principal_id: str | None
    workspace_id: str | None
    roles: tuple[str, ...] = ()
    permissions: frozenset[str] = frozenset()
    scope_revision: int = 0
    identity_bound: bool = False

    def allows(self, permission: str) -> bool:
        return permission in self.permissions


class InvitationCreateCommand(BaseModel):
    scope_type: ScopeType
    scope_id: str = Field(min_length=1, max_length=128)
    email: str = Field(min_length=3, max_length=320)
    role_key: str = Field(min_length=1, max_length=64)
    expected_revision: int = Field(ge=0)
    expires_in_days: int = Field(default=7, ge=1, le=30)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_email(value)

    def validate_semantics(self) -> None:
        validate_role_scope(self.role_key, self.scope_type)
        if self.scope_type == "local_core" and self.scope_id != "local-core":
            raise ValueError("invalid_local_core_scope")


class InvitationCreated(BaseModel):
    invitation_id: str
    invitation_token: str
    scope_type: ScopeType
    scope_id: str
    email: str
    role_key: str
    expires_at: datetime
    revision: int


class InvitationAcceptCommand(BaseModel):
    invitation_token: str = Field(min_length=32, max_length=512)


class GrantChangeCommand(BaseModel):
    principal_id: str = Field(min_length=1, max_length=64)
    scope_type: ScopeType
    scope_id: str = Field(min_length=1, max_length=128)
    role_key: str = Field(min_length=1, max_length=64)
    expected_revision: int = Field(ge=1)

    def validate_semantics(self) -> None:
        validate_role_scope(self.role_key, self.scope_type)


class ScopeAccessProjection(BaseModel):
    scope_type: ScopeType
    scope_id: str
    revision: int
    members: list[dict]
    invitations: list[dict]
    audit_events: list[dict]
    role_catalog_version: str
