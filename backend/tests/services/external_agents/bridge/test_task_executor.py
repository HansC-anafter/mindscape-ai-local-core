import pytest
import json
from pathlib import Path

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
        snapshot_paths=None,
        extra_env=None,
    ):
        captured["cwd"] = cwd
        captured["snapshot_root"] = snapshot_root
        captured["snapshot_paths"] = snapshot_paths
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
    assert captured["snapshot_paths"] == []
    assert captured["runtime_name"] == "codex_cli"


@pytest.mark.asyncio
async def test_codex_cli_uses_targeted_snapshot_for_expected_deliverable_when_sandbox_missing(
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
        snapshot_paths=None,
        extra_env=None,
    ):
        captured["cwd"] = cwd
        captured["snapshot_root"] = snapshot_root
        captured["snapshot_paths"] = snapshot_paths
        return ExecutionResult(status="completed", output="ok")

    monkeypatch.setattr(executor, "_fetch_runtime_auth_env", _fake_fetch_runtime_auth_env)
    monkeypatch.setattr(executor, "_run_cli_agent_subprocess", _fake_run_cli_agent_subprocess)
    monkeypatch.setattr(executor, "_resolve_runtime_binary", lambda _: "/bin/echo")

    ctx = ExecutionContext(
        execution_id="exec-123",
        workspace_id="ws-test",
        task="Write the persona deliverable.",
        allowed_tools=[],
        max_duration=60,
        sandbox_path=str(tmp_path / "missing-sandbox"),
        thread_id="thread-1",
        inputs={"deliverable_path": "persona_operating_system.md"},
    )
    result = await executor._execute_via_codex_cli(ctx, timeout=30)

    assert result.status == "completed"
    assert captured["cwd"] == str(tmp_path)
    assert captured["snapshot_root"] == str(tmp_path)
    assert captured["snapshot_paths"] == ["persona_operating_system.md"]


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
        snapshot_paths=None,
        extra_env=None,
    ):
        captured["cwd"] = cwd
        captured["snapshot_root"] = snapshot_root
        captured["snapshot_paths"] = snapshot_paths
        return ExecutionResult(status="completed", output="ok")

    monkeypatch.setattr(executor, "_fetch_runtime_auth_env", _fake_fetch_runtime_auth_env)
    monkeypatch.setattr(executor, "_run_cli_agent_subprocess", _fake_run_cli_agent_subprocess)
    monkeypatch.setattr(executor, "_resolve_runtime_binary", lambda _: "/bin/echo")

    ctx = _make_ctx(tmp_path, str(sandbox))
    result = await executor._execute_via_codex_cli(ctx, timeout=30)

    assert result.status == "completed"
    assert captured["cwd"] == str(sandbox)
    assert captured["snapshot_root"] == str(sandbox)
    assert captured["snapshot_paths"] == []


@pytest.mark.asyncio
async def test_run_cli_agent_subprocess_skips_snapshot_when_snapshot_root_empty(
    monkeypatch,
    tmp_path,
):
    executor = HostBridgeTaskExecutor(
        workspace_root=str(tmp_path),
        runtime_surface="codex_cli",
    )

    def _snapshot_should_not_run(_root, only_paths=None):
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
    assert result.metadata["effective_sandbox_path"] == str(tmp_path)


@pytest.mark.asyncio
async def test_run_cli_agent_subprocess_reports_effective_sandbox_path_for_targeted_snapshot(
    tmp_path,
):
    executor = HostBridgeTaskExecutor(
        workspace_root=str(tmp_path),
        runtime_surface="codex_cli",
    )

    ctx = _make_ctx(tmp_path, "")
    result = await executor._run_cli_agent_subprocess(
        ctx,
        ["/bin/sh", "-c", "printf '# Title\\n' > persona_operating_system.md"],
        str(tmp_path),
        runtime_name="codex_cli",
        snapshot_root=str(tmp_path),
        snapshot_paths=["persona_operating_system.md"],
    )

    assert result.status == "completed"
    assert result.files_created == ["persona_operating_system.md"]
    assert result.metadata["effective_sandbox_path"] == str(tmp_path)


