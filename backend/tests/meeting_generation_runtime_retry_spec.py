from types import SimpleNamespace

import pytest

from backend.app.services.orchestration.meeting import _generation as generation_module
from backend.app.services.orchestration.meeting._generation import MeetingGenerationMixin
from backend.app.services.workspace_agent_executor import AgentExecutionResponse


def test_codex_pool_admission_block_is_non_retriable_at_outer_layer() -> None:
    assert generation_module._is_runtime_error_non_retriable_for_executor(
        "codex_cli",
        generation_module.CodexPoolAdmissionBlockedError(
            "Codex pool admission blocked: no_runnable_runtimes"
        ),
    )


class _FakeMeetingEngine(MeetingGenerationMixin):
    def __init__(self, executor, executor_runtime="codex_cli"):
        self.executor_runtime = executor_runtime
        self.workspace = SimpleNamespace(id="ws-test")
        self.session = SimpleNamespace(id="meeting-test")
        self.thread_id = "thread-test"
        self.project_id = "project-test"
        self._agent_executor = executor
        self.runtime_events = []
        self.stages = []
        self.codex_pool_admission_decisions = []

    async def _emit_meeting_stage(self, stage, message):
        self.stages.append({"stage": stage, "message": message})

    async def _emit_clarification_event(self, questions):
        self.clarification_questions = questions

    def _emit_runtime_unavailable_event(self, **event):
        self.runtime_events.append(event)

    async def _evaluate_executor_runtime_admission(self):
        if self.codex_pool_admission_decisions:
            return self.codex_pool_admission_decisions.pop(0)
        return {"admissible": True, "reason": "test_runtime_available"}

    def _direct_codex_lease_identity(self):
        return "meeting_session", self.session.id


class _SequenceExecutor:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def execute(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


@pytest.mark.asyncio
async def test_meeting_generation_codex_uses_direct_pool_without_env_flag(monkeypatch):
    monkeypatch.delenv("MINDSCAPE_MEETING_CODEX_DIRECT", raising=False)
    monkeypatch.delenv("MINDSCAPE_CODEX_CLI_DIRECT_SUBPROCESS", raising=False)
    monkeypatch.delenv("MINDSCAPE_BACKEND_ROLE", raising=False)

    executor = _SequenceExecutor(
        [
            AgentExecutionResponse(
                success=True,
                output="bridge response",
            )
        ]
    )
    engine = _FakeMeetingEngine(executor)
    direct_calls = []

    async def _fake_direct(messages, model=None):
        direct_calls.append({"messages": messages, "model": model})
        return "direct response"

    monkeypatch.setattr(engine, "_generate_text_via_direct_codex_cli", _fake_direct)

    output = await engine._generate_text_via_executor_runtime(
        [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "turn"},
        ],
        model="gpt-5.4",
    )

    assert output == "direct response"
    assert direct_calls and direct_calls[0]["model"] == "gpt-5.4"
    assert executor.calls == []


@pytest.mark.asyncio
async def test_meeting_generation_codex_uses_host_bridge_inside_backend_container(monkeypatch):
    monkeypatch.setenv("MINDSCAPE_BACKEND_ROLE", "execution")
    executor = _SequenceExecutor(
        [
            AgentExecutionResponse(
                success=True,
                output="bridge response",
            )
        ]
    )
    engine = _FakeMeetingEngine(executor)

    async def _fake_direct(messages, model=None):
        raise AssertionError("containerized backend must not spawn Codex directly")

    monkeypatch.setattr(engine, "_generate_text_via_direct_codex_cli", _fake_direct)

    output = await engine._generate_text_via_executor_runtime(
        [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "turn"},
        ],
        model="gpt-5.4",
    )

    assert output == "bridge response"
    assert executor.calls[0]["agent_id"] == "codex_cli"


@pytest.mark.asyncio
async def test_meeting_generation_retries_transient_missing_ws_client_for_non_codex_runtime(monkeypatch):
    monkeypatch.setattr(generation_module, "_executor_runtime_retry_delay", lambda _: 0)
    monkeypatch.setenv("MINDSCAPE_MEETING_EXECUTOR_RUNTIME_ATTEMPTS", "2")

    executor = _SequenceExecutor(
        [
            AgentExecutionResponse(
                success=False,
                output="",
                error="No WebSocket client connected. Run scripts/start_cli_bridge.sh --surface codex_cli to connect the host bridge.",
            ),
            AgentExecutionResponse(success=True, output="planner response"),
        ]
    )
    engine = _FakeMeetingEngine(executor, executor_runtime="gemini_cli")

    output = await engine._generate_text_via_executor_runtime(
        [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "turn"},
        ],
        model="gpt-5.4",
    )

    assert output == "planner response"
    assert len(executor.calls) == 2
    assert engine.runtime_events == []


