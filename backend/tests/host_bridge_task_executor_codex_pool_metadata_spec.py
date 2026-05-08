import pytest

from backend.app.services.external_agents.bridge.task_executor import (
    ExecutionContext,
    ExecutionResult,
    HostBridgeTaskExecutor,
)


def test_codex_pool_failure_metadata_preserves_attempted_runtime_context() -> None:
    metadata = HostBridgeTaskExecutor._codex_pool_failure_metadata(
        selected_runtime_id=None,
        attempted_runtime_ids={"runtime-b", "runtime-a"},
        last_runtime_error="You've hit your usage limit.",
        pool_error="No available Codex runtimes in pool",
    )

    assert metadata == {
        "selected_runtime_id": None,
        "attempted_runtime_ids": ["runtime-a", "runtime-b"],
        "last_runtime_error": "You've hit your usage limit.",
        "pool_error": "No available Codex runtimes in pool",
    }


@pytest.mark.asyncio
async def test_codex_pool_task_executor_fails_over_after_stale_refresh(
    monkeypatch,
    tmp_path,
):
    executor = HostBridgeTaskExecutor(
        workspace_root=str(tmp_path),
        runtime_surface="codex_cli",
    )
    bundles = [
        {
            "env": {},
            "selected_runtime_id": "runtime-codex-a",
            "available_runtime_count": 2,
            "available_quota_scope_count": 2,
        },
        {
            "env": {},
            "selected_runtime_id": "runtime-codex-b",
            "available_runtime_count": 2,
            "available_quota_scope_count": 2,
        },
    ]
    calls = []

    async def _fake_fetch(runtime_name, ctx, *, excluded_runtime_ids=None):
        calls.append(
            {
                "runtime_name": runtime_name,
                "excluded_runtime_ids": set(excluded_runtime_ids or set()),
            }
        )
        return bundles.pop(0)

    async def _fake_run(*_args, **kwargs):
        if kwargs["selected_runtime_id"] == "runtime-codex-a":
            return ExecutionResult(
                status="failed",
                error=(
                    "Your access token could not be refreshed because your refresh "
                    "token was already used. Please log out and sign in again."
                ),
            )
        return ExecutionResult(status="completed", output="ok")

    async def _fake_progress(*_args, **_kwargs):
        return None

    monkeypatch.setattr(executor, "_resolve_runtime_binary", lambda _name: "/bin/codex")
    monkeypatch.setattr(
        executor,
        "_resolve_cli_runtime_paths",
        lambda _ctx: (str(tmp_path), str(tmp_path), []),
    )
    monkeypatch.setattr(executor, "_fetch_runtime_auth_env", _fake_fetch)
    monkeypatch.setattr(executor, "_run_cli_agent_subprocess", _fake_run)
    monkeypatch.setattr(executor, "_report_progress", _fake_progress)

    result = await executor._execute_via_codex_cli(
        ExecutionContext(
            execution_id="exec-test",
            workspace_id="ws-test",
            task="return ok",
            allowed_tools=[],
            max_duration=30,
        ),
        timeout=30,
    )

    assert result.status == "completed"
    assert result.output == "ok"
    assert calls[1]["excluded_runtime_ids"] == {"runtime-codex-a"}
