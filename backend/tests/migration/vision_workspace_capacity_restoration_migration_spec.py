from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
MIGRATION = (
    ROOT
    / "backend/alembic_migrations/postgres/versions/"
    "20260725140000_restore_authorized_vision_workspace_capacity.py"
)


def test_vision_capacity_restoration_extends_current_postgres_head() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "20260725140000"' in source
    assert 'down_revision = "20260725130000"' in source
    assert "SET LOCAL lock_timeout = '5s'" in source
    assert "SET LOCAL statement_timeout = '30s'" in source


def test_restoration_is_exact_and_blueprint_owned() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    assert "linked_enabled_blueprint_entry" in source
    assert "blueprint.state = 'enabled'" in source
    assert "allocation.blueprint_entry_id = entry.blueprint_entry_id" in source
    assert "allocation.queue_shard = 'vision_local'" in source
    assert "workspace_vision_local_single_inflight_2026_06_07" in source
    assert "entry.max_parallel_task_claims = 4" in source
    assert "max_worker_target = entry.max_parallel_task_claims" in source
    assert "max_concurrency = entry.max_parallel_task_claims" in source
    assert "max_parallel_task_claims = entry.max_parallel_task_claims" in source
    assert "UPDATE tasks" not in source


def test_downgrade_never_reapplies_single_inflight_override() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    downgrade = source.split("def downgrade()", 1)[1]
    assert "pass" in downgrade
    assert "UPDATE host_resource_workspace_allocations" not in downgrade
