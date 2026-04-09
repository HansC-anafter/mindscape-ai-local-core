from backend.app.models.workspace import Task, TaskStatus
from backend.app.services.stores.tasks_store._base import _canonical_task_params_payload


def _build_task(*, params=None, execution_context=None) -> Task:
    return Task(
        id="task_payload_001",
        workspace_id="ws_001",
        message_id="msg_001",
        execution_id="exec_001",
        pack_id="ig_analyze_pinned_reference",
        task_type="playbook_execution",
        status=TaskStatus.PENDING,
        params=params if params is not None else {},
        execution_context=execution_context if execution_context is not None else {},
    )


def test_canonical_task_params_payload_prefers_explicit_params():
    task = _build_task(
        params={"reference_id": "ref_from_params", "analysis_profile": "visual_anatomy"},
        execution_context={
            "inputs": {
                "reference_id": "ref_from_ctx",
                "analysis_profile": "aesthetic_core",
            }
        },
    )

    assert _canonical_task_params_payload(task) == {
        "reference_id": "ref_from_params",
        "analysis_profile": "visual_anatomy",
    }


def test_canonical_task_params_payload_falls_back_to_execution_context_inputs():
    task = _build_task(
        params={},
        execution_context={
            "inputs": {
                "reference_id": "ref_from_ctx",
                "analysis_profile": "visual_anatomy",
            }
        },
    )

    assert _canonical_task_params_payload(task) == {
        "reference_id": "ref_from_ctx",
        "analysis_profile": "visual_anatomy",
    }
