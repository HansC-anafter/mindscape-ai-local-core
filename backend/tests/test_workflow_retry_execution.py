import os
import sys
from types import SimpleNamespace

import pytest

_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
_backend_root = os.path.join(_repo_root, "backend")
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

from backend.app.services.workflow.retry_execution import execute_step_with_retry


@pytest.mark.asyncio
async def test_execute_step_with_retry_retries_then_succeeds() -> None:
    step = SimpleNamespace(
        playbook_code="demo_step",
        kind="system_tool",
        retry_policy=SimpleNamespace(max_retries=1, retryable_errors=["timeout"]),
    )
    calls = []
    sleeps = []

    async def execute_workflow_step(*args, **kwargs):
        calls.append((args, kwargs))
        if len(calls) == 1:
            return {"status": "error", "error": "request timeout"}
        return {"status": "completed", "outputs": {"ok": True}}

    result = await execute_step_with_retry(
        step=step,
        workflow_context={"x": 1},
        previous_results={},
        execution_id="exec-1",
        workspace_id="ws-1",
        profile_id="profile-1",
        project_id="proj-1",
        step_index=3,
        execute_workflow_step_fn=execute_workflow_step,
        get_default_retry_policy_fn=lambda kind: None,
        calculate_retry_delay_fn=lambda attempt, retry_policy: 1.5,
        classify_error_fn=lambda error: "timeout" if "timeout" in error else "other",
        sleep_fn=lambda delay: _record_sleep(sleeps, delay),
    )

    assert result == {"status": "completed", "outputs": {"ok": True}}
    assert len(calls) == 2
    assert sleeps == [1.5]


@pytest.mark.asyncio
async def test_execute_step_with_retry_stops_on_non_retryable_error_result() -> None:
    step = SimpleNamespace(
        playbook_code="demo_step",
        kind="system_tool",
        retry_policy=SimpleNamespace(max_retries=2, retryable_errors=["timeout"]),
    )

    async def execute_workflow_step(*args, **kwargs):
        return {"status": "error", "error": "permission denied"}

    result = await execute_step_with_retry(
        step=step,
        workflow_context={},
        previous_results={},
        execution_id="exec-1",
        workspace_id="ws-1",
        profile_id=None,
        project_id=None,
        step_index=0,
        execute_workflow_step_fn=execute_workflow_step,
        get_default_retry_policy_fn=lambda kind: None,
        calculate_retry_delay_fn=lambda attempt, retry_policy: 0.1,
        classify_error_fn=lambda error: "auth" if "permission" in error else "other",
        sleep_fn=lambda delay: _record_sleep([], delay),
    )

    assert result == {"status": "error", "error": "permission denied"}


@pytest.mark.asyncio
async def test_execute_step_with_retry_returns_exhausted_error_after_exception_retries() -> None:
    step = SimpleNamespace(
        playbook_code="demo_step",
        kind="system_tool",
        retry_policy=SimpleNamespace(max_retries=1, retryable_errors=["timeout"]),
    )
    sleeps = []

    async def execute_workflow_step(*args, **kwargs):
        raise RuntimeError("request timeout")

    result = await execute_step_with_retry(
        step=step,
        workflow_context={},
        previous_results={},
        execution_id="exec-1",
        workspace_id="ws-1",
        profile_id=None,
        project_id=None,
        step_index=0,
        execute_workflow_step_fn=execute_workflow_step,
        get_default_retry_policy_fn=lambda kind: None,
        calculate_retry_delay_fn=lambda attempt, retry_policy: 0.25,
        classify_error_fn=lambda error: "timeout" if "timeout" in error else "other",
        sleep_fn=lambda delay: _record_sleep(sleeps, delay),
    )

    assert result["status"] == "error"
    assert result["error_type"] == "timeout"
    assert result["attempts"] == 2
    assert result["retries_exhausted"] is True
    assert sleeps == [0.25]


async def _record_sleep(sleeps, delay):
    sleeps.append(delay)
