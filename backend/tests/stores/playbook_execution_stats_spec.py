from backend.app.services.stores.playbook_execution_stats import (
    build_playbook_workspace_stats,
)


def test_build_playbook_workspace_stats_groups_statuses_and_sorts_workspaces():
    rows = [
        ("workspace-a", "completed", "2026-06-14T10:00:00+00:00", None),
        ("workspace-b", "running", "2026-06-14T12:00:00+00:00", None),
        ("workspace-a", "failed", "2026-06-14T11:00:00+00:00", None),
        ("workspace-a", "pending", "2026-06-14T09:00:00+00:00", None),
    ]

    stats = build_playbook_workspace_stats("demo-playbook", rows)

    assert stats["playbook_code"] == "demo-playbook"
    assert stats["total_executions"] == 4
    assert stats["total_workspaces"] == 2

    first_workspace = stats["workspace_stats"][0]
    assert first_workspace["workspace_id"] == "workspace-a"
    assert first_workspace["execution_count"] == 3
    assert first_workspace["success_count"] == 1
    assert first_workspace["failed_count"] == 1
    assert first_workspace["running_count"] == 1
    assert first_workspace["last_executed_at"] == "2026-06-14T11:00:00+00:00"

    second_workspace = stats["workspace_stats"][1]
    assert second_workspace["workspace_id"] == "workspace-b"
    assert second_workspace["execution_count"] == 1
    assert second_workspace["running_count"] == 1
