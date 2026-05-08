from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.app.routes.core.workspace_agents import (
    CodexAccountHomeTarget,
    WorkspaceAgentAuthActionRequest,
    get_workspace_agent_auth_status,
    list_workspace_agent_account_homes,
    login_workspace_agent,
    logout_workspace_agent,
)


@pytest.mark.asyncio
async def test_codex_auth_status_reports_authenticated(monkeypatch):
    workspace = SimpleNamespace(id="ws-1")

    async def _fake_resolve(workspace_id, agent_id):
        assert workspace_id == "ws-1"
        assert agent_id == "codex_cli"
        return object(), {
            "available": True,
            "transport": "ws",
            "reason": "ws_connected",
        }

    async def _fake_execute(workspace_obj, agent_id, control_action, inputs=None):
        assert workspace_obj is workspace
        assert agent_id == "codex_cli"
        assert control_action == "codex_login_status"
        return SimpleNamespace(success=True, output="Logged in as demo", error=None)

    monkeypatch.setattr(
        "backend.app.routes.core.workspace_agents._resolve_agent_availability",
        _fake_resolve,
    )
    monkeypatch.setattr(
        "backend.app.routes.core.workspace_agents._execute_agent_control",
        _fake_execute,
    )

    result = await get_workspace_agent_auth_status(
        workspace_id="ws-1",
        agent_id="codex_cli",
        workspace=workspace,
    )

    assert result.status == "authenticated"
    assert result.login_supported is True
    assert result.logout_supported is True


@pytest.mark.asyncio
async def test_claude_auth_status_is_explicitly_manual(monkeypatch):
    workspace = SimpleNamespace(id="ws-1")

    async def _fake_resolve(workspace_id, agent_id):
        return object(), {
            "available": True,
            "transport": "ws",
            "reason": "ws_connected",
        }

    monkeypatch.setattr(
        "backend.app.routes.core.workspace_agents._resolve_agent_availability",
        _fake_resolve,
    )

    result = await get_workspace_agent_auth_status(
        workspace_id="ws-1",
        agent_id="claude_code_cli",
        workspace=workspace,
    )

    assert result.status == "manual_required"
    assert result.manual_command == "claude setup-token"
    assert result.login_supported is False


@pytest.mark.asyncio
async def test_codex_login_route_rejects_no_target(monkeypatch):
    workspace = SimpleNamespace(id="ws-1")

    async def _fake_resolve(workspace_id, agent_id):
        return object(), {"available": True}

    monkeypatch.setattr(
        "backend.app.routes.core.workspace_agents._resolve_agent_availability",
        _fake_resolve,
    )

    with pytest.raises(HTTPException) as exc:
        await login_workspace_agent(
            workspace_id="ws-1",
            agent_id="codex_cli",
            workspace=workspace,
        )

    assert exc.value.status_code == 400
    assert "No-target login is disabled" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_codex_login_and_logout_routes_delegate_to_control_action(monkeypatch, tmp_path):
    workspace = SimpleNamespace(id="ws-1")
    account_home = tmp_path / "accounts" / "acct-a"
    seen_actions = []
    seen_inputs = []

    async def _fake_resolve(workspace_id, agent_id):
        return object(), {"available": True}

    async def _fake_execute(workspace_obj, agent_id, control_action, inputs=None):
        seen_actions.append(control_action)
        seen_inputs.append(inputs)
        return SimpleNamespace(success=True, output=f"ran:{control_action}", error=None)

    monkeypatch.setattr(
        "backend.app.routes.core.workspace_agents._resolve_agent_availability",
        _fake_resolve,
    )
    monkeypatch.setattr(
        "backend.app.routes.core.workspace_agents._execute_agent_control",
        _fake_execute,
    )

    login_result = await login_workspace_agent(
        workspace_id="ws-1",
        agent_id="codex_cli",
        payload=WorkspaceAgentAuthActionRequest(codex_home=str(account_home)),
        workspace=workspace,
    )
    logout_result = await logout_workspace_agent(
        workspace_id="ws-1",
        agent_id="codex_cli",
        payload=WorkspaceAgentAuthActionRequest(codex_home=str(account_home)),
        workspace=workspace,
    )

    assert seen_actions == ["codex_login", "codex_logout"]
    assert seen_inputs[0]["env"]["CODEX_HOME"] == str(account_home)
    assert seen_inputs[1]["env"]["CODEX_HOME"] == str(account_home)
    assert login_result.success is True
    assert logout_result.success is True


