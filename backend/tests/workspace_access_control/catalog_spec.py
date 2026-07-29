import pytest

from backend.app.services.workspace_access_control.catalog import (
    ALL_PERMISSIONS,
    ROLE_CATALOG_VERSION,
    ROLE_PERMISSIONS,
    WORKSPACE_MEMBERS_MANAGE,
    WORKSPACE_OWNER_MANAGE,
    WORKSPACE_READ,
    permissions_for_role,
    validate_role_scope,
)


def test_role_catalog_is_fixed_and_permission_based():
    assert ROLE_CATALOG_VERSION == "workspace-access-system-roles.v1"
    assert set(ROLE_PERMISSIONS) == {
        "local_core_super_admin",
        "workspace_owner",
        "workspace_admin",
        "workspace_editor",
        "workspace_viewer",
    }
    assert permissions_for_role("local_core_super_admin") == ALL_PERMISSIONS
    assert permissions_for_role("workspace_viewer") == {WORKSPACE_READ}
    assert WORKSPACE_MEMBERS_MANAGE in permissions_for_role("workspace_admin")
    assert WORKSPACE_OWNER_MANAGE not in permissions_for_role("workspace_admin")


def test_unknown_and_cross_scope_roles_fail_closed():
    with pytest.raises(ValueError, match="unknown_access_role"):
        permissions_for_role("custom_role")
    with pytest.raises(ValueError, match="access_role_scope_mismatch"):
        validate_role_scope("workspace_owner", "local_core")
    with pytest.raises(ValueError, match="access_role_scope_mismatch"):
        validate_role_scope("local_core_super_admin", "workspace")
