import json
from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from backend.app.services.result_object_contract import json_payload_size
from backend.app.services.stores.tasks_store._base import TasksStoreCrudMixin
from backend.app.services.task_payload_budget import (
    PayloadBudgetError,
    apply_task_payload_budget,
)


class _SqliteBudgetStore(TasksStoreCrudMixin):
    def __init__(self) -> None:
        self._engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE tasks (
                        id TEXT PRIMARY KEY,
                        params TEXT,
                        result TEXT,
                        execution_context TEXT,
                        blocked_payload TEXT
                    )
                    """
                )
            )
            conn.execute(
                text(
                    """
                    INSERT INTO tasks (
                        id,
                        params,
                        result,
                        execution_context,
                        blocked_payload
                    ) VALUES (
                        'task-1',
                        '{}',
                        '{}',
                        '{}',
                        NULL
                    )
                    """
                )
            )

    @contextmanager
    def transaction(self):
        with self._engine.begin() as conn:
            yield conn

    def serialize_json(self, value):
        return json.dumps(value, ensure_ascii=False, default=str)

    def fetch_payloads(self):
        with self._engine.begin() as conn:
            return conn.execute(
                text(
                    """
                    SELECT params, result, execution_context, blocked_payload
                    FROM tasks
                    WHERE id = 'task-1'
                    """
                )
            ).mappings().one()


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
        "execution_id": "exec-1",
        "workflow_result": workflow_result,
        "execution_trace": {"events": [{"message": "x" * 1000} for _ in range(200)]},
    }

    compacted = apply_task_payload_budget(
        "execution_context",
        context,
        limit_bytes=32 * 1024,
    )

    assert compacted["route_request"] == route_request
    assert compacted["runner_resource_requirements"] == runner_requirements
    assert compacted["execution_id"] == "exec-1"
    assert compacted["workflow_result"]["_compacted"] is True
    assert compacted["execution_trace"]["_compacted"] is True
    assert compacted["_payload_budget"]["field"] == "execution_context"
    assert json_payload_size(compacted) <= 32 * 1024


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


def test_tasks_store_update_task_applies_payload_budget_before_write():
    store = _SqliteBudgetStore()
    route_request = {
        "target_lane": "comfyui_runtime:flux2_klein_true_v2_q6_local",
        "resource_groups": ["apple_metal_heavy"],
    }

    store.update_task(
        "task-1",
        execution_context={
            "route_request": route_request,
            "execution_trace": {"events": [{"message": "x" * 1000} for _ in range(500)]},
            "workflow_result": {
                "status": "completed",
                "steps": {
                    f"step_{index}": {
                        "status": "success",
                        "outputs": {"items": ["x" * 1000 for _ in range(30)]},
                    }
                    for index in range(20)
                },
            },
        },
        result={
            "summary": "done",
            "status": "completed",
            "execution_trace": {"events": [{"message": "x" * 1000} for _ in range(400)]},
        },
        return_updated=False,
    )

    row = store.fetch_payloads()
    stored_context = json.loads(row["execution_context"])
    stored_result = json.loads(row["result"])

    assert stored_context["route_request"] == route_request
    assert stored_context["execution_trace"]["_compacted"] is True
    assert stored_context["workflow_result"]["_compacted"] is True
    assert stored_result["summary"] == "done"
    assert stored_result["result_object"]["payload_schema"] == "task_result"
    assert not _contains_key(stored_result, "execution_trace")
