from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
MIGRATION = (
    ROOT
    / "backend"
    / "alembic_migrations"
    / "postgres"
    / "versions"
    / "20260715123000_add_workspace_group_execution_snapshots.py"
)


def test_snapshot_reference_converges_bootstrap_created_columns():
    source = MIGRATION.read_text(encoding="utf-8")

    assert "ADD COLUMN IF NOT EXISTS" in source
    assert "contains values longer than 64 characters" in source
    assert "TYPE VARCHAR(64)" in source
    assert "FROM pg_constraint" in source
    assert "CREATE INDEX IF NOT EXISTS" in source
    assert source.count("_ensure_snapshot_reference(") == 3
    assert 'table_name="meeting_sessions"' in source
    assert 'table_name="task_irs"' in source


def test_snapshot_migration_keeps_one_exact_revision_path():
    source = MIGRATION.read_text(encoding="utf-8")

    assert 'revision = "20260715123000"' in source
    assert 'down_revision = "20260715120000"' in source
    assert "upgrade heads" not in source
    assert "stamp" not in source
