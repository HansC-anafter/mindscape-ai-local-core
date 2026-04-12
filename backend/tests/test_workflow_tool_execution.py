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

from backend.app.services.execution_core.errors import RecoverableStepError
from backend.app.services.tool_policy_engine import PolicyViolationError
from backend.app.services.workflow.tool_execution import (
    check_tool_policy,
    execute_tool_step,
)


def test_check_tool_policy_translates_policy_violation(monkeypatch) -> None:
    class StubPolicyEngine:
        def check(self, *, tool_id, policy, workspace_id):
            raise PolicyViolationError("blocked by policy engine")

    monkeypatch.setattr(
        "backend.app.services.workflow.tool_execution.get_tool_policy_engine",
        lambda: StubPolicyEngine(),
    )

    step = SimpleNamespace(tool_policy={"allowed_tool_patterns": ["core_llm.*"]})

    with pytest.raises(ValueError, match="Tool execution blocked by policy"):
        check_tool_policy(
            step=step,
            tool_id="shell.exec",
            workspace_id="ws-1",
        )


@pytest.mark.asyncio
async def test_execute_tool_step_adds_explicit_llm_contract_for_local_llm_tools(
    monkeypatch,
) -> None:
    step = SimpleNamespace(id="step-1", tool_policy=None)
    execute_calls = []
    provider = object()

    monkeypatch.setattr(
        "backend.app.services.workflow.tool_execution._build_managed_llm_provider",
        lambda **kwargs: (
            provider,
            SimpleNamespace(
                model_name=kwargs.get("model_name") or "resolved-model",
                provider_name="ollama",
            ),
        ),
    )

    async def execute_tool(tool_id, **kwargs):
        execute_calls.append((tool_id, kwargs))
        return {"status": "completed", "result": "ok"}

    async def maybe_execute_remote(**kwargs):
        return False, None

    result = await execute_tool_step(
        step=step,
        tool_id="core_llm.multimodal_analyze",
        resolved_inputs={"prompt": "analyze"},
        playbook_inputs={"playbook_code": "demo"},
        execution_profile={"reasoning": "standard"},
        execution_id="exec-1",
        workspace_id="ws-1",
        profile_id="profile-1",
        resolve_remote_tool_route_fn=lambda playbook_inputs, *, step_id, tool_id: None,
        resolve_tool_model_override_fn=lambda **kwargs: "mlx-community/model",
        maybe_execute_tool_via_remote_route_fn=maybe_execute_remote,
        execute_tool_fn=execute_tool,
    )

    assert result == {"status": "completed", "result": "ok"}
    assert execute_calls == [
        (
            "core_llm.multimodal_analyze",
            {
                "prompt": "analyze",
                "profile_id": "profile-1",
                "model_name": "mlx-community/model",
                "llm_provider": provider,
            },
        )
    ]


