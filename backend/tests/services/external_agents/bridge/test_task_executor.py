import pytest

from backend.app.services.external_agents.bridge.task_executor import (
    ExecutionContext,
    ExecutionResult,
    HostBridgeTaskExecutor,
)


def _make_ctx(tmp_path, sandbox_path: str) -> ExecutionContext:
    return ExecutionContext(
        execution_id="exec-123",
        workspace_id="ws-test",
        task="Summarize the workspace state.",
        allowed_tools=[],
        max_duration=60,
        sandbox_path=sandbox_path,
        thread_id="thread-1",
    )


@pytest.mark.asyncio
async def test_codex_cli_uses_workspace_root_without_snapshot_when_sandbox_missing(
    monkeypatch,
    tmp_path,
):
    executor = HostBridgeTaskExecutor(
        workspace_root=str(tmp_path),
        runtime_surface="codex_cli",
    )
    captured = {}

    async def _fake_fetch_runtime_auth_env(runtime_name, ctx):
        return {}

    async def _fake_run_cli_agent_subprocess(
        ctx,
        cmd,
        cwd,
        runtime_name,
        last_message_path=None,
        snapshot_root=None,
        extra_env=None,
    ):
        captured["cwd"] = cwd
        captured["snapshot_root"] = snapshot_root
        captured["runtime_name"] = runtime_name
        return ExecutionResult(status="completed", output="ok")

    monkeypatch.setattr(executor, "_fetch_runtime_auth_env", _fake_fetch_runtime_auth_env)
    monkeypatch.setattr(executor, "_run_cli_agent_subprocess", _fake_run_cli_agent_subprocess)
    monkeypatch.setattr(executor, "_resolve_runtime_binary", lambda _: "/bin/echo")

    ctx = _make_ctx(tmp_path, str(tmp_path / "missing-sandbox"))
    result = await executor._execute_via_codex_cli(ctx, timeout=30)

    assert result.status == "completed"
    assert captured["cwd"] == str(tmp_path)
    assert captured["snapshot_root"] == ""
    assert captured["runtime_name"] == "codex_cli"


@pytest.mark.asyncio
async def test_codex_cli_uses_existing_sandbox_for_snapshot(monkeypatch, tmp_path):
    executor = HostBridgeTaskExecutor(
        workspace_root=str(tmp_path),
        runtime_surface="codex_cli",
    )
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    captured = {}

    async def _fake_fetch_runtime_auth_env(runtime_name, ctx):
        return {}

    async def _fake_run_cli_agent_subprocess(
        ctx,
        cmd,
        cwd,
        runtime_name,
        last_message_path=None,
        snapshot_root=None,
        extra_env=None,
    ):
        captured["cwd"] = cwd
        captured["snapshot_root"] = snapshot_root
        return ExecutionResult(status="completed", output="ok")

    monkeypatch.setattr(executor, "_fetch_runtime_auth_env", _fake_fetch_runtime_auth_env)
    monkeypatch.setattr(executor, "_run_cli_agent_subprocess", _fake_run_cli_agent_subprocess)
    monkeypatch.setattr(executor, "_resolve_runtime_binary", lambda _: "/bin/echo")

    ctx = _make_ctx(tmp_path, str(sandbox))
    result = await executor._execute_via_codex_cli(ctx, timeout=30)

    assert result.status == "completed"
    assert captured["cwd"] == str(sandbox)
    assert captured["snapshot_root"] == str(sandbox)


@pytest.mark.asyncio
async def test_run_cli_agent_subprocess_skips_snapshot_when_snapshot_root_empty(
    monkeypatch,
    tmp_path,
):
    executor = HostBridgeTaskExecutor(
        workspace_root=str(tmp_path),
        runtime_surface="codex_cli",
    )

    def _snapshot_should_not_run(_root):
        raise AssertionError("snapshot should be skipped when snapshot_root is empty")

    monkeypatch.setattr(executor, "_snapshot_files", _snapshot_should_not_run)

    ctx = _make_ctx(tmp_path, "")
    result = await executor._run_cli_agent_subprocess(
        ctx,
        ["/bin/sh", "-c", "printf hi"],
        str(tmp_path),
        runtime_name="codex_cli",
        snapshot_root="",
    )

    assert result.status == "completed"
    assert result.output == "hi"
    assert result.files_created == []
    assert result.files_modified == []
