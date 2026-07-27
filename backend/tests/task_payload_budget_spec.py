from pathlib import Path

import pytest

from backend.app.services.result_object_contract import json_payload_size
from backend.app.services.task_payload_budget import (
    DEFAULT_TASK_PAYLOAD_LIMITS,
    HOT_TASK_JSON_LIMIT_BYTES,
    HOT_TASK_JSON_WRITE_LIMIT_BYTES,
    PayloadBudgetError,
    apply_task_payload_budget,
)


def _contains_key(value, target_key):
    if isinstance(value, dict):
        return target_key in value or any(
            _contains_key(child, target_key) for child in value.values()
        )
    if isinstance(value, list):
        return any(_contains_key(child, target_key) for child in value)
    return False


def test_execution_context_budget_preserves_route_metadata():
    route_request = {
        "target_lane": "comfyui_runtime:flux2_klein_true_v2_q6_local",
        "resource_groups": ["apple_metal_heavy"],
        "priority_class": "interactive_high",
    }
    runner_requirements = {
        "min_free_memory_gb": 32,
        "resource_groups": ["apple_metal_heavy"],
    }
    workflow_result = {
        "status": "completed",
        "steps": {
            f"step_{index}": {
                "status": "success",
                "outputs": {"items": ["x" * 1000 for _ in range(30)]},
            }
            for index in range(20)
        },
    }
    context = {
        "route_request": route_request,
        "runner_resource_requirements": runner_requirements,
        "resource_class": "browser",
        "capability_code": "site_publication",
        "runner_profile_hint": "default_local_browser",
        "runtime_affinity": {"scope": "local"},
        "runner_timeout_seconds": 7200,
        "concurrency": {"lock_scope": "playbook"},
        "execution_inputs_ref": {
            "schema_version": 1,
            "workspace_id": "workspace-1",
            "execution_id": "exec-1",
            "storage_ref": "/workspace/execution-inputs/exec-1/inputs.json",
            "checksum_sha256": "a" * 64,
            "bytes": 140000,
            "mime_type": "application/json",
        },
        "execution_id": "exec-1",
        "workflow_result": workflow_result,
        "execution_trace": {"events": [{"message": "x" * 1000} for _ in range(200)]},
    }

    compacted = apply_task_payload_budget(
        "execution_context",
        context,
    )

    assert compacted["route_request"] == route_request
    assert compacted["runner_resource_requirements"] == runner_requirements
    assert compacted["resource_class"] == "browser"
    assert compacted["capability_code"] == "site_publication"
    assert compacted["runner_profile_hint"] == "default_local_browser"
    assert compacted["runtime_affinity"] == {"scope": "local"}
    assert compacted["runner_timeout_seconds"] == 7200
    assert compacted["concurrency"] == {"lock_scope": "playbook"}
    assert compacted["execution_inputs_ref"]["bytes"] == 140000
    assert compacted["execution_id"] == "exec-1"
    assert compacted["workflow_result"]["_compacted"] is True
    assert compacted["execution_trace"]["_compacted"] is True
    assert compacted["_payload_budget"]["field"] == "execution_context"
    assert json_payload_size(compacted) <= HOT_TASK_JSON_WRITE_LIMIT_BYTES


def test_default_hot_task_json_limits_are_strict_completion_budget():
    assert HOT_TASK_JSON_LIMIT_BYTES == 16 * 1024
    assert DEFAULT_TASK_PAYLOAD_LIMITS == {
        "params": 15 * 1024,
        "result": 15 * 1024,
        "execution_context": 15 * 1024,
        "storyline_tags": 15 * 1024,
        "blocked_payload": 15 * 1024,
    }


def test_result_budget_converts_large_result_to_descriptor():
    result = {
        "summary": "done",
        "status": "completed",
        "execution_id": "exec-1",
        "storage_ref": "/workspace/artifacts/exec-1",
        "execution_trace": {"events": [{"message": "x" * 1000} for _ in range(200)]},
    }

    compacted = apply_task_payload_budget(
        "result",
        result,
        limit_bytes=8 * 1024,
    )

    assert compacted["summary"] == "done"
    assert compacted["storage_ref"] == "/workspace/artifacts/exec-1"
    assert compacted["result_object"]["bytes"] == json_payload_size(result)
    assert compacted["_payload_budget"]["field"] == "result"
    assert json_payload_size(compacted) <= 8 * 1024
    assert not _contains_key(compacted, "execution_trace")


def test_params_budget_rejects_oversized_inputs_without_truncation():
    params = {"prompt": "x" * 4096}

    with pytest.raises(PayloadBudgetError):
        apply_task_payload_budget("params", params, limit_bytes=1024)


def test_tasks_store_write_paths_apply_payload_budget_before_serialization():
    create_source = (
        Path(__file__).resolve().parents[1]
        / "app/services/stores/tasks_store/_crud_create_read.py"
    ).read_text(encoding="utf-8")
    update_source = (
        Path(__file__).resolve().parents[1]
        / "app/services/stores/tasks_store/_crud_update.py"
    ).read_text(encoding="utf-8")

    assert 'apply_task_payload_budget("params", task.params)' in create_source
    assert 'apply_task_payload_budget("result", task.result)' in create_source
    assert 'apply_task_payload_budget(\n            "execution_context"' in create_source
    assert '"blocked_payload",\n            task.blocked_payload' in create_source
    assert '"storyline_tags",\n            task.storyline_tags' in create_source
    assert '"params": self.serialize_json(task_params)' in create_source
    assert '"result": self.serialize_json(task_result)' in create_source
    assert '"execution_context": (\n                self.serialize_json(task_execution_context)' in create_source
    assert '"blocked_payload": self.serialize_json(task_blocked_payload)' in create_source
    assert 'apply_task_payload_budget(key, value)' in update_source
