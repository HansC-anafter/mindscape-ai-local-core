from __future__ import annotations

from scripts.maintenance.postgres_task_index_manifest import build_manifest_receipt


def _row(relation: str, index_name: str) -> dict[str, object]:
    return {
        "relation": relation,
        "index_name": index_name,
        "definition": f"CREATE INDEX {index_name} ON {relation}(id)",
        "index_bytes": 4096,
        "idx_scan": 2,
        "idx_tup_read": 3,
        "idx_tup_fetch": 1,
        "is_valid": True,
        "is_ready": True,
    }


def test_manifest_joins_catalog_to_exact_ownership_and_counts_targets() -> None:
    payload = build_manifest_receipt(
        [
            _row("tasks", "tasks_pkey"),
            _row("tasks", "idx_tasks_ig_active_workbench"),
            _row(
                "task_summary_projection",
                "idx_tsp_ig_workbench_active_rank_updated_v4",
            ),
        ],
        table_stats=[],
        captured_at="2026-07-17T00:00:00+00:00",
        stats_reset="2026-07-16T00:00:00+00:00",
    )

    assert payload["ok"] is True
    assert payload["registered_count"] == 3
    assert payload["pack_specific_retirement_count"] == 2
    assert payload["unregistered"] == []


def test_manifest_fails_closed_for_unregistered_or_invalid_index() -> None:
    unknown = _row("tasks", "idx_tasks_unowned")
    invalid = _row("tasks", "tasks_pkey")
    invalid["is_valid"] = False

    payload = build_manifest_receipt(
        [unknown, invalid],
        table_stats=[],
        captured_at="2026-07-17T00:00:00+00:00",
        stats_reset=None,
    )

    assert payload["ok"] is False
    assert payload["unregistered"] == ["tasks.idx_tasks_unowned"]
    assert payload["invalid_or_not_ready"] == ["tasks.tasks_pkey"]
    assert payload["indexes"][0]["status"] == "blocked_keep"
