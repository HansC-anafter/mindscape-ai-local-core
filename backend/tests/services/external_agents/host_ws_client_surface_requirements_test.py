import pytest

from backend.app.services.external_agents.bridge.host_ws_client import (
    HostBridgeWSClient,
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