@pytest.mark.asyncio
async def test_meeting_generation_direct_codex_reports_quota_and_fails_over(monkeypatch):
    monkeypatch.setattr(generation_module, "_executor_runtime_retry_delay", lambda _: 0)

    bundles = [
        {
            "env": {},
            "selected_runtime_id": "runtime-codex-a",
            "quota_scope_key": "account:a",
            "available_runtime_count": 2,
            "available_quota_scope_count": 2,
        },
        {
            "env": {},
            "selected_runtime_id": "runtime-codex-b",
            "quota_scope_key": "account:b",
            "available_runtime_count": 2,
            "available_quota_scope_count": 2,
        },
    ]
    engine = _FakeMeetingEngine(executor=None)
    reported_quota = []
    reported_success = []
    fetch_kwargs = []

    async def _fake_fetch_bundle(**kwargs):
        fetch_kwargs.append(kwargs)
        return bundles.pop(0)

    async def _fake_run_subprocess(**kwargs):
        if len(reported_quota) == 0:
            return (
                1,
                "",
                "You've hit your usage limit. Try again later.",
                "",
                "You've hit your usage limit. Try again later.",
            )
        return (0, "", "", "planner response", "")

    async def _fake_report_quota(runtime_id, workspace_id, error_text=""):
        reported_quota.append(
            {
                "runtime_id": runtime_id,
                "workspace_id": workspace_id,
                "error_text": error_text,
            }
        )

    async def _fake_report_success(runtime_id):
        reported_success.append(runtime_id)

    monkeypatch.setattr(engine, "_fetch_direct_codex_auth_bundle", _fake_fetch_bundle)
    monkeypatch.setattr(engine, "_run_direct_codex_cli_subprocess", _fake_run_subprocess)
    monkeypatch.setattr(
        engine,
        "_report_direct_codex_runtime_quota_exhausted",
        _fake_report_quota,
    )
    monkeypatch.setattr(engine, "_report_direct_codex_runtime_success", _fake_report_success)

    output = await engine._generate_text_via_direct_codex_cli(
        [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "turn"},
        ],
        model="gpt-5.4",
    )

    assert output == "planner response"
    assert reported_quota[0]["runtime_id"] == "runtime-codex-a"
    assert "usage limit" in reported_quota[0]["error_text"]
    assert reported_success == ["runtime-codex-b"]
    assert bundles == []
    assert fetch_kwargs[0]["excluded_runtime_ids"] == set()
    assert fetch_kwargs[0]["excluded_quota_scope_keys"] == set()
    assert fetch_kwargs[1]["excluded_runtime_ids"] == {"runtime-codex-a"}
    assert fetch_kwargs[1]["excluded_quota_scope_keys"] == {"account:a"}


@pytest.mark.asyncio
async def test_meeting_generation_direct_codex_reports_auth_and_fails_over(monkeypatch):
    monkeypatch.setattr(generation_module, "_executor_runtime_retry_delay", lambda _: 0)

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
    engine = _FakeMeetingEngine(executor=None)
    reported_auth = []
    reported_success = []

    async def _fake_fetch_bundle(**kwargs):
        return bundles.pop(0)

    async def _fake_run_subprocess(**kwargs):
        if len(reported_auth) == 0:
            return (
                1,
                "",
                "Your access token could not be refreshed. Please log out and sign in again.",
                "",
                "Your access token could not be refreshed. Please log out and sign in again.",
            )
        return (0, "", "", "planner response", "")

    async def _fake_report_auth(runtime_id, error_code, workspace_id):
        reported_auth.append(
            {
                "runtime_id": runtime_id,
                "error_code": error_code,
                "workspace_id": workspace_id,
            }
        )

    async def _fake_report_success(runtime_id):
        reported_success.append(runtime_id)

    monkeypatch.setattr(engine, "_fetch_direct_codex_auth_bundle", _fake_fetch_bundle)
    monkeypatch.setattr(engine, "_run_direct_codex_cli_subprocess", _fake_run_subprocess)
    monkeypatch.setattr(
        engine,
        "_report_direct_codex_runtime_auth_failure",
        _fake_report_auth,
    )
    monkeypatch.setattr(engine, "_report_direct_codex_runtime_success", _fake_report_success)

    output = await engine._generate_text_via_direct_codex_cli(
        [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "turn"},
        ],
        model="gpt-5.4",
    )

    assert output == "planner response"
    assert reported_auth[0]["runtime_id"] == "runtime-codex-a"
    assert reported_success == ["runtime-codex-b"]
    assert bundles == []


