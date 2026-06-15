from pathlib import Path


def test_run_harness_episode_ledger_migration_shape_is_metadata_only() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    migration = (
        repo_root
        / "alembic_migrations"
        / "postgres"
        / "versions"
        / "20260614230000_create_run_harness_episode_ledger.py"
    ).read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS run_harness_episodes" in migration
    assert "CREATE TABLE IF NOT EXISTS run_harness_episode_events" in migration
    assert "CREATE TABLE IF NOT EXISTS run_harness_episode_results" in migration
    assert "intent_envelope_ref" in migration
    assert "selection_ref" in migration
    assert "attempt_id" in migration
    assert "attempt_number" in migration
    assert "payload_ref" in migration
    assert "failure_details" in migration
    assert "score" in migration
    assert "next_action" in migration
    assert "trace_refs" in migration
    assert "JSONB" in migration
    assert "artifact_blob" not in migration
    assert "queue" not in migration.lower()
    assert "worker" not in migration.lower()


def test_run_harness_episode_ledger_migration_has_fixed_read_indexes() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    migration = (
        repo_root
        / "alembic_migrations"
        / "postgres"
        / "versions"
        / "20260614230000_create_run_harness_episode_ledger.py"
    ).read_text(encoding="utf-8")

    assert "idx_run_harness_episodes_run_id" in migration
    assert "idx_run_harness_episodes_workspace_created" in migration
    assert "idx_run_harness_episode_events_sequence" in migration
    assert "idx_run_harness_episode_results_status_updated" in migration
    assert migration.count("CREATE INDEX IF NOT EXISTS idx_run_harness") == 4
    assert "uq_run_harness_episode_events_sequence" in migration
    assert "uq_run_harness_episode_events_episode_event" in migration
