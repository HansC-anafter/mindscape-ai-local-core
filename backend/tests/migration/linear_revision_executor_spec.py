from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
EXECUTOR = (
    ROOT
    / "backend/app/services/migrations/linear_revision_executor.py"
)


def test_linear_executor_owns_lock_and_head_compare_and_swap() -> None:
    source = EXECUTOR.read_text(encoding="utf-8")
    assert "pg_advisory_xact_lock" in source
    assert "LOCK TABLE alembic_version IN SHARE ROW EXCLUSIVE MODE" in source
    assert "linear_revision_parent_head_changed" in source
    assert "UPDATE alembic_version" in source
    assert "WHERE version_num = :parent_revision" in source
    assert "linear_revision_head_compare_and_swap_failed" in source
    assert "linear_revision_receipt_readback_mismatch" in source


def test_linear_executor_runs_upgrade_inside_transactional_operations_context() -> None:
    source = EXECUTOR.read_text(encoding="utf-8")
    assert "with engine.begin() as connection" in source
    assert "MigrationContext.configure" in source
    assert "with Operations.context(migration_context)" in source
    assert "upgrade()" in source
