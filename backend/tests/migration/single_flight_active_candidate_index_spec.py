from pathlib import Path


def test_migration_uses_concurrent_partial_index_for_active_pending_candidates():
    repo_root = Path(__file__).resolve().parents[3]
    migration = (
        repo_root
        / "backend"
        / "alembic_migrations"
        / "postgres"
        / "versions"
        / "20260614015500_add_single_flight_active_candidate_index.py"
    ).read_text(encoding="utf-8")

    assert "CREATE INDEX CONCURRENTLY IF NOT EXISTS" in migration
    assert "idx_tasks_pending_active_concurrency_key" in migration
    assert "frontier_state IN ('ready', 'running')" in migration
    assert "blocked_reason IS NULL OR blocked_reason = ''" in migration
    assert "DROP INDEX CONCURRENTLY IF EXISTS" in migration