@pytest.mark.asyncio
async def test_codex_login_route_forwards_account_home_target(monkeypatch, tmp_path):
    workspace = SimpleNamespace(id="ws-1")
    account_home = tmp_path / "accounts" / "acct-a"
    seen = {}

    async def _fake_resolve(workspace_id, agent_id):
        return object(), {"available": True}

    async def _fake_execute(workspace_obj, agent_id, control_action, inputs=None):
        seen["control_action"] = control_action
        seen["inputs"] = inputs
        return SimpleNamespace(success=True, output="login", error=None)

    monkeypatch.setattr(
        "backend.app.routes.core.workspace_agents._resolve_agent_availability",
        _fake_resolve,
    )
    monkeypatch.setattr(
        "backend.app.routes.core.workspace_agents._execute_agent_control",
        _fake_execute,
    )

    result = await login_workspace_agent(
        workspace_id="ws-1",
        agent_id="codex_cli",
        payload=WorkspaceAgentAuthActionRequest(codex_home=str(account_home)),
        workspace=workspace,
    )

    assert result.success is True
    assert seen["control_action"] == "codex_login"
    assert seen["inputs"]["codex_home"] == str(account_home)
    assert seen["inputs"]["env"]["CODEX_HOME"] == str(account_home)


@pytest.mark.asyncio
async def test_codex_login_route_rejects_post_login_identity_mismatch(monkeypatch, tmp_path):
    workspace = SimpleNamespace(id="ws-1")
    account_home = tmp_path / "accounts" / "acct-a"

    async def _fake_resolve_available(workspace_id, agent_id):
        return object(), {"available": True}

    async def _fake_execute(workspace_obj, agent_id, control_action, inputs=None):
        return SimpleNamespace(success=True, output="Successfully logged in", error=None)

    monkeypatch.setattr(
        "backend.app.routes.core.workspace_agents._resolve_agent_availability",
        _fake_resolve_available,
    )
    monkeypatch.setattr(
        "backend.app.routes.core.workspace_agents._resolve_codex_account_home_inputs",
        lambda payload: {
            "codex_home": str(account_home),
            "expected_account_key": "expected-key",
            "expected_login_email": "agent@example.com",
            "env": {"CODEX_HOME": str(account_home)},
        },
    )
    monkeypatch.setattr(
        "backend.app.routes.core.workspace_agents._execute_agent_control",
        _fake_execute,
    )
    monkeypatch.setattr(
        "backend.app.services.codex_account_home_auth_source_service."
        "CodexAccountHomeAuthSourceService.metadata_for_codex_home",
        lambda codex_home: {
            "account_key": "actual-key",
            "login_email": "service@example.com",
        },
    )

    with pytest.raises(HTTPException) as exc:
        await login_workspace_agent(
            workspace_id="ws-1",
            agent_id="codex_cli",
            payload=WorkspaceAgentAuthActionRequest(codex_home=str(account_home)),
            workspace=workspace,
        )

    assert exc.value.status_code == 409
    assert "different account identity" in str(exc.value.detail)
    assert "expected-key" in str(exc.value.detail)
    assert "actual-key" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_codex_account_home_route_lists_targets(monkeypatch):
    workspace = SimpleNamespace(id="ws-1")

    monkeypatch.setattr(
        "backend.app.routes.core.workspace_agents._list_codex_account_home_targets",
        lambda: [
            CodexAccountHomeTarget(
                runtime_id="runtime-codex_cli-a",
                login_email="ai@example.com",
                account_key="acct-key",
                codex_home="/tmp/codex-home",
                has_access=True,
                has_refresh=True,
                probe_state="auth_failed",
                last_probe_error_code="stale_refresh_token",
            )
        ],
    )

    result = await list_workspace_agent_account_homes(
        workspace_id="ws-1",
        agent_id="codex_cli",
        workspace=workspace,
    )

    assert result.workspace_id == "ws-1"
    assert result.agent_id == "codex_cli"
    assert result.targets[0].runtime_id == "runtime-codex_cli-a"
    assert result.targets[0].last_probe_error_code == "stale_refresh_token"
