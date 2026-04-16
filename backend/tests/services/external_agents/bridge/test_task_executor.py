import asyncio
import pytest
import json
import urllib.error
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
        selected_runtime_id=None,
        stall_timeout=None,
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
        selected_runtime_id=None,
        stall_timeout=None,
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
        selected_runtime_id=None,
        stall_timeout=None,
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
async def test_run_cli_agent_subprocess_includes_targeted_deliverable_attachment(
    tmp_path,
):
    executor = HostBridgeTaskExecutor(
        workspace_root=str(tmp_path),
        runtime_surface="codex_cli",
    )

    ctx = _make_ctx(tmp_path, "")
    result = await executor._run_cli_agent_subprocess(
        ctx,
        ["/bin/sh", "-c", "printf '# Persona\\n' > persona_operating_system.md"],
        str(tmp_path),
        runtime_name="codex_cli",
        snapshot_root=str(tmp_path),
        snapshot_paths=["persona_operating_system.md"],
    )

    assert result.status == "completed"
    assert result.attachments == [
        {
            "filename": "persona_operating_system.md",
            "content": "# Persona\n",
        }
    ]


@pytest.mark.asyncio
async def test_run_cli_agent_subprocess_times_out_when_stalled(
    monkeypatch,
    tmp_path,
):
    executor = HostBridgeTaskExecutor(
        workspace_root=str(tmp_path),
        runtime_surface="codex_cli",
    )

    class _FakeProc:
        def __init__(self):
            self.pid = 99999
            self.returncode = None

        async def communicate(self):
            while self.returncode is None:
                await asyncio.sleep(0.01)
            return b"", b""

        def kill(self):
            self.returncode = -9

    fake_proc = _FakeProc()

    async def _fake_create_subprocess_exec(*args, **kwargs):
        return fake_proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_create_subprocess_exec)

    ctx = _make_ctx(tmp_path, "")
    result = await executor._run_cli_agent_subprocess(
        ctx,
        ["/bin/echo", "noop"],
        str(tmp_path),
        runtime_name="codex_cli",
        last_message_path=str(tmp_path / "last-message.txt"),
        snapshot_root=str(tmp_path),
        snapshot_paths=["persona_operating_system.md"],
        stall_timeout=0.05,
    )

    assert result.status == "timeout"
    assert "stalled after" in (result.error or "")
    assert fake_proc.returncode == -9


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


def test_fetch_runtime_auth_bundle_retries_after_timeout(monkeypatch, tmp_path):
    executor = HostBridgeTaskExecutor(
        workspace_root=str(tmp_path),
        runtime_surface="codex_cli",
    )
    monkeypatch.setenv("MINDSCAPE_BACKEND_API_URL", "http://127.0.0.1:8200")
    monkeypatch.setenv("MINDSCAPE_CLI_AUTH_BUNDLE_MAX_ATTEMPTS", "2")
    monkeypatch.setenv("MINDSCAPE_CLI_AUTH_BUNDLE_RETRY_DELAY_SECONDS", "0")

    attempts = {"count": 0}

    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(
                {
                    "selected_runtime_id": "runtime-b",
                    "env": {"CODEX_HOME": "/tmp/codex-b"},
                }
            ).encode("utf-8")

    def _fake_urlopen(req, timeout):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise urllib.error.URLError(TimeoutError("timed out"))
        return _FakeResponse()

    monkeypatch.setattr(
        "backend.app.services.external_agents.bridge.task_executor.urllib.request.urlopen",
        _fake_urlopen,
    )

    bundle = executor._fetch_runtime_auth_bundle_sync("codex_cli", _make_ctx(tmp_path, ""))

    assert attempts["count"] == 2
    assert bundle["selected_runtime_id"] == "runtime-b"
    assert bundle["env"]["CODEX_HOME"] == "/tmp/codex-b"


def test_report_runtime_quota_exhausted_retries_after_timeout(monkeypatch, tmp_path):
    executor = HostBridgeTaskExecutor(
        workspace_root=str(tmp_path),
        runtime_surface="codex_cli",
    )
    monkeypatch.setenv("MINDSCAPE_BACKEND_API_URL", "http://127.0.0.1:8200")
    monkeypatch.setenv("MINDSCAPE_CLI_RUNTIME_QUOTA_REPORT_MAX_ATTEMPTS", "2")

    attempts = {"count": 0}

    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def _fake_urlopen(req, timeout):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise urllib.error.URLError(TimeoutError("timed out"))
        return _FakeResponse()

    monkeypatch.setattr(
        "backend.app.services.external_agents.bridge.task_executor.urllib.request.urlopen",
        _fake_urlopen,
    )

    executor._report_runtime_quota_exhausted_sync("codex_cli", "runtime-a")

    assert attempts["count"] == 2


