from types import SimpleNamespace

import pytest

from backend.app.routes.core.workspace_agents import (
    get_workspace_agent_auth_status,
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

    async def _fake_execute(workspace_obj, agent_id, control_action):
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
async def test_codex_login_and_logout_routes_delegate_to_control_action(monkeypatch):
    workspace = SimpleNamespace(id="ws-1")
    seen_actions = []

    async def _fake_resolve(workspace_id, agent_id):
        return object(), {"available": True}

    async def _fake_execute(workspace_obj, agent_id, control_action):
        seen_actions.append(control_action)
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
        workspace=workspace,
    )
    logout_result = await logout_workspace_agent(
        workspace_id="ws-1",
        agent_id="codex_cli",
        workspace=workspace,
    )

    assert seen_actions == ["codex_login", "codex_logout"]
    assert login_result.success is True
    assert logout_result.success is True
