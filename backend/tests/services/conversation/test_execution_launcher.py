from backend.app.services.conversation.execution_launcher import ExecutionLauncher


def test_handle_execution_result_extracts_nested_conversation_execution_id():
    launcher = ExecutionLauncher()

    handled = launcher._handle_execution_result(
        playbook_code="project_breakdown",
        execution_result={
            "execution_mode": "conversation",
            "result": {"execution_id": "exec-nested-123"},
        },
    )

    assert handled["execution_id"] == "exec-nested-123"
    assert handled["execution_mode"] == "conversation"


def test_handle_execution_result_falls_back_to_nested_task_id():
    launcher = ExecutionLauncher()

    handled = launcher._handle_execution_result(
        playbook_code="project_breakdown",
        execution_result={
            "execution_mode": "conversation",
            "result": {"task_id": "task-nested-456"},
        },
    )

    assert handled["execution_id"] == "task-nested-456"
