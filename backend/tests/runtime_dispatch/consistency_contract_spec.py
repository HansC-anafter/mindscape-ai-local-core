from backend.app.services.runtime_dispatch.consistency import (
    build_apply_projection_result,
    required_apply_event_contract,
)


def test_required_apply_event_contract_orders_db_event_outbox_before_redis():
    contract = required_apply_event_contract(
        plan_id="plan-a",
        apply_token="token-a",
        task_ids=["task-b", "task-a"],
    )

    assert contract["db_source_of_truth"] is True
    assert contract["task_event_type"] == "task.route_changed"
    assert contract["outbox_event_type"] == "runtime_dispatch.redis_projection_requested"
    assert contract["task_ids"] == ["task-a", "task-b"]
    assert contract["ordering"] == [
        "bounded_db_route_update",
        "append_task_route_changed_event",
        "append_redis_projection_requested_outbox",
        "bounded_redis_projection_update",
    ]


def test_apply_projection_result_marks_redis_partial_failure_as_repair_required():
    result = build_apply_projection_result(
        plan_id="plan-a",
        apply_token="token-a",
        updated_task_ids=["task-a", "task-b"],
        skipped_task_ids=["task-c"],
        redis_failed_task_ids=["task-b"],
    )

    assert result["state"] == "partial_success"
    assert result["redis_partial_failure"] is True
    assert result["repair_required"] is True
    assert result["repair_scope"] == {
        "plan_id": "plan-a",
        "task_ids": ["task-b"],
    }


def test_apply_projection_result_without_redis_failure_has_no_repair_scope():
    result = build_apply_projection_result(
        plan_id="plan-a",
        apply_token="token-a",
        updated_task_ids=["task-a"],
    )

    assert result["state"] == "applied"
    assert result["redis_partial_failure"] is False
    assert result["repair_required"] is False
    assert result["repair_scope"] is None