@pytest.mark.asyncio
async def test_codex_cli_retries_with_next_runtime_after_quota_failure(monkeypatch, tmp_path):
    executor = HostBridgeTaskExecutor(
        workspace_root=str(tmp_path),
        runtime_surface="codex_cli",
    )

    auth_bundles = [
        {
            "selected_runtime_id": "runtime-a",
            "env": {"CODEX_HOME": "/tmp/codex-a"},
        },
        {
            "selected_runtime_id": "runtime-b",
            "env": {"CODEX_HOME": "/tmp/codex-b"},
        },
    ]
    seen_runtime_ids = []

    async def _fake_fetch_runtime_auth_env(runtime_name, ctx):
        return auth_bundles.pop(0)

    async def _fake_run_cli_agent_subprocess(
        ctx,
        cmd,
        cwd,
        runtime_name,
        last_message_path=None,
        snapshot_root=None,
        snapshot_paths=None,
        extra_env=None,
        selected_runtime_id=None,
        stall_timeout=None,
    ):
        seen_runtime_ids.append(selected_runtime_id)
        if selected_runtime_id == "runtime-a":
            return ExecutionResult(
                status="failed",
                output="",
                error="You've hit your usage limit.",
                metadata={"selected_runtime_id": selected_runtime_id},
            )
        return ExecutionResult(
            status="completed",
            output="ok",
            metadata={"selected_runtime_id": selected_runtime_id},
        )

    monkeypatch.setattr(executor, "_fetch_runtime_auth_env", _fake_fetch_runtime_auth_env)
    monkeypatch.setattr(executor, "_run_cli_agent_subprocess", _fake_run_cli_agent_subprocess)
    monkeypatch.setattr(executor, "_resolve_runtime_binary", lambda _: "/bin/echo")

    ctx = _make_ctx(tmp_path, "")
    result = await executor._execute_via_codex_cli(ctx, timeout=30)

    assert result.status == "completed"
    assert result.output == "ok"
    assert seen_runtime_ids == ["runtime-a", "runtime-b"]


@pytest.mark.asyncio
async def test_codex_cli_stops_when_pool_reuses_exhausted_runtime(monkeypatch, tmp_path):
    executor = HostBridgeTaskExecutor(
        workspace_root=str(tmp_path),
        runtime_surface="codex_cli",
    )

    async def _fake_fetch_runtime_auth_env(runtime_name, ctx):
        return {
            "selected_runtime_id": "runtime-a",
            "env": {"CODEX_HOME": "/tmp/codex-a"},
        }

    attempt_count = 0

    async def _fake_run_cli_agent_subprocess(
        ctx,
        cmd,
        cwd,
        runtime_name,
        last_message_path=None,
        snapshot_root=None,
        snapshot_paths=None,
        extra_env=None,
        selected_runtime_id=None,
        stall_timeout=None,
    ):
        nonlocal attempt_count
        attempt_count += 1
        return ExecutionResult(
            status="failed",
            output="",
            error="usage limit",
            metadata={"selected_runtime_id": selected_runtime_id},
        )

    monkeypatch.setattr(executor, "_fetch_runtime_auth_env", _fake_fetch_runtime_auth_env)
    monkeypatch.setattr(executor, "_run_cli_agent_subprocess", _fake_run_cli_agent_subprocess)
    monkeypatch.setattr(executor, "_resolve_runtime_binary", lambda _: "/bin/echo")

    ctx = _make_ctx(tmp_path, "")
    result = await executor._execute_via_codex_cli(ctx, timeout=30)

    assert result.status == "failed"
    assert "reused exhausted runtime" in (result.error or "")
    assert attempt_count == 1


@pytest.mark.asyncio
async def test_codex_cli_stops_failover_when_no_alternate_runtime_is_selected(
    monkeypatch,
    tmp_path,
):
    executor = HostBridgeTaskExecutor(
        workspace_root=str(tmp_path),
        runtime_surface="codex_cli",
    )

    auth_bundles = [
        {
            "selected_runtime_id": "runtime-a",
            "env": {"CODEX_HOME": "/tmp/codex-a"},
        },
        {
            "warning": "No available Codex runtimes in pool",
            "env": {},
        },
    ]
    attempt_count = 0

    async def _fake_fetch_runtime_auth_env(runtime_name, ctx):
        return auth_bundles.pop(0)

    async def _fake_run_cli_agent_subprocess(
        ctx,
        cmd,
        cwd,
        runtime_name,
        last_message_path=None,
        snapshot_root=None,
        snapshot_paths=None,
        extra_env=None,
        selected_runtime_id=None,
        stall_timeout=None,
    ):
        nonlocal attempt_count
        attempt_count += 1
        return ExecutionResult(
            status="failed",
            output="",
            error="You've hit your usage limit.",
            metadata={"selected_runtime_id": selected_runtime_id},
        )

    monkeypatch.setattr(executor, "_fetch_runtime_auth_env", _fake_fetch_runtime_auth_env)
    monkeypatch.setattr(executor, "_run_cli_agent_subprocess", _fake_run_cli_agent_subprocess)
    monkeypatch.setattr(executor, "_resolve_runtime_binary", lambda _: "/bin/echo")

    ctx = _make_ctx(tmp_path, "")
    result = await executor._execute_via_codex_cli(ctx, timeout=30)

    assert result.status == "failed"
    assert "usage limit" in (result.error or "").lower()
    assert "No available Codex runtimes in pool" in (result.error or "")
    assert attempt_count == 1


