import pytest

from backend.app.services.codex_runtime_failure_classifier import (
    classify_codex_cli_runtime_failure,
)
from backend.app.services.external_agents.bridge.task_executor import (
    ExecutionContext,
    ExecutionResult,
)
from backend.app.services.host_runtime_sessions.bridge_client import (
    HostRuntimeTurnRunner,
    HostRuntimeDirectCodexTaskExecutor,
    build_host_runtime_progress_payload,
)
from backend.app.services.host_runtime_sessions.runtime_recovery_policy import (
    DIRECT_CODEX_RUNTIME_ID,
    build_direct_codex_failure_metadata,
)


@pytest.mark.asyncio
async def test_direct_codex_auth_bundle_declares_non_pool_runtime(tmp_path) -> None:
    executor = HostRuntimeDirectCodexTaskExecutor(
        workspace_root=str(tmp_path),
        runtime_surface="codex_cli",
    )
    ctx = ExecutionContext(
        execution_id="exec-direct",
        workspace_id="ws-direct",
        task="summarize",
        allowed_tools=[],
        max_duration=30,
    )

    bundle = await executor._fetch_runtime_auth_env("codex_cli", ctx)

    assert bundle["selected_runtime_id"] == DIRECT_CODEX_RUNTIME_ID
    assert bundle["runtime_mode"] == "direct_subprocess"
    assert bundle["pool_managed"] is False
    assert bundle["recovery_policy"] == "direct_codex_cli"


@pytest.mark.asyncio
async def test_direct_codex_auth_bundle_honors_excluded_runtime(tmp_path) -> None:
    executor = HostRuntimeDirectCodexTaskExecutor(
        workspace_root=str(tmp_path),
        runtime_surface="codex_cli",
    )
    ctx = ExecutionContext(
        execution_id="exec-direct",
        workspace_id="ws-direct",
        task="summarize",
        allowed_tools=[],
        max_duration=30,
    )

    bundle = await executor._fetch_runtime_auth_env(
        "codex_cli",
        ctx,
        excluded_runtime_ids={DIRECT_CODEX_RUNTIME_ID},
    )

    assert bundle["selected_runtime_id"] == ""
    assert bundle["error"] == "direct_codex_runtime_excluded"
    assert bundle["pool_managed"] is False
    assert "pool_error" not in bundle


def test_direct_codex_failure_policy_classifies_cli_panic() -> None:
    metadata = build_direct_codex_failure_metadata(
        selected_runtime_id=DIRECT_CODEX_RUNTIME_ID,
        workspace_id="ws-direct",
        effective_workspace_id="ws-direct",
        error_text="thread 'main' panicked: Attempted to create a NULL object.",
        stage="preflight",
        exit_code=101,
    )

    assert metadata["failure_kind"] == "codex_cli_panic"
    assert metadata["error_code"] == "codex_cli_panic"
    assert metadata["recovery_action"] == "repair_or_update_local_codex_cli"
    assert metadata["pool_managed"] is False


def test_codex_classifier_maps_invalid_model_reasoning_effort_config() -> None:
    classification = classify_codex_cli_runtime_failure(
        "Error loading configuration: unknown variant `xhigh`, expected one of "
        "`minimal`, `low`, `medium`, `high` in `model_reasoning_effort`"
    )

    assert classification == {
        "fault_kind": "runtime",
        "error_code": "codex_cli_config_invalid",
    }


@pytest.mark.asyncio
async def test_direct_codex_preflight_failure_blocks_exec_dispatch(
    monkeypatch,
    tmp_path,
) -> None:
    executor = HostRuntimeDirectCodexTaskExecutor(
        workspace_root=str(tmp_path),
        runtime_surface="codex_cli",
    )

    async def fake_progress(*_args, **_kwargs):
        return None

    async def fake_preflight(**_kwargs):
        return ExecutionResult(
            status="failed",
            error="Codex CLI preflight failed with exit code 101",
            metadata={
                "runtime_mode": "direct_subprocess",
                "pool_managed": False,
                "failure_kind": "codex_cli_panic",
                "error_code": "codex_cli_panic",
                "recovery_action": "repair_or_update_local_codex_cli",
            },
        )

    async def fail_if_exec_runs(*_args, **_kwargs):
        raise AssertionError("codex exec should not run after failed preflight")

    monkeypatch.setattr(executor, "_resolve_runtime_binary", lambda _name: "/bin/codex")
    monkeypatch.setattr(
        executor,
        "_resolve_cli_runtime_paths",
        lambda _ctx: (str(tmp_path), str(tmp_path), []),
    )
    monkeypatch.setattr(executor, "_report_progress", fake_progress)
    monkeypatch.setattr(executor, "_preflight_direct_codex_cli", fake_preflight)
    monkeypatch.setattr(executor, "_run_cli_agent_subprocess", fail_if_exec_runs)

    result = await executor._execute_via_codex_cli(
        ExecutionContext(
            execution_id="exec-direct",
            workspace_id="ws-direct",
            task="summarize ig seed",
            allowed_tools=[],
            max_duration=30,
        ),
        timeout=30,
    )

    assert result.status == "failed"
    assert result.metadata["failure_kind"] == "codex_cli_panic"
    assert result.metadata["pool_managed"] is False
    assert "pool_error" not in result.metadata


