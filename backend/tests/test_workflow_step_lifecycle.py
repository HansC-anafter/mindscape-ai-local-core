import os
import sys
from datetime import datetime, timezone

import pytest

_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
_backend_root = os.path.join(_repo_root, "backend")
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

from backend.app.services.workflow.step_lifecycle import (
    build_gate_pause_result,
    maybe_invoke_step_hook,
    resolve_gate_action,
)


@pytest.mark.asyncio
async def test_maybe_invoke_step_hook_raises_value_error_in_strict_mode() -> None:
    async def fail_hook(**kwargs):
        raise RuntimeError("hook failed")

    with pytest.raises(ValueError, match="pre_step hook failed"):
        await maybe_invoke_step_hook(
            step_id="step-1",
            hook_phase="pre_step",
            hook_spec_model={"tool": "hook.tool"},
            playbook_inputs={},
            execution_id="exec-1",
            workspace_id="ws-1",
            profile_id="profile-1",
            step_outputs={},
            strict=True,
            invoke_step_hook_fn=fail_hook,
        )


@pytest.mark.asyncio
async def test_maybe_invoke_step_hook_is_non_fatal_in_warn_mode() -> None:
    async def fail_hook(**kwargs):
        raise RuntimeError("hook failed")

    await maybe_invoke_step_hook(
        step_id="step-1",
        hook_phase="post_step",
        hook_spec_model={"tool": "hook.tool"},
        playbook_inputs={},
        execution_id="exec-1",
        workspace_id="ws-1",
        profile_id="profile-1",
        step_outputs={},
        strict=False,
        invoke_step_hook_fn=fail_hook,
    )


def test_resolve_gate_action_supports_scalar_and_object_payloads() -> None:
    assert (
        resolve_gate_action(
            playbook_inputs={"gate_decisions": {"gate-1": {"action": "approved"}}},
            step_id="gate-1",
        )
        == "approved"
    )
    assert (
        resolve_gate_action(
            playbook_inputs={"gate_decisions": {"gate-2": "rejected"}},
            step_id="gate-2",
        )
        == "rejected"
    )


def test_build_gate_pause_result_embeds_checkpoint_and_sandbox() -> None:
    created_at = datetime(2026, 3, 24, 12, 0, 0, tzinfo=timezone.utc)

    result = build_gate_pause_result(
        step_id="gate-step",
        gate={"required": True},
        execution_id="exec-1",
        playbook_code="demo_playbook",
        sandbox_id="sbx-1",
        completed_steps={"prepare"},
        step_outputs={"prepare": {"ok": True}},
        partial_outputs={"summary": "ok"},
        created_at=created_at,
    )

    assert result["status"] == "paused"
    assert result["pause_reason"] == "waiting_gate"
    assert result["sandbox_id"] == "sbx-1"
    assert result["checkpoint"]["paused_step_id"] == "gate-step"
    assert result["checkpoint"]["sandbox_id"] == "sbx-1"
    assert result["checkpoint"]["created_at"] == created_at.isoformat()
