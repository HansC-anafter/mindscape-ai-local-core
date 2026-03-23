import os
import sys
from types import SimpleNamespace

_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
_backend_root = os.path.join(_repo_root, "backend")
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

from backend.app.models.playbook import ErrorHandlingStrategy
from backend.app.services.workflow.scheduling import (
    apply_step_result_to_context,
    build_dependency_graph,
    build_paused_workflow_result,
    build_previous_results,
    evaluate_condition,
    get_ready_steps,
    get_ready_steps_for_parallel,
    normalize_parallel_step_result,
    should_stop_workflow_after_error,
)


def test_build_dependency_graph_tracks_previous_references() -> None:
    steps = [
        SimpleNamespace(
            playbook_code="first",
            inputs={},
            input_mapping={},
        ),
        SimpleNamespace(
            playbook_code="second",
            inputs={"summary": "$previous.first.outputs.summary"},
            input_mapping={"other": "$previous.first.outputs.extra"},
        ),
    ]

    graph = build_dependency_graph(steps)

    assert graph == {
        "first": set(),
        "second": {"first"},
    }


def test_evaluate_condition_supports_template_and_previous_conditions() -> None:
    template_step = SimpleNamespace(
        playbook_code="step-2",
        condition="{{input.enabled and step.prepare.summary}}",
    )
    previous_step = SimpleNamespace(
        playbook_code="step-3",
        condition="$previous.prepare.outputs.summary",
    )

    assert (
        evaluate_condition(
            step=template_step,
            results={},
            playbook_inputs={"enabled": True},
            step_outputs={"prepare": {"summary": "ok"}},
        )
        is True
    )
    assert (
        evaluate_condition(
            step=previous_step,
            results={"prepare": {"status": "completed", "outputs": {"summary": "ok"}}},
            playbook_inputs={},
        )
        is True
    )


def test_get_ready_steps_for_parallel_skips_condition_mismatches() -> None:
    step = SimpleNamespace(
        playbook_code="second",
        condition="{{input.enabled}}",
    )
    pending_steps = {"second": step}
    completed_steps = {"first"}
    results = {"first": {"status": "completed", "outputs": {"summary": "ok"}}}

    ready_steps = get_ready_steps_for_parallel(
        pending_steps=pending_steps,
        completed_steps=completed_steps,
        dependency_graph={"second": {"first"}},
        results=results,
        playbook_inputs={"enabled": False},
    )

    assert ready_steps == []
    assert "second" in completed_steps
    assert results["second"]["status"] == "skipped"
    assert "second" not in pending_steps


def test_get_ready_steps_marks_serial_condition_mismatch_as_skipped() -> None:
    step = SimpleNamespace(
        id="report",
        depends_on=["prepare"],
        condition="{{input.enabled}}",
    )
    step_outputs = {"prepare": {"summary": "ok"}}
    completed_steps = {"prepare"}

    ready = get_ready_steps(
        steps=[step],
        completed_steps=completed_steps,
        playbook_inputs={"enabled": False},
        step_outputs=step_outputs,
    )

    assert ready == []
    assert "report" in completed_steps
    assert step_outputs["report"]["status"] == "skipped"


def test_parallel_result_helpers_normalize_pause_and_error_handling() -> None:
    normalized = normalize_parallel_step_result(
        step_playbook_code="step-1",
        step_result=RuntimeError("boom"),
    )
    workflow_context = {}
    apply_step_result_to_context(
        workflow_context=workflow_context,
        step_result={"status": "completed", "outputs": {"summary": "done"}},
    )
    paused = build_paused_workflow_result(
        step_playbook_code="step-2",
        results={"step-2": {"status": "paused"}},
        workflow_context=workflow_context,
        step_result={"status": "paused", "checkpoint": {"id": "cp-1"}},
    )

    assert normalized["status"] == "error"
    assert workflow_context == {"summary": "done"}
    assert paused["paused_step"] == "step-2"
    assert paused["checkpoint"] == {"id": "cp-1"}


def test_should_stop_workflow_after_error_respects_strategy() -> None:
    stop_step = SimpleNamespace(
        playbook_code="stop-step",
        error_handling=ErrorHandlingStrategy.STOP_WORKFLOW,
    )
    continue_step = SimpleNamespace(
        playbook_code="continue-step",
        error_handling=ErrorHandlingStrategy.RETRY_THEN_CONTINUE,
    )

    assert (
        should_stop_workflow_after_error(
            step=stop_step,
            step_result={"status": "error", "error": "boom"},
        )
        is True
    )
    assert (
        should_stop_workflow_after_error(
            step=continue_step,
            step_result={
                "status": "error",
                "error": "boom",
                "retries_exhausted": True,
            },
        )
        is False
    )


def test_build_previous_results_only_keeps_outputs() -> None:
    previous = build_previous_results(
        {
            "one": {"status": "completed", "outputs": {"summary": "ok"}},
            "two": {"status": "error", "error": "boom"},
        }
    )

    assert previous == {"one": {"summary": "ok"}}
