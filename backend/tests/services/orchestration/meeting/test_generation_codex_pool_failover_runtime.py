import asyncio
from types import SimpleNamespace

import pytest

from backend.app.services.orchestration.meeting._generation import (
    _sanitize_direct_codex_last_message,
)
from generation_codex_pool_failover_test_support import _DummyMeeting


@pytest.mark.asyncio
async def test_generate_text_prefers_bound_executor_runtime_over_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _DummyMeeting()

    async def _fake_executor(messages, model=None):
        return "runtime-owned-output"

    monkeypatch.setattr(engine, "_generate_text_via_executor_runtime", _fake_executor)

    output = await engine._generate_text(
        [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "user"},
        ],
        model="gpt-test",
    )

    assert output == "runtime-owned-output"

@pytest.mark.asyncio
async def test_generate_text_requires_bound_executor_runtime() -> None:
    engine = _DummyMeeting()
    engine.executor_runtime = None

    with pytest.raises(
        RuntimeError,
        match="Meeting generation requires a bound executor runtime",
    ):
        await engine._generate_text(
            [
                {"role": "system", "content": "system"},
                {"role": "user", "content": "user"},
            ],
            model="gpt-test",
        )

@pytest.mark.asyncio
async def test_direct_codex_cli_failsover_to_next_runtime_on_quota(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _DummyMeeting()
    bundle_calls: list[str] = []
    quota_reports: list[tuple[str, str]] = []
    run_calls: list[str] = []
    success_reports: list[str] = []

    async def _fake_bundle(**kwargs):
        bundle_calls.append("bundle")
        if len(bundle_calls) == 1:
            return {
                "env": {"CODEX_HOME": "/tmp/acct-a"},
                "selected_runtime_id": "runtime-a",
                "effective_workspace_id": "ws-effective",
                "available_quota_scope_count": 2,
            }
        return {
            "env": {"CODEX_HOME": "/tmp/acct-b"},
            "selected_runtime_id": "runtime-b",
            "effective_workspace_id": "ws-effective",
            "available_quota_scope_count": 2,
        }

    async def _fake_run(**kwargs):
        run_calls.append(str(kwargs.get("extra_env", {}).get("CODEX_HOME") or ""))
        if len(run_calls) == 1:
            transcript = (
                "[Meeting Agent Turn]\n"
                "[System Prompt]\nplanner instructions\n"
                "[Turn Prompt]\nscene request\n"
                "ERROR: You've hit your usage limit."
            )
            return (1, transcript, "", "", transcript)
        return (0, "done", "", "done", "done")

    async def _fake_report(
        runtime_id: str,
        *,
        workspace_id: str = "",
        error_text: str = "",
    ) -> None:
        quota_reports.append((runtime_id, workspace_id))

    async def _fake_success(runtime_id: str) -> None:
        success_reports.append(runtime_id)

    monkeypatch.setattr(engine, "_fetch_direct_codex_auth_bundle", _fake_bundle)
    monkeypatch.setattr(engine, "_run_direct_codex_cli_subprocess", _fake_run)
    monkeypatch.setattr(
        engine,
        "_report_direct_codex_runtime_quota_exhausted",
        _fake_report,
    )
    monkeypatch.setattr(
        engine,
        "_report_direct_codex_runtime_success",
        _fake_success,
    )

    output = await engine._generate_text_via_direct_codex_cli(
        [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "user"},
        ],
        model="gpt-test",
    )

    assert output == "done"
    assert len(bundle_calls) == 2
    assert run_calls == ["/tmp/acct-a", "/tmp/acct-b"]
    assert quota_reports == [("runtime-a", "ws-effective")]
    assert success_reports == ["runtime-b"]
    assert engine._bound_direct_codex_auth_bundle is None

