import sys
from types import SimpleNamespace

import pytest

from backend.app.services.governance.playbook_preflight import PlaybookPreflight


class _FakeRegistry:
    def __init__(self, adapter):
        self.adapter = adapter

    def list_agents(self):
        return ["codex_cli"]

    def get_adapter(self, agent_id):
        assert agent_id == "codex_cli"
        return self.adapter


class _FakeAdapter:
    def __init__(self):
        self.workspace_ids = []

    async def is_available(self, workspace_id=None, **kwargs):
        self.workspace_ids.append(workspace_id)
        return workspace_id == "ws-target"


class _FakeDetailAdapter:
    def __init__(self, detail):
        self.detail = detail
        self.workspace_ids = []

    def get_availability_detail(self, workspace_id=None):
        self.workspace_ids.append(workspace_id)
        return dict(self.detail)

    async def is_available(self, workspace_id=None, **kwargs):
        raise AssertionError("availability detail should be used when present")


class _Settings:
    def get(self, key, default=None):
        if key == "governance.mode":
            return "permissive"
        return default


@pytest.mark.asyncio
async def test_agent_availability_uses_workspace_scoped_bridge(monkeypatch):
    adapter = _FakeAdapter()
    registry = _FakeRegistry(adapter)

    monkeypatch.setitem(
        sys.modules,
        "backend.app.services.external_agents.core.registry",
        SimpleNamespace(get_runtime_registry=lambda: registry),
    )

    preflight = PlaybookPreflight(settings_store=_Settings())
    available, error = await preflight._check_agent_availability(
        "codex_cli",
        workspace_id="ws-target",
    )

    assert available is True
    assert error is None
    assert adapter.workspace_ids == ["ws-target"]


@pytest.mark.asyncio
async def test_agent_availability_preserves_no_ws_client_retry_reason(monkeypatch):
    adapter = _FakeDetailAdapter({"available": False, "reason": "no_ws_client"})
    registry = _FakeRegistry(adapter)

    monkeypatch.setitem(
        sys.modules,
        "backend.app.services.external_agents.core.registry",
        SimpleNamespace(get_runtime_registry=lambda: registry),
    )

    preflight = PlaybookPreflight(settings_store=_Settings())
    available, error = await preflight._check_agent_availability(
        "codex_cli",
        workspace_id="ws-target",
    )

    assert available is False
    assert "No WebSocket client connected" in str(error)
    assert "--surface codex_cli" in str(error)
    assert adapter.workspace_ids == ["ws-target"]
