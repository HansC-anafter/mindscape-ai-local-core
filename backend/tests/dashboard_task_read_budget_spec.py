from pathlib import Path


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_dashboard_uses_one_bounded_task_read_store():
    source = (
        _backend_root() / "app/services/dashboard_aggregator.py"
    ).read_text(encoding="utf-8")

    assert "DashboardTaskReadStore" in source
    assert "self.tasks_store.list_pending_tasks" not in source
    assert "_group_tasks_by_execution" not in source
    assert "self.dashboard_tasks.list_pending_items" in source
    assert "self.dashboard_tasks.count_pending_tasks" in source
    assert "self.dashboard_tasks.count_tasks_by_execution_ids" in source


def test_dashboard_task_page_limits_ids_before_payload_hydration():
    source = (
        _backend_root()
        / "app/services/stores/postgres/dashboard_task_read_store.py"
    ).read_text(encoding="utf-8")

    assert "SELECT *" not in source
    assert "WITH workspace_candidates AS MATERIALIZED" in source
    assert "page_ids AS MATERIALIZED" in source
    assert "LIMIT :candidate_limit" in source
    assert "LIMIT :limit OFFSET :offset" in source
    assert "JOIN task_summary_projection AS projection" in source
    assert "source.params ->> 'description'" in source
    assert source.index("LIMIT :limit OFFSET :offset") < source.index(
        "source.params ->> 'description'"
    )


def test_dashboard_counts_are_narrow_and_query_scoped():
    source = (
        _backend_root()
        / "app/services/stores/postgres/dashboard_task_read_store.py"
    ).read_text(encoding="utf-8")

    assert "status = 'pending'" in source
    assert "execution_id = ANY(CAST(:execution_ids AS text[]))" in source
    assert "SET LOCAL statement_timeout = '10000ms'" in source
    assert "GROUP BY execution_id" in source


def test_dashboard_errors_are_redacted_and_retryable_for_database_recovery():
    source = (
        _backend_root() / "app/routes/core/dashboard.py"
    ).read_text(encoding="utf-8")

    assert "detail=str(e)" not in source
    assert "classify_database_error" in source
    assert '"error_code": "runtime_database_unavailable"' in source
    assert 'headers={"Retry-After": "30"}' in source
    assert 'detail={"error_code": "dashboard_query_failed"}' in source


def test_dashboard_read_paths_are_registered_as_p0_semantic_surfaces():
    registry = (
        _backend_root().parent / "ci/product_semantic_surfaces.yaml"
    ).read_text(encoding="utf-8")
    runtime_budget = registry.split(
        "id: psc.local-core.runtime-task-read-budget.v1",
        maxsplit=1,
    )[1].split("\n  - id:", maxsplit=1)[0]

    assert "backend/app/routes/core/dashboard.py" in runtime_budget
    assert "backend/app/services/dashboard_aggregator.py" in runtime_budget
    assert (
        "backend/app/services/stores/postgres/dashboard_task_read_store.py"
        in runtime_budget
    )
    assert "backend/tests/dashboard_task_read_budget_spec.py" in runtime_budget
