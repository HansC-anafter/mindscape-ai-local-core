from pathlib import Path


def test_migration_uses_concurrent_indexes_for_workspace_quota_release_paths():
    repo_root = Path(__file__).resolve().parents[3]
    migration = (
        repo_root
        / "backend"
        / "alembic_migrations"
        / "postgres"
        / "versions"
        / "20260615043000_add_workspace_quota_release_indexes.py"
    ).read_text(encoding="utf-8")

    assert "CREATE INDEX CONCURRENTLY IF NOT EXISTS" in migration
    assert "idx_tasks_cold_workspace_quota_due_shard" in migration
    assert "idx_tasks_ready_running_ws_reserved" in migration
    assert "idx_tasks_ready_running_ws_pack_selector" in migration
    assert "idx_tasks_ready_running_ws_playbook_selector" in migration
    assert "workspace_allocation_required" in migration
    assert "workspace_allocation_disabled" in migration
    assert "DROP INDEX CONCURRENTLY IF EXISTS" in migration
