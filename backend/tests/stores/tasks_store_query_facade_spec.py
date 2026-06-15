from pathlib import Path

from backend.app.services.stores.tasks_store._queries import TasksStoreQueryMixin


QUERY_MODULES = (
    "_queries.py",
    "_query_common.py",
    "_query_candidates.py",
    "_query_lists.py",
    "_query_admission.py",
    "_query_cold_release.py",
    "_query_meeting.py",
)


def test_tasks_store_query_facade_exposes_existing_methods():
    expected_methods = (
        "_select_fair_runnable_tasks",
        "list_runner_candidate_projections_by_ids",
        "list_tasks_by_workspace",
        "list_due_admission_deferred_tasks",
        "list_due_workspace_quota_tasks",
        "list_tasks_by_meeting_session",
        "list_running_playbook_execution_tasks",
    )

    for method_name in expected_methods:
        assert hasattr(TasksStoreQueryMixin, method_name)


def test_tasks_store_query_modules_stay_below_large_file_gate():
    module_dir = Path(__file__).parents[2] / "app/services/stores/tasks_store"

    for module_name in QUERY_MODULES:
        line_count = len((module_dir / module_name).read_text().splitlines())
        assert line_count < 500, module_name
