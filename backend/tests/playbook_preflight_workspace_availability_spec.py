import sys
from types import SimpleNamespace

import pytest

from backend.app.services.governance.playbook_preflight import PlaybookPreflight
from backend.app.services.governance.stubs import PreflightStatus


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
    def __init__(self, mode="permissive"):
        self.mode = mode

    def get(self, key, default=None):
        if key == "governance.mode":
            return self.mode
        return default


def _workspace_with_primary_runtime(runtime_id="codex_cli"):
    return SimpleNamespace(
        id="ws-target",
        sandbox_config={},
        metadata={
            "model_routing_registry": {
                "executor_route_policy": {
                    "primary_executor_runtime": runtime_id,
                },
            },
        },
    )


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


@pytest.mark.asyncio
async def test_external_agent_preflight_rejects_unbound_workspace_runtime(monkeypatch):
    adapter = _FakeDetailAdapter({"available": True})
    registry = _FakeRegistry(adapter)

    monkeypatch.setitem(
        sys.modules,
        "backend.app.services.external_agents.core.registry",
        SimpleNamespace(get_runtime_registry=lambda: registry),
    )

    preflight = PlaybookPreflight(settings_store=_Settings(mode="strict"))
    result = await preflight.check_external_agent_execution(
        "codex_cli",
        "write a summary",
        _workspace_with_primary_runtime("gemini_cli"),
    )

    assert result.accepted is False
    assert result.status == PreflightStatus.REJECT
    assert "not in model-route-registry" in str(result.rejection_reason)
    assert adapter.workspace_ids == ["ws-target"]


@pytest.mark.asyncio
async def test_external_agent_preflight_requires_confirmation_for_high_risk_task(
    monkeypatch,
):
    adapter = _FakeDetailAdapter({"available": True})
    registry = _FakeRegistry(adapter)

    monkeypatch.setitem(
        sys.modules,
        "backend.app.services.external_agents.core.registry",
        SimpleNamespace(get_runtime_registry=lambda: registry),
    )

    preflight = PlaybookPreflight(settings_store=_Settings(mode="strict"))
    result = await preflight.check_external_agent_execution(
        "codex_cli",
        "delete generated files",
        _workspace_with_primary_runtime("codex_cli"),
    )

    assert result.accepted is False
    assert result.status == PreflightStatus.NEED_CLARIFICATION
    assert result.clarification_questions
    assert "HIGH risk level" in result.clarification_questions[0]


@pytest.mark.asyncio
async def test_meeting_agent_turn_preserves_risk_bypass(monkeypatch):
    adapter = _FakeDetailAdapter({"available": True})
    registry = _FakeRegistry(adapter)

    monkeypatch.setitem(
        sys.modules,
        "backend.app.services.external_agents.core.registry",
        SimpleNamespace(get_runtime_registry=lambda: registry),
    )

    preflight = PlaybookPreflight(settings_store=_Settings(mode="strict"))
    result = await preflight.check_external_agent_execution(
        "codex_cli",
        "[Meeting Agent Turn] delete historical context note",
        _workspace_with_primary_runtime("codex_cli"),
    )

    assert result.accepted is True
    assert result.status == PreflightStatus.ACCEPT
