import pytest

from backend.app.services.external_agents.agents.claude_code_cli.adapter import (
    ClaudeCodeCLIAdapter,
)
from backend.app.services.external_agents.agents.codex_cli.adapter import (
    CodexCLIAdapter,
)
from backend.app.services.external_agents.core.base_adapter import RuntimeExecRequest


class _FakeWSManager:
    def __init__(self, expected_surface: str):
        self.expected_surface = expected_surface
        self.messages = []

    def has_connections(self, workspace_id=None, surface_type=None):
        assert workspace_id == "ws-1"
        assert surface_type == self.expected_surface
        return True

    async def dispatch_and_wait(
        self,
        workspace_id,
        message,
        execution_id,
        timeout,
        target_client_id=None,
    ):
        assert workspace_id == "ws-1"
        assert target_client_id is None
        assert message["type"] == "dispatch"
        assert message["agent_id"] == self.expected_surface
        self.messages.append(message)
        return {
            "execution_id": execution_id,
            "status": "completed",
            "output": f"ok:{self.expected_surface}",
            "metadata": {"transport": "ws_push"},
        }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("adapter_cls", "surface"),
    [
        (CodexCLIAdapter, "codex_cli"),
        (ClaudeCodeCLIAdapter, "claude_code_cli"),
    ],
)
async def test_surface_adapter_execute_uses_surface_specific_ws_dispatch(
    adapter_cls,
    surface,
):
    adapter = adapter_cls(ws_manager=_FakeWSManager(surface))

    response = await adapter.execute(
        RuntimeExecRequest(
            task="ping",
            sandbox_path="/tmp",
            workspace_id="ws-1",
        )
    )

    assert response.success is True
    assert response.output == f"ok:{surface}"
    assert response.agent_metadata["transport"] == "ws_push"
