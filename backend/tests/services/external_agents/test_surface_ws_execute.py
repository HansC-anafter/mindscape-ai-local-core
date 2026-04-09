import pytest

from backend.app.services.external_agents.agents.claude_code_cli.adapter import (
    ClaudeCodeCLIAdapter,
)
from backend.app.services.external_agents.agents.codex_cli.adapter import (
    CodexCLIAdapter,
)
from backend.app.services.external_agents.core.base_adapter import RuntimeExecRequest


class _FakeWSManager:
    def __init__(
        self,
        expected_surface: str,
        expected_target_client_id: str | None = None,
    ):
        self.expected_surface = expected_surface
        self.expected_target_client_id = expected_target_client_id
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
        assert target_client_id == self.expected_target_client_id
        assert message["type"] == "dispatch"
        assert message["agent_id"] == self.expected_surface
        self.messages.append(message)
        return {
            "execution_id": execution_id,
            "status": "completed",
            "output": f"ok:{self.expected_surface}",
            "metadata": {"transport": "ws_push"},
        }


class _FlakyWSManager(_FakeWSManager):
    def __init__(self, expected_surface: str, availability_sequence):
        super().__init__(expected_surface)
        self._availability_sequence = list(availability_sequence)

    def has_connections(self, workspace_id=None, surface_type=None):
        assert workspace_id == "ws-1"
        assert surface_type == self.expected_surface
        if not self._availability_sequence:
            return False
        if len(self._availability_sequence) == 1:
            return self._availability_sequence[0]
        return self._availability_sequence.pop(0)


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


@pytest.mark.asyncio
async def test_surface_adapter_execute_propagates_target_client_id():
    adapter = CodexCLIAdapter(
        ws_manager=_FakeWSManager(
            "codex_cli",
            expected_target_client_id="client-e2e-001",
        )
    )

    response = await adapter.execute(
        RuntimeExecRequest(
            task="ping",
            sandbox_path="/tmp",
            workspace_id="ws-1",
            agent_config={"target_client_id": "client-e2e-001"},
        )
    )

    assert response.success is True


@pytest.mark.asyncio
async def test_surface_adapter_dispatch_includes_transport_inputs():
    ws_manager = _FakeWSManager("codex_cli")
    adapter = CodexCLIAdapter(ws_manager=ws_manager)

    response = await adapter.execute(
        RuntimeExecRequest(
            task="ping",
            sandbox_path="/tmp",
            workspace_id="ws-1",
            agent_config={
                "inputs": {
                    "deliverable_id": "D2",
                    "deliverable_name": "Week 1 calendar",
                    "deliverable_path": "instagram_week1_calendar.md",
                }
            },
        )
    )

    assert response.success is True
    assert ws_manager.messages[0]["context"]["inputs"]["deliverable_path"] == (
        "instagram_week1_calendar.md"
    )
    assert ws_manager.messages[0]["context"]["deliverable_path"] == (
        "instagram_week1_calendar.md"
    )


@pytest.mark.asyncio
async def test_surface_adapter_waits_for_recent_ws_reconnect(monkeypatch):
    adapter = CodexCLIAdapter(
        ws_manager=_FlakyWSManager("codex_cli", [False, False, True])
    )
    adapter._last_ws_connected_at["ws-1"] = 100.0
    adapter.WS_RECONNECT_GRACE_SECONDS = 5.0
    adapter.WS_RECONNECT_POLL_INTERVAL = 0.01

    monotonic_values = iter([101.0, 101.0, 101.1, 101.2, 101.3, 101.4])
    monkeypatch.setattr(
        "backend.app.services.external_agents.bridge.runtime_adapter.time.monotonic",
        lambda: next(monotonic_values),
    )

    response = await adapter.execute(
        RuntimeExecRequest(
            task="ping",
            sandbox_path="/tmp",
            workspace_id="ws-1",
        )
    )

    assert response.success is True
