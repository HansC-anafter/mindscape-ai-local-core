import json

from backend.app.services.stores.task_ir_projection import (
    empty_task_ir_stats,
    row_to_task_ir,
    task_ir_stats_from_row,
)


def _deserialize_json(value):
    return json.loads(value)


def test_row_to_task_ir_projects_json_columns_into_models():
    row = {
        "task_id": "task-1",
        "intent_instance_id": "intent-instance-1",
        "workspace_id": "workspace-1",
        "actor_id": "actor-1",
        "current_phase": "phase-1",
        "status": "running",
        "phases": json.dumps(
            [
                {
                    "id": "phase-1",
                    "name": "Draft",
                    "status": "pending",
                    "preferred_engine": "playbook:demo",
                }
            ]
        ),
        "artifacts": json.dumps(
            [
                {
                    "id": "artifact-1",
                    "type": "text/plain",
                    "source": "playbook:demo",
                    "uri": "file:///tmp/demo.txt",
                    "created_at": "2026-06-16T01:30:00+00:00",
                }
            ]
        ),
        "metadata": json.dumps(
            {
                "intent": {"intent_id": "intent-1"},
                "execution": {"playbook_code": "demo"},
            }
        ),
        "created_at": "2026-06-16T01:00:00+00:00",
        "updated_at": "2026-06-16T02:00:00+00:00",
        "last_checkpoint_at": "2026-06-16T01:45:00+00:00",
    }

    task_ir = row_to_task_ir(row, deserialize_json=_deserialize_json)

    assert task_ir.task_id == "task-1"
    assert task_ir.phases[0].preferred_engine == "playbook:demo"
    assert task_ir.artifacts[0].uri == "file:///tmp/demo.txt"
    assert task_ir.metadata.get_intent_id() == "intent-1"
    assert task_ir.metadata.get_playbook_code() == "demo"
    assert task_ir.last_checkpoint_at.isoformat() == "2026-06-16T01:45:00+00:00"


def test_task_ir_stats_projection_preserves_existing_defaults():
    assert task_ir_stats_from_row((4, 1, 2, 1, 3.5)) == {
        "total_tasks": 4,
        "completed_tasks": 1,
        "running_tasks": 2,
        "failed_tasks": 1,
        "avg_duration_hours": 3.5,
    }
    assert task_ir_stats_from_row((4, 1, 2, 1, None))["avg_duration_hours"] == 0
    assert task_ir_stats_from_row(None) == empty_task_ir_stats()
