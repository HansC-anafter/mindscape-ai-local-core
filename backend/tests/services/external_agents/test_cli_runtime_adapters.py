from backend.app.services.external_agents.agents.claude_code_cli.adapter import (
    ClaudeCodeCLIAdapter,
)
from backend.app.services.external_agents.agents.codex_cli.adapter import (
    CodexCLIAdapter,
)


class _FakeDispatchManager:
    def __init__(self, expected_surface: str):
        self.expected_surface = expected_surface

    def has_connections(self, workspace_id=None, surface_type=None):
        assert surface_type == self.expected_surface
        return True


def test_codex_cli_adapter_reports_surface_ws_connection(monkeypatch):
    monkeypatch.setattr(
        "backend.app.routes.agent_websocket.get_agent_dispatch_manager",
        lambda: _FakeDispatchManager("codex_cli"),
    )

    detail = CodexCLIAdapter().get_availability_detail(workspace_id="ws-1")

    assert detail == {
        "available": True,
        "transport": "ws",
        "reason": "ws_connected",
    }


def test_claude_code_cli_adapter_reports_surface_ws_connection(monkeypatch):
    monkeypatch.setattr(
        "backend.app.routes.agent_websocket.get_agent_dispatch_manager",
        lambda: _FakeDispatchManager("claude_code_cli"),
    )

    detail = ClaudeCodeCLIAdapter().get_availability_detail(workspace_id="ws-1")

    assert detail == {
        "available": True,
        "transport": "ws",
        "reason": "ws_connected",
    }
