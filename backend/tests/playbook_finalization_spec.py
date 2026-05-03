from types import SimpleNamespace

import pytest

from backend.app.services.workflow.playbook_finalization import (
    finalize_playbook_execution,
)


@pytest.mark.asyncio
async def test_finalize_playbook_execution_passes_meeting_lineage_to_artifacts():
    calls = []

    async def fake_load_playbook_metadata(**_kwargs):
        return {"output_artifacts": [{"id": "demo"}]}

    async def fake_create_artifacts(**kwargs):
        calls.append(kwargs)
        return []

    result = await finalize_playbook_execution(
        store=object(),
        playbook_json=SimpleNamespace(playbook_code="demo_playbook"),
        playbook_inputs={
            "meeting_session_id": "mtg-1",
            "thread_id": "thread-1",
            "task_ir_id": "task-ir-1",
        },
        step_outputs={"write_file": {"body": "content"}},
        final_outputs={"body": "content"},
        execution_id="exec-1",
        workspace_id="ws-1",
        sandbox_id="sandbox-1",
        load_playbook_metadata_fn=fake_load_playbook_metadata,
        create_artifacts_fn=fake_create_artifacts,
        update_task_execution_context_fn=lambda **_kwargs: False,
    )

    assert result["status"] == "completed"
    assert calls
    assert calls[0]["execution_context"]["thread_id"] == "mtg-1"
    assert calls[0]["execution_context"]["task_id"] == "task-ir-1"
