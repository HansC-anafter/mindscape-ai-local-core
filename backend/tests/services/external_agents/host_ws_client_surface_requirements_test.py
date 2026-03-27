import pytest

from backend.app.services.external_agents.bridge.host_ws_client import (
    HostBridgeWSClient,
)
from backend.app.services.external_agents.bridge.runtime_adapter import (
    HostBridgeRuntimeAdapter,
)


def test_host_bridge_ws_client_requires_surface():
    with pytest.raises(ValueError, match="surface is required"):
        HostBridgeWSClient(workspace_id="ws-1", host="localhost:8200", surface="")


def test_codex_surface_preflight_does_not_require_gemini_bridge(monkeypatch):
    monkeypatch.delenv("GEMINI_CLI_RUNTIME_CMD", raising=False)
    monkeypatch.setenv("MINDSCAPE_BACKEND_API_URL", "http://localhost:8200")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    client = HostBridgeWSClient(
        workspace_id="ws-1",
        host="localhost:8200",
        surface="codex_cli",
    )

    client._preflight_check()


class _FakeWSManager:
    def __init__(self, results):
        self._results = list(results)
        self.calls = 0

    def has_connections(self, workspace_id=None, surface_type=None):
        self.calls += 1
        if not self._results:
            return False
        if len(self._results) == 1:
            return self._results[0]
        return self._results.pop(0)


def test_unavailable_availability_cache_expires_quickly_after_reconnect(monkeypatch):
    timeline = iter([100.0, 102.2])
    manager = _FakeWSManager([False, True])
    adapter = HostBridgeRuntimeAdapter(strategy="ws", ws_manager=manager)
    monkeypatch.setattr(
        "backend.app.services.external_agents.bridge.runtime_adapter.time.monotonic",
        lambda: next(timeline),
    )

    first = adapter.get_availability_detail(workspace_id="ws-1")
    second = adapter.get_availability_detail(workspace_id="ws-1")

    assert first == {
        "available": False,
        "transport": None,
        "reason": "no_ws_client",
    }
    assert second == {
        "available": True,
        "transport": "ws",
        "reason": "ws_connected",
    }
    assert manager.calls == 2