@pytest.mark.asyncio
async def test_direct_codex_cli_failsover_to_next_runtime_on_stall_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _DummyMeeting()
    bundle_calls: list[str] = []
    auth_reports: list[tuple[str, str, str]] = []
    run_calls: list[str] = []
    success_reports: list[str] = []

    async def _fake_bundle(**kwargs):
        bundle_calls.append("bundle")
        if len(bundle_calls) == 1:
            return {
                "env": {"CODEX_HOME": "/tmp/acct-a"},
                "selected_runtime_id": "runtime-a",
                "effective_workspace_id": "ws-effective",
                "available_quota_scope_count": 2,
            }
        return {
            "env": {"CODEX_HOME": "/tmp/acct-b"},
            "selected_runtime_id": "runtime-b",
            "effective_workspace_id": "ws-effective",
            "available_quota_scope_count": 2,
        }

    async def _fake_run(**kwargs):
        run_calls.append(str(kwargs.get("extra_env", {}).get("CODEX_HOME") or ""))
        if len(run_calls) == 1:
            stalled = "codex_cli subprocess stalled after 45s without file or message activity"
            return (1, "", "", "", stalled)
        return (0, "done", "", "done", "done")

    async def _fake_report(
        runtime_id: str,
        *,
        error_code: str = "401",
        workspace_id: str = "",
    ) -> None:
        auth_reports.append((runtime_id, error_code, workspace_id))

    async def _fake_success(runtime_id: str) -> None:
        success_reports.append(runtime_id)

    monkeypatch.setattr(engine, "_fetch_direct_codex_auth_bundle", _fake_bundle)
    monkeypatch.setattr(engine, "_run_direct_codex_cli_subprocess", _fake_run)
    monkeypatch.setattr(
        engine,
        "_report_direct_codex_runtime_auth_failure",
        _fake_report,
    )
    monkeypatch.setattr(
        engine,
        "_report_direct_codex_runtime_success",
        _fake_success,
    )

    output = await engine._generate_text_via_direct_codex_cli(
        [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "user"},
        ],
        model="gpt-test",
    )

    assert output == "done"
    assert len(bundle_calls) == 2
    assert run_calls == ["/tmp/acct-a", "/tmp/acct-b"]
    assert auth_reports == [("runtime-a", "timeout", "ws-effective")]
    assert success_reports == ["runtime-b"]
    assert engine._bound_direct_codex_auth_bundle is None

@pytest.mark.asyncio
async def test_direct_codex_cli_failsover_to_next_runtime_on_os_error_2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _DummyMeeting()
    bundle_calls: list[str] = []
    auth_reports: list[tuple[str, str, str]] = []
    run_calls: list[str] = []
    success_reports: list[str] = []

    async def _fake_bundle(**kwargs):
        bundle_calls.append("bundle")
        if len(bundle_calls) == 1:
            return {
                "env": {"CODEX_HOME": "/tmp/acct-a"},
                "selected_runtime_id": "runtime-a",
                "effective_workspace_id": "ws-effective",
                "available_quota_scope_count": 2,
            }
        return {
            "env": {"CODEX_HOME": "/tmp/acct-b"},
            "selected_runtime_id": "runtime-b",
            "effective_workspace_id": "ws-effective",
            "available_quota_scope_count": 2,
        }

    async def _fake_run(**kwargs):
        run_calls.append(str(kwargs.get("extra_env", {}).get("CODEX_HOME") or ""))
        if len(run_calls) == 1:
            missing = "Error: No such file or directory (os error 2)"
            return (1, "", "", "", missing)
        return (0, "done", "", "done", "done")

    async def _fake_report(
        runtime_id: str,
        *,
        error_code: str = "401",
        workspace_id: str = "",
    ) -> None:
        auth_reports.append((runtime_id, error_code, workspace_id))

    async def _fake_success(runtime_id: str) -> None:
        success_reports.append(runtime_id)

    monkeypatch.setattr(engine, "_fetch_direct_codex_auth_bundle", _fake_bundle)
    monkeypatch.setattr(engine, "_run_direct_codex_cli_subprocess", _fake_run)
    monkeypatch.setattr(
        engine,
        "_report_direct_codex_runtime_auth_failure",
        _fake_report,
    )
    monkeypatch.setattr(
        engine,
        "_report_direct_codex_runtime_success",
        _fake_success,
    )

    output = await engine._generate_text_via_direct_codex_cli(
        [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "user"},
        ],
        model="gpt-test",
    )

    assert output == "done"
    assert len(bundle_calls) == 2
    assert run_calls == ["/tmp/acct-a", "/tmp/acct-b"]
    assert auth_reports == [("runtime-a", "timeout", "ws-effective")]
    assert success_reports == ["runtime-b"]
    assert engine._bound_direct_codex_auth_bundle is None

