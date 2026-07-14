import asyncio

import pytest
from fastapi import HTTPException

from backend.app.dependencies import auth


class _Request:
    def __init__(self, headers=None):
        self.headers = headers or {}


def test_current_operator_authenticates_without_listing_local_workspaces(monkeypatch):
    default_user_reads = []
    workspace_reads = []
    monkeypatch.setattr(auth, "is_cloud_mode", lambda: False)
    monkeypatch.setattr(
        auth,
        "get_default_user_id",
        lambda: default_user_reads.append(True) or "default-user",
    )
    monkeypatch.setattr(
        auth,
        "_get_local_workspace_ids",
        lambda _user_id: workspace_reads.append(True) or ["ws-1"],
    )

    context = asyncio.run(auth.get_current_operator(_Request()))

    assert context.user_id == auth.LOCAL_CONTROL_OPERATOR_USER_ID
    assert context.tenant_id == "local"
    assert context.workspace_ids == []
    assert default_user_reads == []
    assert workspace_reads == []


def test_current_user_keeps_the_existing_workspace_projection(monkeypatch):
    monkeypatch.setattr(auth, "is_cloud_mode", lambda: False)
    monkeypatch.setattr(auth, "get_default_user_id", lambda: "local-user")
    monkeypatch.setattr(
        auth,
        "_get_local_workspace_ids",
        lambda user_id: [f"{user_id}-workspace"],
    )

    context = asyncio.run(auth.get_current_user(_Request()))

    assert context.workspace_ids == ["local-user-workspace"]


def test_current_operator_keeps_cloud_mode_fail_closed_without_a_token(monkeypatch):
    monkeypatch.setattr(auth, "is_cloud_mode", lambda: True)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(auth.get_current_operator(_Request()))

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Authorization header required in cloud mode"
