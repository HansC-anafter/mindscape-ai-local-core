from __future__ import annotations

import pytest

from backend.app.database.task_control_contract import (
    TASK_JSON_PAYLOAD_COLUMNS,
    validate_task_index_definitions,
)
from backend.app.services.task_payload_budget import (
    HOT_TASK_JSON_WRITE_LIMIT_BYTES,
    PayloadBudgetError,
    apply_task_payload_budget,
)


def test_all_five_hot_json_columns_share_the_write_budget() -> None:
    assert TASK_JSON_PAYLOAD_COLUMNS == (
        "params",
        "result",
        "execution_context",
        "storyline_tags",
        "blocked_payload",
    )
    with pytest.raises(PayloadBudgetError):
        apply_task_payload_budget(
            "storyline_tags",
            {"oversized": "x" * (HOT_TASK_JSON_WRITE_LIMIT_BYTES + 1)},
        )


def test_task_indexes_reject_pack_literals_and_json_paths() -> None:
    violations = validate_task_index_definitions(
        [
            (
                "idx_tasks_ig_reference",
                "CREATE INDEX ON tasks(workspace_id, (execution_context->'inputs'->>'reference_id')) WHERE pack_id = 'ig_analyze'",
            ),
            (
                "idx_tasks_execution_id",
                "CREATE INDEX ON tasks(execution_id)",
            ),
        ]
    )

    assert [item.index_name for item in violations] == ["idx_tasks_ig_reference"]
