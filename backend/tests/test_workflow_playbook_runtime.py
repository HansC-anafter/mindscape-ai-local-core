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

from backend.app.services.workflow.playbook_runtime import (
    apply_execution_profile_model_override,
    ensure_execution_sandbox,
    resolve_resume_checkpoint,
    restore_checkpoint_state,
)


def test_resolve_resume_checkpoint_requires_matching_execution_and_playbook_code() -> None:
    checkpoint = resolve_resume_checkpoint(
        playbook_inputs={
            "_workflow_checkpoint": {
                "execution_id": "exec-1",
                "playbook_code": "demo_playbook",
                "sandbox_id": "sbx-1",
            }
        },
        execution_id="exec-1",
        playbook_code="demo_playbook",
    )

    assert checkpoint == {
        "execution_id": "exec-1",
        "playbook_code": "demo_playbook",
        "sandbox_id": "sbx-1",
    }
    assert (
        resolve_resume_checkpoint(
            playbook_inputs={
                "_workflow_checkpoint": {
                    "execution_id": "exec-other",
                    "playbook_code": "demo_playbook",
                }
            },
            execution_id="exec-1",
            playbook_code="demo_playbook",
        )
        is None
    )


def test_restore_checkpoint_state_reapplies_approved_gate_step() -> None:
    step_outputs, completed_steps = restore_checkpoint_state(
        playbook_inputs={"gate_decisions": {"gate_step": {"action": "approved"}}},
        resume_checkpoint={
            "step_outputs": {"gate_step": {"status": "ok"}},
            "completed_steps": ["prepare"],
            "paused_step_id": "gate_step",
        },
    )

    assert step_outputs == {"gate_step": {"status": "ok"}}
    assert completed_steps == {"prepare", "gate_step"}


def test_apply_execution_profile_model_override_sets_resolved_model() -> None:
    playbook_inputs = {}

    resolved = apply_execution_profile_model_override(
        playbook_json=SimpleNamespace(
            execution_profile={
                "reasoning": "standard",
                "modalities": ["vision"],
                "locality": "local",
            }
        ),
        playbook_inputs=playbook_inputs,
        resolve_model_fn=lambda capability_profile, **kwargs: ("mlx/qwen", "balanced"),
    )

    assert resolved == "mlx/qwen"
    assert playbook_inputs["_model_override"] == "mlx/qwen"


def test_apply_execution_profile_model_override_does_not_override_existing_value() -> None:
    playbook_inputs = {"_model_override": "existing-model"}

    resolved = apply_execution_profile_model_override(
        playbook_json=SimpleNamespace(
            execution_profile={"reasoning": "standard"}
        ),
        playbook_inputs=playbook_inputs,
        resolve_model_fn=lambda capability_profile, **kwargs: ("mlx/qwen", "balanced"),
    )

    assert resolved is None
    assert playbook_inputs["_model_override"] == "existing-model"


@pytest.mark.asyncio
async def test_ensure_execution_sandbox_prefers_checkpoint_sandbox() -> None:
    project_calls = []
    execution_calls = []

    sandbox_id = await ensure_execution_sandbox(
        store=object(),
        playbook_json=SimpleNamespace(playbook_code="demo_playbook"),
        execution_id="exec-1",
        workspace_id="ws-1",
        project_id="proj-1",
        resume_checkpoint={"sandbox_id": "sbx-checkpoint"},
        get_project_fn=lambda **kwargs: _record_async(project_calls, kwargs),
        get_or_create_project_sandbox_fn=lambda **kwargs: _record_async(project_calls, kwargs),
        create_execution_sandbox_fn=lambda **kwargs: _record_async(execution_calls, kwargs),
    )

    assert sandbox_id == "sbx-checkpoint"
    assert project_calls == []
    assert execution_calls == []


@pytest.mark.asyncio
async def test_ensure_execution_sandbox_uses_project_sandbox_before_fallback() -> None:
    project_calls = []
    sandbox_calls = []
    execution_calls = []

    async def get_project(**kwargs):
        project_calls.append(kwargs)
        return {"id": kwargs["project_id"]}

    async def get_project_sandbox(**kwargs):
        sandbox_calls.append(kwargs)
        return "sbx-project"

    sandbox_id = await ensure_execution_sandbox(
        store=object(),
        playbook_json=SimpleNamespace(playbook_code="demo_playbook"),
        execution_id="exec-1",
        workspace_id="ws-1",
        project_id="proj-1",
        resume_checkpoint=None,
        get_project_fn=get_project,
        get_or_create_project_sandbox_fn=get_project_sandbox,
        create_execution_sandbox_fn=lambda **kwargs: _record_async(execution_calls, kwargs),
    )

    assert sandbox_id == "sbx-project"
    assert project_calls == [{"project_id": "proj-1", "workspace_id": "ws-1"}]
    assert sandbox_calls == [{"project_id": "proj-1", "workspace_id": "ws-1"}]
    assert execution_calls == []


@pytest.mark.asyncio
async def test_ensure_execution_sandbox_falls_back_to_execution_sandbox() -> None:
    execution_calls = []

    async def create_execution_sandbox(**kwargs):
        execution_calls.append(kwargs)
        return "sbx-exec"

    sandbox_id = await ensure_execution_sandbox(
        store=object(),
        playbook_json=SimpleNamespace(playbook_code="demo_playbook"),
        execution_id="exec-1",
        workspace_id="ws-1",
        project_id=None,
        resume_checkpoint=None,
        create_execution_sandbox_fn=create_execution_sandbox,
    )

    assert sandbox_id == "sbx-exec"
    assert execution_calls == [
        {
            "workspace_id": "ws-1",
            "execution_id": "exec-1",
            "playbook_code": "demo_playbook",
        }
    ]


async def _record_async(calls, payload):
    calls.append(payload)
    return None
