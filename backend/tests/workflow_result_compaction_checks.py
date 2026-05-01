from backend.app.services.playbook_run_executor_core.result_compaction import (
    compact_workflow_result_for_task_context,
)


def test_compacts_large_account_arrays_but_keeps_summary():
    payload = {
        "status": "completed",
        "outputs": {
            "summary": {"total_accounts": 1000, "verified_accounts": 75},
            "accounts": [
                {"username": f"user_{index}", "bio": "x" * 500}
                for index in range(1000)
            ],
        },
    }

    compacted = compact_workflow_result_for_task_context(payload, max_bytes=16 * 1024)

    assert compacted["_compacted"] is True
    assert compacted["status"] == "completed"
    assert compacted["outputs"]["summary"]["total_accounts"] == 1000
    assert compacted["outputs"]["accounts"]["count"] == 1000
    assert compacted["outputs"]["accounts"]["_compacted"] is True


def test_compaction_falls_back_to_minimal_payload_when_still_too_large():
    payload = {
        "status": "completed",
        "outputs": {
            f"key_{index}": "x" * 2000
            for index in range(200)
        },
    }

    compacted = compact_workflow_result_for_task_context(payload, max_bytes=1024)

    assert compacted["_compacted"] is True
    assert compacted["status"] == "completed"
    assert "_original_bytes" in compacted
