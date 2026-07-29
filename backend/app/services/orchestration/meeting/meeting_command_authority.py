"""Server-owned authority carried from Meeting ingress to tool admission."""

from __future__ import annotations

from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field

from backend.app.dependencies.auth import AuthContext


SERVER_AUTHORITY_METADATA_KEY = "_mindscape_server_authority"


class MeetingCommandAuthority(BaseModel):
    """Bounded authority projection; callers never supply this structure."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    actor_user_id: str = Field(min_length=1, max_length=128)
    tenant_id: str = Field(min_length=1, max_length=128)
    workspace_id: str = Field(min_length=1, max_length=128)
    allowed_workspace_ids: tuple[str, ...] = Field(max_length=256)
    allowed_group_ids: tuple[str, ...] = Field(default=(), max_length=256)
    active_group_id: str | None = Field(default=None, max_length=128)
    auth_revision: str | None = Field(default=None, max_length=256)
    root_execution_id: str = Field(min_length=1, max_length=128)
    trace_id: str = Field(min_length=1, max_length=128)
    source: str = Field(min_length=1, max_length=64)


class MeetingCommandAuthorityError(ValueError):
    """Raised when a Meeting command lacks server-verifiable authority."""


def strip_server_authority(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    """Remove any caller attempt to provide protected authority."""

    normalized = dict(metadata or {})
    normalized.pop(SERVER_AUTHORITY_METADATA_KEY, None)
    return normalized


def build_authenticated_authority(
    *,
    auth: AuthContext,
    workspace_id: str,
    active_group_id: str | None,
    command_id: str,
) -> MeetingCommandAuthority:
    allowed_workspace_ids = tuple(
        sorted({str(item) for item in auth.workspace_ids if str(item).strip()})
    )
    if workspace_id not in allowed_workspace_ids:
        raise MeetingCommandAuthorityError(
            "meeting_command_workspace_outside_authenticated_scope"
        )
    return MeetingCommandAuthority(
        actor_user_id=auth.user_id,
        tenant_id=auth.tenant_id,
        workspace_id=workspace_id,
        allowed_workspace_ids=allowed_workspace_ids,
        allowed_group_ids=tuple(
            sorted({str(item) for item in auth.group_ids if str(item).strip()})
        ),
        active_group_id=active_group_id,
        auth_revision=auth.auth_revision,
        root_execution_id=f"meeting-command:{command_id}",
        trace_id=f"meeting-command:{command_id}",
        source="authenticated_route",
    )


def build_internal_workspace_authority(
    *,
    workspace_id: str,
    workspace_owner_user_id: str,
    active_group_id: str | None,
    command_id: str,
) -> MeetingCommandAuthority:
    """Build authority for trusted server voice adapters from loaded workspace truth."""

    actor_user_id = str(workspace_owner_user_id or "").strip()
    if not actor_user_id:
        raise MeetingCommandAuthorityError(
            "meeting_command_internal_workspace_owner_required"
        )
    return MeetingCommandAuthority(
        actor_user_id=actor_user_id,
        tenant_id="local",
        workspace_id=workspace_id,
        allowed_workspace_ids=(workspace_id,),
        allowed_group_ids=(),
        active_group_id=active_group_id,
        root_execution_id=f"meeting-command:{command_id}",
        trace_id=f"meeting-command:{command_id}",
        source="trusted_internal_workspace",
    )


def inject_server_authority(
    metadata: Mapping[str, Any] | None,
    authority: MeetingCommandAuthority,
) -> dict[str, Any]:
    return {
        **strip_server_authority(metadata),
        SERVER_AUTHORITY_METADATA_KEY: authority.model_dump(mode="json"),
    }


def read_server_authority(
    metadata: Mapping[str, Any] | None,
) -> MeetingCommandAuthority:
    raw = (metadata or {}).get(SERVER_AUTHORITY_METADATA_KEY)
    if not isinstance(raw, Mapping):
        raise MeetingCommandAuthorityError(
            "meeting_command_server_authority_required"
        )
    return MeetingCommandAuthority.model_validate(raw)


__all__ = [
    "MeetingCommandAuthority",
    "MeetingCommandAuthorityError",
    "SERVER_AUTHORITY_METADATA_KEY",
    "build_authenticated_authority",
    "build_internal_workspace_authority",
    "inject_server_authority",
    "read_server_authority",
    "strip_server_authority",
]