@pytest.mark.asyncio
async def test_gemini_runtime_bridge_payload_includes_model_hint(monkeypatch, tmp_path):
    executor = HostBridgeTaskExecutor(
        workspace_root=str(tmp_path),
        runtime_surface="gemini_cli",
    )
    monkeypatch.setenv("MINDSCAPE_CLI_RUNTIME_CMD", "/bin/echo")

    captured = {}

    class _FakeProc:
        returncode = 0

        async def communicate(self, payload_bytes):
            captured["payload"] = json.loads(payload_bytes.decode("utf-8"))
            return (
                json.dumps({"status": "completed", "output": "ok"}).encode("utf-8"),
                b"",
            )

        def kill(self):
            return None

    async def _fake_create_subprocess_exec(*args, **kwargs):
        captured["argv"] = list(args)
        captured["cwd"] = kwargs.get("cwd")
        return _FakeProc()

    monkeypatch.setattr(
        "backend.app.services.external_agents.bridge.task_executor.asyncio.create_subprocess_exec",
        _fake_create_subprocess_exec,
    )

    ctx = ExecutionContext(
        execution_id="exec-123",
        workspace_id="ws-test",
        task="Summarize the workspace state.",
        allowed_tools=[],
        max_duration=60,
        model="gemini-2.5-pro",
        thread_id="thread-1",
    )

    result = await executor._execute_via_gemini_runtime_bridge(ctx, timeout=30)

    assert result["status"] == "completed"
    assert captured["payload"]["model"] == "gemini-2.5-pro"


@pytest.mark.asyncio
async def test_codex_cli_fails_when_no_last_agent_message(monkeypatch, tmp_path):
    executor = HostBridgeTaskExecutor(
        workspace_root=str(tmp_path),
        runtime_surface="codex_cli",
    )

    last_message_path = tmp_path / "codex-last.txt"
    last_message_path.write_text("", encoding="utf-8")

    class _FakeProc:
        pid = 12345
        returncode = 0

        async def communicate(self):
            stdout = (
                "[2026-04-01T18:55:30] OpenAI Codex v0.39.0 (research preview)\n"
                "--------\n"
                "User instructions:\n"
                "Reply with exactly: HI\n"
                "[2026-04-01T18:55:31] ERROR: You've hit your usage limit.\n"
            ).encode("utf-8")
            stderr = (
                f"Warning: no last agent message; wrote empty content to {last_message_path}\n"
            ).encode("utf-8")
            return stdout, stderr

    async def _fake_create_subprocess_exec(*args, **kwargs):
        return _FakeProc()

    monkeypatch.setattr(
        "backend.app.services.external_agents.bridge.task_executor.asyncio.create_subprocess_exec",
        _fake_create_subprocess_exec,
    )

    ctx = _make_ctx(tmp_path, "")
    result = await executor._run_cli_agent_subprocess(
        ctx,
        ["/bin/echo", "ignored"],
        str(tmp_path),
        runtime_name="codex_cli",
        last_message_path=str(last_message_path),
        snapshot_root="",
    )

    assert result.status == "failed"
    assert result.output == ""
    assert "usage limit" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_codex_cli_prefers_last_agent_message(monkeypatch, tmp_path):
    executor = HostBridgeTaskExecutor(
        workspace_root=str(tmp_path),
        runtime_surface="codex_cli",
    )

    last_message_path = tmp_path / "codex-last.txt"
    last_message_path.write_text('{"workstreams":[{"id":"WS1","name":"OK"}]}', encoding="utf-8")

    class _FakeProc:
        pid = 12346
        returncode = 0

        async def communicate(self):
            return b"banner output that should be ignored", b""

    async def _fake_create_subprocess_exec(*args, **kwargs):
        return _FakeProc()

    monkeypatch.setattr(
        "backend.app.services.external_agents.bridge.task_executor.asyncio.create_subprocess_exec",
        _fake_create_subprocess_exec,
    )

    ctx = _make_ctx(tmp_path, "")
    result = await executor._run_cli_agent_subprocess(
        ctx,
        ["/bin/echo", "ignored"],
        str(tmp_path),
        runtime_name="codex_cli",
        last_message_path=str(last_message_path),
        snapshot_root="",
    )

    assert result.status == "completed"
    assert result.output == Path(last_message_path).read_text(encoding="utf-8")