@pytest.mark.asyncio
async def test_execute_tool_step_falls_back_to_enabled_local_model_when_primary_selection_unavailable(
    monkeypatch,
) -> None:
    step = SimpleNamespace(id="step-fallback", tool_policy=None)
    execute_calls = []
    provider = object()
    calls = []

    def _build_managed_llm_provider(**kwargs):
        calls.append(kwargs)
        if kwargs.get("provider_name") == "ollama":
            return (
                provider,
                SimpleNamespace(
                    model_name=kwargs["model_name"],
                    provider_name="ollama",
                ),
            )
        raise ValueError("Selected provider 'openai' is not available")

    monkeypatch.setattr(
        "backend.app.services.workflow.tool_execution._build_managed_llm_provider",
        _build_managed_llm_provider,
    )
    monkeypatch.setattr(
        "backend.app.services.workflow.tool_execution._resolve_enabled_local_chat_model",
        lambda: "qwen3:8b",
    )

    async def execute_tool(tool_id, **kwargs):
        execute_calls.append((tool_id, kwargs))
        return {"status": "completed", "result": "ok"}

    async def maybe_execute_remote(**kwargs):
        return False, None

    result = await execute_tool_step(
        step=step,
        tool_id="core_llm.structured_extract",
        resolved_inputs={"text": "brand brief", "schema_description": "{}"},
        playbook_inputs={"playbook_code": "demo"},
        execution_profile={"reasoning": "standard"},
        execution_id="exec-fallback",
        workspace_id="ws-1",
        profile_id="profile-1",
        resolve_remote_tool_route_fn=lambda playbook_inputs, *, step_id, tool_id: None,
        resolve_tool_model_override_fn=lambda **kwargs: None,
        maybe_execute_tool_via_remote_route_fn=maybe_execute_remote,
        execute_tool_fn=execute_tool,
    )

    assert result == {"status": "completed", "result": "ok"}
    assert len(calls) == 2
    assert calls[1]["provider_name"] == "ollama"
    assert calls[1]["model_name"] == "qwen3:8b"
    assert execute_calls == [
        (
            "core_llm.structured_extract",
            {
                "text": "brand brief",
                "schema_description": "{}",
                "profile_id": "profile-1",
                "model_name": "qwen3:8b",
                "llm_provider": provider,
            },
        )
    ]


@pytest.mark.asyncio
async def test_execute_tool_step_uses_remote_result_without_local_fallback() -> None:
    step = SimpleNamespace(id="step-remote", tool_policy=None)
    remote_calls = []
    local_calls = []

    async def maybe_execute_remote(**kwargs):
        remote_calls.append(kwargs)
        return True, {"status": "completed", "result": "remote-ok"}

    async def execute_tool(tool_id, **kwargs):
        local_calls.append((tool_id, kwargs))
        return {"status": "completed", "result": "local-ok"}

    result = await execute_tool_step(
        step=step,
        tool_id="core_llm.multimodal_analyze",
        resolved_inputs={"prompt": "analyze"},
        playbook_inputs={"playbook_code": "demo"},
        execution_profile=None,
        execution_id="exec-1",
        workspace_id="ws-1",
        profile_id="profile-1",
        resolve_remote_tool_route_fn=lambda playbook_inputs, *, step_id, tool_id: {
            "execution_backend": "remote"
        },
        resolve_tool_model_override_fn=lambda **kwargs: None,
        maybe_execute_tool_via_remote_route_fn=maybe_execute_remote,
        execute_tool_fn=execute_tool,
    )

    assert result == {"status": "completed", "result": "remote-ok"}
    assert len(remote_calls) == 1
    assert remote_calls[0]["tool_inputs"]["profile_id"] == "profile-1"
    assert local_calls == []


@pytest.mark.asyncio
async def test_execute_tool_step_raises_recoverable_error_for_recoverable_payload() -> None:
    step = SimpleNamespace(id="step-recoverable", tool_policy=None)

    async def execute_tool(tool_id, **kwargs):
        return {
            "status": "error",
            "recoverable": True,
            "error_type": "timeout",
            "error": "temporary backend timeout",
        }

    async def maybe_execute_remote(**kwargs):
        return False, None

    with pytest.raises(RecoverableStepError) as exc_info:
        await execute_tool_step(
            step=step,
            tool_id="shell.exec",
            resolved_inputs={"command": "echo hi"},
            playbook_inputs={"playbook_code": "demo"},
            execution_profile=None,
            execution_id="exec-1",
            workspace_id="ws-1",
            profile_id=None,
            resolve_remote_tool_route_fn=lambda playbook_inputs, *, step_id, tool_id: None,
            resolve_tool_model_override_fn=lambda **kwargs: None,
            maybe_execute_tool_via_remote_route_fn=maybe_execute_remote,
            execute_tool_fn=execute_tool,
        )

    assert exc_info.value.step_id == "step-recoverable"
    assert exc_info.value.error_type == "timeout"
    assert exc_info.value.detail == "temporary backend timeout"
