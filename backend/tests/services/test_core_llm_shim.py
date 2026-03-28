from types import SimpleNamespace

import pytest

from backend.app.services.llm.core_llm import core_llm_call


@pytest.mark.asyncio
async def test_core_llm_call_delegates_to_workspace_runtime(monkeypatch):
    workspace = SimpleNamespace(
        id="ws-1",
        executor_runtime="codex_cli",
        resolved_executor_runtime="codex_cli",
        storage_base_path="/tmp/ws-1",
        sandbox_config={},
    )

    class _Store:
        async def get_workspace(self, workspace_id):
            assert workspace_id == "ws-1"
            return workspace

    class _Executor:
        last_call = None

        def __init__(self, bound_workspace):
            assert bound_workspace is workspace

        async def check_agent_available(self, agent_id):
            assert agent_id == "codex_cli"
            return True

        async def execute(self, **kwargs):
            _Executor.last_call = kwargs
            return SimpleNamespace(success=True, output='{"ok": true}', error=None)

    monkeypatch.setattr(
        "backend.app.services.stores.postgres.workspaces_store.PostgresWorkspacesStore",
        lambda: _Store(),
    )
    monkeypatch.setattr(
        "backend.app.services.workspace_agent_executor.WorkspaceAgentExecutor",
        _Executor,
    )

    result = await core_llm_call(
        system_prompt="system",
        user_message="user",
        response_format="json",
        workspace_id="ws-1",
    )

    assert result == {"ok": True}
    assert _Executor.last_call["agent_id"] == "codex_cli"
    assert _Executor.last_call["skip_preflight"] is True


@pytest.mark.asyncio
async def test_core_llm_call_requires_workspace_runtime(monkeypatch):
    class _Store:
        async def get_workspace(self, workspace_id):
            return None

    monkeypatch.setattr(
        "backend.app.services.stores.postgres.workspaces_store.PostgresWorkspacesStore",
        lambda: _Store(),
    )

    with pytest.raises(RuntimeError, match="hidden managed LLM fallback has been removed"):
        await core_llm_call(user_message="hello")
