"""Versioned system role catalog; callers consume permissions, never role names."""

from __future__ import annotations

from types import MappingProxyType


LOCAL_CORE_SETTINGS_MANAGE = "local_core.settings.manage"
LOCAL_CORE_WORKSPACES_CREATE = "local_core.workspaces.create"
LOCAL_CORE_ACCESS_MANAGE = "local_core.access.manage"
WORKSPACE_READ = "workspace.read"
WORKSPACE_CONTENT_WRITE = "workspace.content.write"
WORKSPACE_EXECUTE = "workspace.execute"
WORKSPACE_SETTINGS_MANAGE = "workspace.settings.manage"
WORKSPACE_MEMBERS_MANAGE = "workspace.members.manage"
WORKSPACE_AUDIT_READ = "workspace.audit.read"
WORKSPACE_OWNER_MANAGE = "workspace.owner.manage"
WORKSPACE_DELETE = "workspace.delete"

LOCAL_CORE_PERMISSIONS = frozenset(
    {
        LOCAL_CORE_SETTINGS_MANAGE,
        LOCAL_CORE_WORKSPACES_CREATE,
        LOCAL_CORE_ACCESS_MANAGE,
    }
)
WORKSPACE_PERMISSIONS = frozenset(
    {
        WORKSPACE_READ,
        WORKSPACE_CONTENT_WRITE,
        WORKSPACE_EXECUTE,
        WORKSPACE_SETTINGS_MANAGE,
        WORKSPACE_MEMBERS_MANAGE,
        WORKSPACE_AUDIT_READ,
        WORKSPACE_OWNER_MANAGE,
        WORKSPACE_DELETE,
    }
)
ALL_PERMISSIONS = LOCAL_CORE_PERMISSIONS | WORKSPACE_PERMISSIONS

ROLE_PERMISSIONS = MappingProxyType(
    {
        "local_core_super_admin": ALL_PERMISSIONS,
        "workspace_owner": WORKSPACE_PERMISSIONS,
        "workspace_admin": frozenset(
            {
                WORKSPACE_READ,
                WORKSPACE_CONTENT_WRITE,
                WORKSPACE_EXECUTE,
                WORKSPACE_SETTINGS_MANAGE,
                WORKSPACE_MEMBERS_MANAGE,
                WORKSPACE_AUDIT_READ,
            }
        ),
        "workspace_editor": frozenset(
            {
                WORKSPACE_READ,
                WORKSPACE_CONTENT_WRITE,
                WORKSPACE_EXECUTE,
            }
        ),
        "workspace_viewer": frozenset({WORKSPACE_READ}),
    }
)

ROLE_CATALOG_VERSION = "workspace-access-system-roles.v1"


def permissions_for_role(role_key: str) -> frozenset[str]:
    permissions = ROLE_PERMISSIONS.get(role_key)
    if permissions is None:
        raise ValueError("unknown_access_role")
    return permissions


def validate_role_scope(role_key: str, scope_type: str) -> None:
    permissions_for_role(role_key)
    if scope_type == "local_core" and role_key == "local_core_super_admin":
        return
    if scope_type == "workspace" and role_key.startswith("workspace_"):
        return
    raise ValueError("access_role_scope_mismatch")
