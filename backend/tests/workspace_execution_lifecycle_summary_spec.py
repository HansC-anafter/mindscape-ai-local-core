from backend.app.services.workspace_execution.lifecycle_summary import (
    attach_lifecycle_summaries_to_tasks,
    attach_lifecycle_summary_to_progress_snapshot,
    build_lifecycle_summary,
)


def test_lifecycle_summary_marks_running_runtime_owner():
    summary = build_lifecycle_summary(
        {
            "task_id": "task-1",
            "execution_id": "exec-1",
            "status": "running",
            "queue_shard": "browser_local",
            "execution_context": {"runner_id": "runner-browser-1"},
        },
        source="workspace_tasks",
    )

    assert summary["phase"] == "running"
    assert summary["terminal"] is False
    assert summary["owner"] == {"type": "runtime", "id": "runner-browser-1"}
    assert summary["evidence"]["queue_shard"] == "browser_local"


def test_lifecycle_summary_keeps_blocked_work_waiting():
    summary = build_lifecycle_summary(
        {
            "task_id": "task-1",
            "execution_id": "exec-1",
            "status": "pending",
            "blocked_reason": "concurrency_locked",
            "frontier_state": "cold",
        },
        source="workspace_tasks",
    )

    assert summary["phase"] == "waiting"
    assert summary["next_step"] == "Waiting for blocker to clear: concurrency_locked."
    assert summary["evidence"]["blocked_reason"] == "concurrency_locked"


def test_lifecycle_summary_marks_terminal_artifact_evidence():
    snapshot = attach_lifecycle_summary_to_progress_snapshot(
        {
            "workspace_id": "ws-1",
            "execution_id": "exec-1",
            "task_status": "succeeded",
            "artifact_id": "artifact-1",
        }
    )

    assert snapshot["lifecycle_summary"]["phase"] == "completed"
    assert snapshot["lifecycle_summary"]["terminal"] is True
    assert snapshot["lifecycle_summary"]["evidence"]["artifact_id"] == "artifact-1"


def test_task_list_enrichment_does_not_mutate_source_payload():
    task = {"task_id": "task-1", "status": "running"}
    payload = attach_lifecycle_summaries_to_tasks({"tasks": [task]})

    assert "lifecycle_summary" not in task
    assert payload["tasks"][0]["lifecycle_summary"]["phase"] == "running"
