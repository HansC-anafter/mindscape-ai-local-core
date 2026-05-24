from pathlib import Path


def test_capability_host_refresh_hot_path_migration_extends_external_run_observation_graph():
    versions_dir = (
        Path(__file__).resolve().parents[1]
        / "alembic_migrations"
        / "postgres"
        / "versions"
    )
    baseline = versions_dir / "20260521173000_add_external_run_observation_fields.py"
    migration = versions_dir / "20260522143000_add_capability_host_refresh_hot_path_indexes.py"

    assert baseline.exists()
    assert migration.exists()

    source = migration.read_text(encoding="utf-8")
    assert 'down_revision = "20260521173000"' in source
    assert "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_workspace_run_feed_workspace_source_run_latest" in source
    assert "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_runs_workspace_source_status_updated_run" in source
    assert "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_task_summary_projection_workspace_status_pack_updated" in source
    assert "op.get_context().autocommit_block()" in source
