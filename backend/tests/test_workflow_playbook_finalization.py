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

from backend.app.services.workflow.playbook_finalization import (
    build_completed_result,
    finalize_playbook_execution,
    load_playbook_metadata,
    preserve_sandbox_context,
    resolve_playbook_code,
)


def test_resolve_playbook_code_falls_back_to_metadata() -> None:
    playbook_code = resolve_playbook_code(
        SimpleNamespace(
            playbook_code=None,
            metadata=SimpleNamespace(playbook_code="demo_playbook"),
        )
    )

    assert playbook_code == "demo_playbook"


@pytest.mark.asyncio
async def test_load_playbook_metadata_merges_service_and_json_sources() -> None:
    metadata = await load_playbook_metadata(
        store=object(),
        playbook_code="demo_playbook",
        playbook_json=SimpleNamespace(output_artifacts=[{"id": "model"}]),
        load_playbook_fn=lambda playbook_code: _return_async(
            SimpleNamespace(metadata={"title": "Demo"})
        ),
        load_playbook_json_fn=lambda playbook_code: {
            "output_artifacts": [{"id": "json"}]
        },
    )

    assert metadata["title"] == "Demo"
    assert metadata["output_artifacts"] == [{"id": "json"}]


def test_preserve_sandbox_context_updates_task_context_when_available() -> None:
    calls = []

    preserve_sandbox_context(
        sandbox_id="sbx-1",
        execution_id="exec-1",
        workspace_id="ws-1",
        update_task_execution_context_fn=lambda **kwargs: _record_update(calls, kwargs),
    )

    assert calls == [{"execution_id": "exec-1", "sandbox_id": "sbx-1"}]


def test_build_completed_result_includes_sandbox_id() -> None:
    result = build_completed_result(
        step_outputs={"step-1": {"ok": True}},
        final_outputs={"summary": "done"},
        sandbox_id="sbx-1",
    )

    assert result == {
        "status": "completed",
        "step_outputs": {"step-1": {"ok": True}},
        "outputs": {"summary": "done"},
        "sandbox_id": "sbx-1",
    }


@pytest.mark.asyncio
async def test_finalize_playbook_execution_runs_side_effects_and_returns_result() -> None:
    create_calls = []
    preserve_calls = []

    async def load_metadata(**kwargs):
        return {"output_artifacts": [{"id": "artifact-1"}]}

    async def create_artifacts(**kwargs):
        create_calls.append(kwargs)
        return [{"artifact_id": "artifact-1"}]

    result = await finalize_playbook_execution(
        store=object(),
        playbook_json=SimpleNamespace(playbook_code="demo_playbook"),
        playbook_inputs={"input": "x"},
        step_outputs={"step-1": {"ok": True}},
        final_outputs={"summary": "done"},
        execution_id="exec-1",
        workspace_id="ws-1",
        sandbox_id="sbx-1",
        load_playbook_metadata_fn=load_metadata,
        create_artifacts_fn=create_artifacts,
        update_task_execution_context_fn=lambda **kwargs: _record_update(
            preserve_calls,
            kwargs,
        ),
    )

    assert create_calls[0]["execution_context"] == {
        "execution_id": "exec-1",
        "sandbox_id": "sbx-1",
    }
    assert preserve_calls == [{"execution_id": "exec-1", "sandbox_id": "sbx-1"}]
    assert result["status"] == "completed"
    assert result["sandbox_id"] == "sbx-1"


async def _return_async(value):
    return value


def _record_update(calls, payload):
    calls.append(payload)
    return True