@pytest.mark.asyncio
async def test_codex_cli_expands_failover_attempts_to_available_quota_scopes(
    monkeypatch,
    tmp_path,
):
    executor = HostBridgeTaskExecutor(
        workspace_root=str(tmp_path),
        runtime_surface="codex_cli",
    )

    auth_bundles = [
        {
            "selected_runtime_id": "runtime-a",
            "available_quota_scope_count": 5,
            "env": {"CODEX_HOME": "/tmp/codex-a"},
        },
        {
            "selected_runtime_id": "runtime-b",
            "available_quota_scope_count": 5,
            "env": {"CODEX_HOME": "/tmp/codex-b"},
        },
        {
            "selected_runtime_id": "runtime-c",
            "available_quota_scope_count": 5,
            "env": {"CODEX_HOME": "/tmp/codex-c"},
        },
        {
            "selected_runtime_id": "runtime-d",
            "available_quota_scope_count": 5,
            "env": {"CODEX_HOME": "/tmp/codex-d"},
        },
        {
            "selected_runtime_id": "runtime-e",
            "available_quota_scope_count": 5,
            "env": {"CODEX_HOME": "/tmp/codex-e"},
        },
    ]
    attempted_runtime_ids: list[str] = []

    async def _fake_fetch_runtime_auth_env(runtime_name, ctx):
        return auth_bundles.pop(0)

    async def _fake_run_cli_agent_subprocess(
        ctx,
        cmd,
        cwd,
        runtime_name,
        last_message_path=None,
        snapshot_root=None,
        snapshot_paths=None,
        extra_env=None,
        selected_runtime_id=None,
        stall_timeout=None,
    ):
        attempted_runtime_ids.append(selected_runtime_id)
        if selected_runtime_id == "runtime-e":
            return ExecutionResult(
                status="completed",
                output="ok",
                metadata={"selected_runtime_id": selected_runtime_id},
            )
        return ExecutionResult(
            status="failed",
            output="",
            error="You've hit your usage limit.",
            metadata={"selected_runtime_id": selected_runtime_id},
        )

    monkeypatch.setattr(executor, "_fetch_runtime_auth_env", _fake_fetch_runtime_auth_env)
    monkeypatch.setattr(executor, "_run_cli_agent_subprocess", _fake_run_cli_agent_subprocess)
    monkeypatch.setattr(executor, "_resolve_runtime_binary", lambda _: "/bin/echo")

    ctx = _make_ctx(tmp_path, "")
    result = await executor._execute_via_codex_cli(ctx, timeout=30)

    assert result.status == "completed"
    assert attempted_runtime_ids == [
        "runtime-a",
        "runtime-b",
        "runtime-c",
        "runtime-d",
        "runtime-e",
    ]


@pytest.mark.asyncio
async def test_codex_cli_failovers_on_retryable_stall_timeout(monkeypatch, tmp_path):
    executor = HostBridgeTaskExecutor(
        workspace_root=str(tmp_path),
        runtime_surface="codex_cli",
    )

    auth_bundles = [
        {
            "selected_runtime_id": "runtime-a",
            "env": {"CODEX_HOME": "/tmp/codex-a"},
        },
        {
            "selected_runtime_id": "runtime-b",
            "env": {"CODEX_HOME": "/tmp/codex-b"},
        },
    ]
    attempted_runtime_ids: list[str] = []

    async def _fake_fetch_runtime_auth_env(runtime_name, ctx):
        return auth_bundles.pop(0)

    async def _fake_run_cli_agent_subprocess(
        ctx,
        cmd,
        cwd,
        runtime_name,
        last_message_path=None,
        snapshot_root=None,
        snapshot_paths=None,
        extra_env=None,
        selected_runtime_id=None,
        stall_timeout=None,
    ):
        attempted_runtime_ids.append(selected_runtime_id)
        if selected_runtime_id == "runtime-a":
            return ExecutionResult(
                status="timeout",
                output="",
                error="codex_cli subprocess stalled after 180s without file or message activity",
                metadata={"selected_runtime_id": selected_runtime_id},
            )
        return ExecutionResult(
            status="completed",
            output="ok",
            metadata={"selected_runtime_id": selected_runtime_id},
        )

    monkeypatch.setattr(executor, "_fetch_runtime_auth_env", _fake_fetch_runtime_auth_env)
    monkeypatch.setattr(executor, "_run_cli_agent_subprocess", _fake_run_cli_agent_subprocess)
    monkeypatch.setattr(executor, "_resolve_runtime_binary", lambda _: "/bin/echo")

    ctx = _make_ctx(tmp_path, "")
    result = await executor._execute_via_codex_cli(ctx, timeout=30)

    assert result.status == "completed"
    assert result.output == "ok"
    assert attempted_runtime_ids == ["runtime-a", "runtime-b"]
