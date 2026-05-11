from backend.app.services.task_result_landing import TaskResultLandingService


def test_extract_workflow_failure_prefers_explicit_top_level_error():
    failure = TaskResultLandingService._extract_workflow_failure(
        result_data={
            "status": "failed",
            "error": "top-level failure",
            "steps": {
                "step_a": {
                    "status": "error",
                    "error": "step failure",
                }
            },
        }
    )

    assert failure == "top-level failure"


def test_extract_workflow_failure_uses_step_error_before_generic_fallback():
    failure = TaskResultLandingService._extract_workflow_failure(
        result_data=None,
        execution_context={
            "workflow_result": {
                "status": "failed",
                "steps": {
                    "batch_pin": {
                        "status": "error",
                        "error": "unsupported operand type(s) for -: 'NoneType' and 'int'",
                    }
                },
            }
        },
    )

    assert failure == "unsupported operand type(s) for -: 'NoneType' and 'int'"


def test_extract_workflow_failure_keeps_generic_fallback_when_no_step_error_exists():
    failure = TaskResultLandingService._extract_workflow_failure(
        result_data={
            "status": "failed",
            "steps": {
                "step_a": {
                    "status": "completed",
                }
            },
        }
    )

    assert failure == "workflow failed"