@pytest.mark.asyncio
async def test_meeting_generation_does_not_retry_non_transient_failure(monkeypatch):
    async def _fake_sleep(delay):
        raise AssertionError("non-transient errors must not sleep")

    monkeypatch.setattr(generation_module.asyncio, "sleep", _fake_sleep)
    monkeypatch.setenv("MINDSCAPE_MEETING_EXECUTOR_RUNTIME_ATTEMPTS", "3")

    executor = _SequenceExecutor(
        [
            AgentExecutionResponse(
                success=False,
                output="",
                error="Agent adapter not found: codex_cli",
            )
        ]
    )
    engine = _FakeMeetingEngine(executor, executor_runtime="gemini_cli")

    with pytest.raises(RuntimeError, match="Agent adapter not found"):
        await engine._generate_text_via_executor_runtime(
            [
                {"role": "system", "content": "system"},
                {"role": "user", "content": "turn"},
            ]
        )

    assert len(executor.calls) == 1
    assert engine.runtime_events[0]["reason"] == "executor_runtime_failed"


@pytest.mark.asyncio
async def test_meeting_generation_direct_codex_pool_block_skips_bridge_dispatch(monkeypatch):
    async def _fake_sleep(delay):
        raise AssertionError("admission-blocked single attempt must not sleep")

    monkeypatch.setattr(generation_module.asyncio, "sleep", _fake_sleep)
    monkeypatch.setenv("MINDSCAPE_CODEX_POOL_WAIT_ATTEMPTS", "1")

    executor = _SequenceExecutor(
        [
            AgentExecutionResponse(success=True, output="must not be dispatched"),
        ]
    )
    engine = _FakeMeetingEngine(executor, executor_runtime="codex_cli")

    async def _fake_fetch_bundle(**kwargs):
        return {"error": "Codex pool admission blocked: no_runnable_runtimes"}

    monkeypatch.setattr(engine, "_fetch_direct_codex_auth_bundle", _fake_fetch_bundle)

    with pytest.raises(RuntimeError, match="Codex pool admission blocked"):
        await engine._generate_text_via_executor_runtime(
            [
                {"role": "system", "content": "system"},
                {"role": "user", "content": "turn"},
            ],
            model="gpt-5.4",
        )

    assert executor.calls == []


@pytest.mark.asyncio
async def test_meeting_direct_codex_waits_for_temporary_pool_unavailable(monkeypatch):
    bundles = [
        {"error": "No available Codex runtimes in pool"},
        {
            "env": {},
            "selected_runtime_id": "runtime-codex-a",
            "available_runtime_count": 1,
            "available_quota_scope_count": 1,
        },
    ]
    sleeps = []
    engine = _FakeMeetingEngine(executor=None)

    async def _fake_fetch_bundle(**kwargs):
        return bundles.pop(0)

    async def _fake_sleep(delay):
        sleeps.append(delay)

    async def _fake_run_subprocess(**kwargs):
        return (0, "", "", "planner response", "")

    async def _fake_report_success(runtime_id):
        engine.reported_runtime_id = runtime_id

    monkeypatch.setenv("MINDSCAPE_CODEX_POOL_WAIT_ATTEMPTS", "2")
    monkeypatch.setattr(generation_module.asyncio, "sleep", _fake_sleep)
    monkeypatch.setattr(engine, "_fetch_direct_codex_auth_bundle", _fake_fetch_bundle)
    monkeypatch.setattr(engine, "_run_direct_codex_cli_subprocess", _fake_run_subprocess)
    monkeypatch.setattr(engine, "_report_direct_codex_runtime_success", _fake_report_success)

    output = await engine._generate_text_via_direct_codex_cli(
        [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "turn"},
        ],
        model="gpt-5.4",
    )

    assert output == "planner response"
    assert sleeps == [2.0]
    assert engine.reported_runtime_id == "runtime-codex-a"
    assert bundles == []
