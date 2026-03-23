import os
import sys

_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
_backend_root = os.path.join(_repo_root, "backend")
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

from backend.app.services.workflow.result_mapper import (
    map_sub_playbook_result_to_step_outputs,
    map_tool_result_to_step_outputs,
)


def test_map_tool_result_to_step_outputs_supports_nested_fields() -> None:
    mapped = map_tool_result_to_step_outputs(
        step_id="step-1",
        output_defs={
            "summary": "payload.summary",
            "topics": "payload.topics",
        },
        tool_result={
            "payload": {
                "summary": "done",
                "topics": ["a", "b"],
            }
        },
    )

    assert mapped == {"summary": "done", "topics": ["a", "b"]}


def test_map_tool_result_to_step_outputs_supports_empty_field_passthrough() -> None:
    tool_result = {"status": "completed", "value": 42}

    mapped = map_tool_result_to_step_outputs(
        step_id="step-2",
        output_defs={"result": ""},
        tool_result=tool_result,
    )

    assert mapped == {"result": tool_result}


def test_map_tool_result_to_step_outputs_raises_for_missing_required_field() -> None:
    try:
        map_tool_result_to_step_outputs(
            step_id="step-3",
            output_defs={"summary": "payload.summary"},
            tool_result={"payload": {}},
        )
    except ValueError as exc:
        assert "required output 'summary'" in str(exc)
    else:
        raise AssertionError("expected ValueError for missing nested output")


def test_map_sub_playbook_result_to_step_outputs() -> None:
    mapped = map_sub_playbook_result_to_step_outputs(
        {"summary": "report", "grade": "score"},
        {"report": "ok", "score": 42, "ignored": True},
    )

    assert mapped == {"summary": "ok", "grade": 42}
