from types import SimpleNamespace

import pytest

from backend.app.services.governance.playbook_preflight import PlaybookPreflight


class _SettingsStore:
    def get(self, key, default=None):
        return default


class _Registry:
    def __init__(self, adapter):
        self._adapter = adapter

    def list_agents(self):
        return ["codex_cli"]

    def get_adapter(self, agent_id):
        if agent_id == "codex_cli":
            return self._adapter
        return None


class _WorkspaceBoundAdapter:
    def __init__(self):
        self.calls = []

    def get_availability_detail(self, workspace_id=None):
        self.calls.append(workspace_id)
        if workspace_id == "ws-memory-engine-e2e-codex-054234":
            return {
                "available": True,
                "transport": "ws",
                "reason": "ws_connected",
            }
        return {
            "available": False,
            "transport": None,
            "reason": "no_surface_bridge",
        }


@pytest.mark.asyncio
async def test_external_agent_preflight_uses_workspace_bound_availability(monkeypatch):
    adapter = _WorkspaceBoundAdapter()
    registry = _Registry(adapter)

    monkeypatch.setattr(
        "backend.app.services.external_agents.core.registry.get_runtime_registry",
        lambda: registry,
    )

    preflight = PlaybookPreflight(settings_store=_SettingsStore())
    workspace = SimpleNamespace(
        id="ws-memory-engine-e2e-codex-054234",
        executor_runtime="codex_cli",
    )

    result = await preflight.check_external_agent_execution(
        agent_id="codex_cli",
        task="[Meeting Agent Turn]\nhello",
        workspace=workspace,
    )

    assert result.accepted is True
    assert adapter.calls == ["ws-memory-engine-e2e-codex-054234"]


@pytest.mark.asyncio
async def test_external_agent_preflight_reports_bridge_specific_unavailability(
    monkeypatch,
):
    adapter = _WorkspaceBoundAdapter()
    registry = _Registry(adapter)

    monkeypatch.setattr(
        "backend.app.services.external_agents.core.registry.get_runtime_registry",
        lambda: registry,
    )

    preflight = PlaybookPreflight(settings_store=_SettingsStore())
    workspace = SimpleNamespace(
        id="ws-without-bridge",
        executor_runtime="codex_cli",
    )

    result = await preflight.check_external_agent_execution(
        agent_id="codex_cli",
        task="[Meeting Agent Turn]\nhello",
        workspace=workspace,
    )

    assert result.accepted is False
    assert result.rejection_reason == (
        "Agent 'codex_cli' bridge is not connected for workspace 'ws-without-bridge'"
    )
