from __future__ import annotations

import pytest

from backend.app.database.task_control_contract import (
    TASK_JSON_PAYLOAD_COLUMNS,
    validate_task_index_definitions,
)
from backend.app.database.task_index_manifest import (
    IG_SUMMARY_RETIREMENT_REPLACEMENTS,
    IG_TASK_RETIREMENT_REPLACEMENTS,
    TASK_INDEX_OWNERSHIP_MANIFEST,
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


def test_index_manifest_owns_exact_live_baseline_and_retirement_targets() -> None:
    task_entries = [
        item
        for (relation, _name), item in TASK_INDEX_OWNERSHIP_MANIFEST.items()
        if relation == "tasks"
    ]
    summary_entries = [
        item
        for (relation, _name), item in TASK_INDEX_OWNERSHIP_MANIFEST.items()
        if relation == "task_summary_projection"
    ]

    assert len(task_entries) == 63
    assert len(summary_entries) == 15
    assert len(IG_TASK_RETIREMENT_REPLACEMENTS) == 18
    assert len(IG_SUMMARY_RETIREMENT_REPLACEMENTS) == 4
    assert all(
        item.owner
        and item.query_owner
        and item.writer_cost
        and item.replacement
        and item.retirement_condition
        and item.status
        for item in TASK_INDEX_OWNERSHIP_MANIFEST.values()
    )


def test_unregistered_task_index_fails_closed() -> None:
    violations = validate_task_index_definitions(
        [("idx_tasks_new_unowned", "CREATE INDEX ON tasks(foo)")]
    )

    assert [item.reason for item in violations] == [
        "unregistered_tasks_index_owner_or_budget"
    ]
