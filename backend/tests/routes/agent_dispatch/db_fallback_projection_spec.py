import json

from backend.app.routes.agent_dispatch.db_fallback_projection import (
    consumer_dispatch_failed_result,
    insert_failed_result,
    pending_dispatch_task,
    pending_record_from_row,
    pending_result_from_row,
    timeout_result,
)


def test_result_builders_preserve_public_shapes():
    assert insert_failed_result("exec-1", RuntimeError("boom")) == {
        "execution_id": "exec-1",
        "status": "failed",
        "error": "Cross-worker DB fallback failed: boom",
    }
    assert timeout_result("exec-2", 12.4) == {
        "execution_id": "exec-2",
        "status": "timeout",
        "error": "No activity for 12s (cross-worker)",
    }
    assert consumer_dispatch_failed_result("exec-3", RuntimeError("send")) == {
        "execution_id": "exec-3",
        "status": "failed",
        "error": "Consumer dispatch failed: send",
    }


def test_pending_result_from_row_decodes_only_done_results():
    payload = {"execution_id": "exec-1", "status": "ok"}

    assert pending_result_from_row((json.dumps(payload), "done", "ts")) == (
        payload,
        "done",
        "ts",
    )
    assert pending_result_from_row((json.dumps(payload), "picked", "ts")) == (
        None,
        "picked",
        "ts",
    )
    assert pending_result_from_row(None) == (None, None, None)


def test_pending_record_and_task_decode_json_payloads():
    payload = {"agent_id": "surface-1"}
    result = {"status": "done"}

    assert pending_record_from_row(
        ("workspace-1", json.dumps(payload), "done", json.dumps(result))
    ) == {
        "workspace_id": "workspace-1",
        "payload": payload,
        "status": "done",
        "result_data": result,
    }
    assert pending_record_from_row(None) is None
    assert pending_dispatch_task("exec-1", "workspace-1", json.dumps(payload)) == {
        "execution_id": "exec-1",
        "workspace_id": "workspace-1",
        "payload": payload,
    }
