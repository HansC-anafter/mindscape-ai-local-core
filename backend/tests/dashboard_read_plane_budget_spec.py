from pathlib import Path

from backend.app.services.dashboard_mappings import (
    map_execution_to_case,
    map_task_to_assignment,
)


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (_backend_root() / relative_path).read_text(encoding="utf-8")


def test_dashboard_uses_one_complete_read_store_without_n_plus_one_calls():
    source = _read("app/services/dashboard_aggregator.py")

    assert "DashboardReadStore" in source
    assert "DashboardTaskReadStore" not in source
    assert "TasksStore" not in source
    assert "list_executions_by_workspace" not in source
    assert "list_tasks_by_workspace" not in source
    assert "await asyncio.to_thread" in source


def test_dashboard_queries_bound_candidates_before_payload_hydration():
    source = _read("app/services/stores/postgres/dashboard_read_queries.py")

    assert "SELECT *" not in source
    assert "LIMIT 50" in source
    assert source.count("LIMIT 100") >= 4
    assert "page_ids AS MATERIALIZED" in source
    assert "JOIN task_summary_projection AS projection" in source
    assert "source.params ->> 'description'" in source
    assert source.index("LIMIT :limit OFFSET :offset") < source.index(
        "source.params ->> 'description'"
    )


def test_assignment_candidates_preserve_bounded_legacy_total_and_task_truth():
    source = _read("app/services/stores/postgres/dashboard_read_queries.py")

    assert "source.status = statuses.source_status" in source
    assert "workspace_rank <= 100" in source
    assert "CASE WHEN status = 'pending' THEN 0 ELSE 1 END" in source
    assert "COUNT(*) OVER () AS bounded_total" in source
    assert "COUNT(*) FILTER (WHERE status = 'pending')" not in source


def test_case_counts_are_restricted_to_page_execution_ids():
    source = _read("app/services/stores/postgres/dashboard_read_queries.py")

    assert "JOIN page_ids" in source
    assert "page_ids.execution_id = source.execution_id" in source
    assert "GROUP BY source.execution_id" in source


def test_dashboard_store_applies_a_statement_timeout_to_every_method():
    source = _read("app/services/stores/postgres/dashboard_read_store.py")

    assert "SET LOCAL statement_timeout = '10000ms'" in source
    assert source.count("self._set_statement_timeout(conn)") >= 3


def test_dashboard_status_mappings_preserve_legacy_fallbacks():
    assignment = map_task_to_assignment(
        task={
            "id": "task-1",
            "execution_id": "execution-1",
            "case_title": "Playbook",
            "task_type": "tool_execution",
            "description": "Run tool",
            "status": "cancelled",
            "created_at": "2026-08-01T00:00:00+00:00",
            "started_at": None,
            "completed_at": None,
        },
        workspace_id="workspace-1",
        workspace_name="Workspace",
        owner_user_id="user-1",
    )
    case = map_execution_to_case(
        execution={
            "id": "execution-1",
            "status": "stale",
            "playbook_code": "demo",
            "metadata": {},
            "created_at": "2026-08-01T00:00:00+00:00",
            "updated_at": "2026-08-01T00:00:00+00:00",
        },
        workspace_id="workspace-1",
        workspace_name="Workspace",
        owner_user_id="user-1",
    )

    assert assignment["status"] == "cancelled"
    assert case["status"] == "open"


def test_saved_views_use_identity_only_and_explicit_columns():
    route = _read("app/routes/core/dashboard.py")
    store = _read("app/services/stores/postgres/saved_views_store.py")

    saved_view_section = route.split("# ==================== Saved Views", 1)[1]
    assert "Depends(get_current_identity)" in saved_view_section
    assert "Depends(get_current_user)" not in saved_view_section
    assert "SELECT *" not in store
    assert "SET LOCAL statement_timeout = '10000ms'" in store


def test_local_auth_workspace_scope_is_id_only_and_thread_offloaded():
    auth = _read("app/dependencies/auth.py")
    workspace_store = _read("app/services/stores/postgres/workspaces_store.py")

    assert "store.list_workspace_ids(owner_user_id=user_id, limit=200)" in auth
    assert "await asyncio.to_thread(_get_local_workspace_ids, user_id)" in auth
    id_method = workspace_store.split("def list_workspace_ids", 1)[1].split(
        "def list_workspace_summaries", 1
    )[0]
    assert "SELECT id" in id_method
    assert "SELECT *" not in id_method
    assert "ORDER BY updated_at DESC, id" in id_method


def test_dashboard_errors_remain_redacted_and_retryable_for_recovery():
    source = _read("app/routes/core/dashboard.py")

    assert "detail=str(e)" not in source
    assert "classify_database_error" in source
    assert '"error_code": "runtime_database_unavailable"' in source
    assert 'headers={"Retry-After": "30"}' in source
    assert 'detail={"error_code": "dashboard_query_failed"}' in source


def test_complete_dashboard_paths_are_registered_as_p0_surfaces():
    registry = (_backend_root().parent / "ci/product_semantic_surfaces.yaml").read_text(
        encoding="utf-8"
    )
    runtime_budget = registry.split(
        "id: psc.local-core.runtime-task-read-budget.v1",
        maxsplit=1,
    )[1].split("\n  - id:", maxsplit=1)[0]

    expected_paths = [
        "backend/app/dependencies/auth.py",
        "backend/app/routes/core/dashboard.py",
        "backend/app/services/dashboard_aggregator.py",
        "backend/app/services/dashboard_mappings.py",
        "backend/app/services/stores/postgres/dashboard_read_queries.py",
        "backend/app/services/stores/postgres/dashboard_read_store.py",
        "backend/app/services/stores/postgres/saved_views_store.py",
        "backend/app/services/stores/postgres/workspaces_store.py",
        "backend/tests/dashboard_read_plane_budget_spec.py",
        "web-console/src/app/work/hooks/useDashboard.ts",
        "web-console/src/app/work/components/DashboardView.tsx",
    ]
    for path in expected_paths:
        assert path in runtime_budget
