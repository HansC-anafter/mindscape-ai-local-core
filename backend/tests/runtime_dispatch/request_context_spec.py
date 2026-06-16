import pytest
from fastapi import HTTPException

from backend.app.dependencies.auth import AuthContext
from backend.app.services.resource_governance import context as governance_context
from backend.app.services.runtime_dispatch.contracts import (
    build_dispatch_request_context,
)


def test_dispatch_request_context_carries_actor_workspace_trace_and_scope():
    context = build_dispatch_request_context(
        AuthContext(
            user_id="default_user",
            tenant_id="local",
            workspace_ids=["ws-a"],
        ),
        workspace_id="ws-a",
        trace_id="trace-1",
        source_surface="settings_host_resources",
        reason="operator_preview",
    )

    assert context.actor_id == "default_user"
    assert context.workspace_id == "ws-a"
    assert context.trace_id == "trace-1"
    assert context.source_surface == "settings_host_resources"
    assert context.reason == "operator_preview"
    assert context.auth_scope["workspace_id"] == "ws-a"
    assert context.auth_scope["scope"] == "workspace"


def test_dispatch_request_context_rejects_workspace_mismatch(monkeypatch):
    monkeypatch.setattr(governance_context, "get_default_user_id", lambda: "default_user")

    with pytest.raises(HTTPException) as exc_info:
        build_dispatch_request_context(
            AuthContext(
                user_id="limited-user",
                tenant_id="local",
                workspace_ids=["ws-a"],
            ),
            workspace_id="ws-b",
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["reason"] == "workspace_resource_access_denied"