@pytest.mark.asyncio
async def test_direct_codex_cli_failsover_when_runner_raises_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _DummyMeeting()
    bundle_calls: list[str] = []
    auth_reports: list[tuple[str, str, str]] = []
    run_calls: list[str] = []
    success_reports: list[str] = []

    async def _fake_bundle(**kwargs):
        bundle_calls.append("bundle")
        if len(bundle_calls) == 1:
            return {
                "env": {"CODEX_HOME": "/tmp/acct-a"},
                "selected_runtime_id": "runtime-a",
                "effective_workspace_id": "ws-effective",
                "available_quota_scope_count": 2,
            }
        return {
            "env": {"CODEX_HOME": "/tmp/acct-b"},
            "selected_runtime_id": "runtime-b",
            "effective_workspace_id": "ws-effective",
            "available_quota_scope_count": 2,
        }

    async def _fake_shared_run(**kwargs):
        run_calls.append(str(kwargs.get("env", {}).get("CODEX_HOME") or ""))
        if len(run_calls) == 1:
            raise asyncio.TimeoutError(
                "codex_cli subprocess stalled after 45s without file or message activity"
            )
        return SimpleNamespace(
            returncode=0,
            stdout_text="done",
            stderr_text="",
            output_text="done",
            combined_output="done",
            synthesized_error=None,
        )

    async def _fake_report(
        runtime_id: str,
        *,
        error_code: str = "401",
        workspace_id: str = "",
    ) -> None:
        auth_reports.append((runtime_id, error_code, workspace_id))

    async def _fake_success(runtime_id: str) -> None:
        success_reports.append(runtime_id)

    monkeypatch.setattr(engine, "_fetch_direct_codex_auth_bundle", _fake_bundle)
    monkeypatch.setattr(
        "backend.app.services.orchestration.meeting._generation._run_shared_codex_cli_subprocess",
        _fake_shared_run,
    )
    monkeypatch.setattr(
        engine,
        "_report_direct_codex_runtime_auth_failure",
        _fake_report,
    )
    monkeypatch.setattr(
        engine,
        "_report_direct_codex_runtime_success",
        _fake_success,
    )

    output = await engine._generate_text_via_direct_codex_cli(
        [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "user"},
        ],
        model="gpt-test",
    )

    assert output == "done"
    assert len(bundle_calls) == 2
    assert run_calls == ["/tmp/acct-a", "/tmp/acct-b"]
    assert auth_reports == [("runtime-a", "timeout", "ws-effective")]
    assert success_reports == ["runtime-b"]
    assert engine._bound_direct_codex_auth_bundle is None

@pytest.mark.asyncio
async def test_direct_codex_cli_reports_deactivated_workspace_error_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _DummyMeeting()
    auth_reports: list[tuple[str, str, str]] = []

    async def _fake_bundle(**kwargs):
        return {
            "env": {"CODEX_HOME": "/tmp/acct-a"},
            "selected_runtime_id": "runtime-a",
            "effective_workspace_id": "ws-effective",
            "available_quota_scope_count": 1,
        }

    async def _fake_run(**kwargs):
        transcript = (
            "402 Payment Required\n"
            '{"code":"deactivated_workspace","message":"workspace disabled"}'
        )
        return (1, transcript, "", "", transcript)

    async def _fake_report(
        runtime_id: str,
        *,
        error_code: str = "401",
        workspace_id: str = "",
    ) -> None:
        auth_reports.append((runtime_id, error_code, workspace_id))

    monkeypatch.setattr(engine, "_fetch_direct_codex_auth_bundle", _fake_bundle)
    monkeypatch.setattr(engine, "_run_direct_codex_cli_subprocess", _fake_run)
    monkeypatch.setattr(
        engine,
        "_report_direct_codex_runtime_auth_failure",
        _fake_report,
    )

    with pytest.raises(RuntimeError, match="deactivated_workspace"):
        await engine._generate_text_via_direct_codex_cli(
            [
                {"role": "system", "content": "system"},
                {"role": "user", "content": "user"},
            ],
            model="gpt-test",
        )

    assert auth_reports == [("runtime-a", "deactivated_workspace", "ws-effective")]

def test_sanitize_direct_codex_last_message_rejects_transcript_echo() -> None:
    polluted = (
        "[Meeting Agent Turn]\n"
        "[System Prompt]\nplanner instructions\n"
        "[Turn Prompt]\nscene request\n"
        '{"decision_summary":"echo"}'
    )

    assert _sanitize_direct_codex_last_message(polluted) == ""
