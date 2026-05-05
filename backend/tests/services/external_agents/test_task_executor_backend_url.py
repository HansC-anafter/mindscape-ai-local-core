from backend.app.services.external_agents.bridge.task_executor import (
    ExecutionContext,
    ExecutionResult,
    HostBridgeTaskExecutor,
)


def test_resolve_backend_api_url_prefers_explicit_env(monkeypatch):
    monkeypatch.setenv("MINDSCAPE_BACKEND_API_URL", "http://localhost:8200/")
    monkeypatch.delenv("MINDSCAPE_WS_HOST", raising=False)

    assert HostBridgeTaskExecutor._resolve_backend_api_url() == "http://localhost:8200"


def test_resolve_backend_api_url_falls_back_to_ws_host(monkeypatch):
    monkeypatch.delenv("MINDSCAPE_BACKEND_API_URL", raising=False)
    monkeypatch.setenv("MINDSCAPE_WS_HOST", "localhost:8200")

    assert HostBridgeTaskExecutor._resolve_backend_api_url() == "http://localhost:8200"


def test_codex_cli_command_uses_workspace_write_sandbox(monkeypatch):
    executor = HostBridgeTaskExecutor(workspace_root="/tmp", runtime_surface="codex_cli")
    captured = {}

    async def fake_fetch(runtime_name, ctx, **kwargs):
        return {"env": {}, "selected_runtime_id": "runtime-codex-test"}

    async def fake_run(ctx, cmd, cwd, runtime_name, **kwargs):
        captured["cmd"] = cmd
        return ExecutionResult(status="completed", output="ok")

    monkeypatch.setattr(executor, "_fetch_runtime_auth_env", fake_fetch)
    monkeypatch.setattr(executor, "_run_cli_agent_subprocess", fake_run)
    monkeypatch.setattr(executor, "_resolve_runtime_binary", lambda surface: "codex")

    ctx = ExecutionContext(
        execution_id="exec-1",
        workspace_id="ws-1",
        task="say hi",
        allowed_tools=[],
        max_duration=60,
    )

    import asyncio

    asyncio.run(executor._execute_via_codex_cli(ctx, timeout=5))

    assert "--full-auto" not in captured["cmd"]
    assert captured["cmd"][captured["cmd"].index("--sandbox") + 1] == "workspace-write"
    assert "--ask-for-approval" not in captured["cmd"]
