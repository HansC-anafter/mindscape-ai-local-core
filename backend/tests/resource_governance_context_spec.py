from fastapi import HTTPException
import pytest

from backend.app.dependencies.auth import AuthContext
from backend.app.services.resource_governance.context import (
    build_resource_governance_context,
    require_workspace_resource_access,
)


def test_default_user_receives_global_resource_context():
    context = build_resource_governance_context(
        AuthContext(
            user_id="default_user",
            tenant_id="local",
            workspace_ids=["ws-1"],
        )
    )

    assert context["mode"] == "global"
    assert context["is_global_admin"] is True
    assert context["can_manage_global"] is True
    assert context["resource_control"]["can_register_host_slots"] is True


def test_workspace_user_is_scoped_to_own_workspace():
    context = build_resource_governance_context(
        AuthContext(
            user_id="member",
            tenant_id="tenant",
            workspace_ids=["ws-1"],
        ),
        workspace_id="ws-1",
    )

    assert context["mode"] == "workspace"
    assert context["is_global_admin"] is False
    assert context["workspace_id"] == "ws-1"
    assert context["can_manage_global"] is False


def test_workspace_access_rejects_foreign_workspace():
    with pytest.raises(HTTPException) as exc_info:
        require_workspace_resource_access(
            AuthContext(
                user_id="member",
                tenant_id="tenant",
                workspace_ids=["ws-1"],
            ),
            "ws-2",
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["reason"] == "workspace_resource_access_denied"
