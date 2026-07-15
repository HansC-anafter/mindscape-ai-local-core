import asyncio

import pytest
from fastapi import HTTPException

from backend.app.dependencies import auth
from backend.app.services import mindscape_store, system_settings_store


class _Request:
    def __init__(self, headers=None):
        self.headers = headers or {}


def test_default_user_fallback_matches_the_canonical_local_profile(monkeypatch):
    class _Store:
        db_path = "/tmp/test.db"

    class _Settings:
        def __init__(self, *, db_path):
            assert db_path == _Store.db_path

        def get_setting(self, key):
            assert key == "default_user_id"
            return None

    monkeypatch.setattr(mindscape_store, "MindscapeStore", _Store)
    monkeypatch.setattr(system_settings_store, "SystemSettingsStore", _Settings)

    assert auth.get_default_user_id() == "default-user"


def test_configured_default_user_keeps_precedence(monkeypatch):
    class _Store:
        db_path = "/tmp/test.db"

    class _Setting:
        value = "configured-local-user"

    class _Settings:
        def __init__(self, *, db_path):
            assert db_path == _Store.db_path

        def get_setting(self, key):
            assert key == "default_user_id"
            return _Setting()

    monkeypatch.setattr(mindscape_store, "MindscapeStore", _Store)
    monkeypatch.setattr(system_settings_store, "SystemSettingsStore", _Settings)

    assert auth.get_default_user_id() == "configured-local-user"


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


def test_current_operator_cloud_mode_fails_closed_before_token_network(
    monkeypatch,
):
    token_reads = []
    monkeypatch.setattr(auth, "is_cloud_mode", lambda: True)
    monkeypatch.setattr(
        auth,
        "get_auth_from_cloud_integration_token",
        lambda _token: token_reads.append(True),
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            auth.get_current_operator(
                _Request({"Authorization": "Bearer should-not-be-read"})
            )
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "cloud_operator_role_required"
    assert token_reads == []


@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost:8300",
        "https://localhost",
        "http://127.0.0.1:8220",
        "https://[::1]:8300",
    ],
)
def test_current_operator_accepts_loopback_browser_origins(
    monkeypatch,
    origin,
):
    monkeypatch.setattr(auth, "is_cloud_mode", lambda: False)

    context = asyncio.run(
        auth.get_current_operator(_Request({"Origin": origin}))
    )

    assert context.user_id == auth.LOCAL_CONTROL_OPERATOR_USER_ID
    assert context.workspace_ids == []


@pytest.mark.parametrize(
    "origin",
    [
        "chrome-extension://abcdefghijklmnop",
        "http://192.168.1.20:8300",
        "https://remote-workbench.mindscapeai.app",
        "http://127.0.0.2:8300",
        "http://localhost:8300/path",
        "http://user@localhost:8300",
        "http://localhost:invalid",
        "null",
        "",
    ],
)
def test_current_operator_rejects_non_loopback_or_invalid_browser_origins(
    monkeypatch,
    origin,
):
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

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(auth.get_current_operator(_Request({"Origin": origin})))

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "local_operator_origin_forbidden"
    assert default_user_reads == []
    assert workspace_reads == []


def test_current_user_keeps_cloud_token_authentication(monkeypatch):
    token_reads = []
    expected = auth.AuthContext(
        user_id="cloud-user",
        tenant_id="cloud-tenant",
        workspace_ids=["ws-1"],
        is_cloud_mode=True,
    )

    async def read_token(token):
        token_reads.append(token)
        return expected

    monkeypatch.setattr(auth, "is_cloud_mode", lambda: True)
    monkeypatch.setattr(
        auth,
        "get_auth_from_cloud_integration_token",
        read_token,
    )

    context = asyncio.run(
        auth.get_current_user(_Request({"Authorization": "Bearer valid"}))
    )

    assert context == expected
    assert token_reads == ["valid"]