@pytest.mark.asyncio
async def test_direct_codex_execution_failure_is_not_pool_reused(
    monkeypatch,
    tmp_path,
) -> None:
    executor = HostRuntimeDirectCodexTaskExecutor(
        workspace_root=str(tmp_path),
        runtime_surface="codex_cli",
    )

    async def fake_progress(*_args, **_kwargs):
        return None

    async def fake_preflight(**_kwargs):
        return None

    async def fake_exec(*_args, **_kwargs):
        return ExecutionResult(
            status="timeout",
            error="codex_cli subprocess stalled after 180s without file or message activity",
        )

    monkeypatch.setattr(executor, "_resolve_runtime_binary", lambda _name: "/bin/codex")
    monkeypatch.setattr(
        executor,
        "_resolve_cli_runtime_paths",
        lambda _ctx: (str(tmp_path), str(tmp_path), []),
    )
    monkeypatch.setattr(executor, "_report_progress", fake_progress)
    monkeypatch.setattr(executor, "_preflight_direct_codex_cli", fake_preflight)
    monkeypatch.setattr(executor, "_run_cli_agent_subprocess", fake_exec)

    result = await executor._execute_via_codex_cli(
        ExecutionContext(
            execution_id="exec-direct",
            workspace_id="ws-direct",
            task="summarize ig seed",
            allowed_tools=[],
            max_duration=30,
        ),
        timeout=30,
    )

    assert result.status == "timeout"
    assert result.error == (
        "codex_cli subprocess stalled after 180s without file or message activity"
    )
    assert result.metadata["failure_kind"] == "codex_cli_stall_no_activity"
    assert result.metadata["runtime_mode"] == "direct_subprocess"
    assert result.metadata["pool_managed"] is False
    assert "pool_error" not in result.metadata


def test_host_runtime_progress_payload_promotes_readable_state() -> None:
    payload = build_host_runtime_progress_payload(
        percent=25,
        detail="Waiting for Codex CLI output (5s elapsed)",
        runtime_surface="codex_cli",
        runtime_id="codex_cli",
    )

    assert payload["phase"] == "waiting_for_output"
    assert payload["title"] == "Codex CLI is working"
    assert payload["detail"] == "Waiting for Codex CLI output (5s elapsed)"
    assert payload["status"] == "running"
    assert payload["raw_event_type"] == "runtime.progress"


def test_host_runtime_progress_payload_maps_extended_phases() -> None:
    assert build_host_runtime_progress_payload(
        percent=18,
        detail="Checking Codex CLI login status",
        runtime_surface="codex_cli",
        runtime_id="codex_cli",
    )["phase"] == "preflight"
    assert build_host_runtime_progress_payload(
        percent=25,
        detail="codex_cli subprocess started",
        runtime_surface="codex_cli",
        runtime_id="codex_cli",
    )["title"] == "Codex CLI subprocess started"
    assert build_host_runtime_progress_payload(
        percent=90,
        detail="Collecting codex_cli output",
        runtime_surface="codex_cli",
        runtime_id="codex_cli",
    )["phase"] == "collecting_output"
    assert build_host_runtime_progress_payload(
        percent=95,
        detail="Finalizing runtime output",
        runtime_surface="codex_cli",
        runtime_id="codex_cli",
    )["phase"] == "finalizing"


@pytest.mark.asyncio
async def test_host_runtime_turn_runner_emits_readable_progress_payload() -> None:
    emitted: list[dict] = []

    async def emit_message(message: dict) -> None:
        emitted.append(message)

    def executor_factory(progress_callback):
        async def executor(_dispatch: dict) -> dict:
            await progress_callback("exec-readable", 30, "Waiting for Codex CLI output (5s elapsed)")
            return {"status": "completed", "output": "done"}

        return executor

    runner = HostRuntimeTurnRunner(
        emit_message=emit_message,
        executor_factory=executor_factory,
        max_duration=30,
    )
    await runner.run_turn(
        {
            "type": "turn.start",
            "workspace_id": "ws-readable",
            "session_id": "session-readable",
            "turn_id": "turn-readable",
            "runtime_surface": "codex_cli",
            "runtime_id": "codex_cli",
            "prompt": "run smoke",
            "envelope": {
                "execution_id": "exec-readable",
                "workspace_id": "ws-readable",
                "session_id": "session-readable",
                "turn_id": "turn-readable",
                "runtime_surface": "codex_cli",
                "runtime_id": "codex_cli",
                "metadata": {"max_duration": 30},
            },
        }
    )

    progress_events = [
        message["event"]
        for message in emitted
        if message.get("event", {}).get("type") == "runtime.progress"
    ]

    assert len(progress_events) == 1
    payload = progress_events[0]["payload"]
    assert payload["title"] == "Codex CLI is working"
    assert payload["detail"] == "Waiting for Codex CLI output (5s elapsed)"
    assert payload["phase"] == "waiting_for_output"
    assert payload["status"] == "running"
