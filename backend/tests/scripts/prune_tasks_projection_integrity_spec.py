from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[2] / "scripts/prune_tasks_retention.py"
).read_text(encoding="utf-8")


def test_retention_batch_deletes_projection_from_the_same_locked_candidates():
    batch_sql = SCRIPT.split("def _delete_batch_query", maxsplit=1)[1].split(
        "def _table_size_query", maxsplit=1
    )[0]

    assert "SELECT id" in batch_sql
    assert "FROM tasks" in batch_sql
    assert "FOR UPDATE" in batch_sql
    assert "DELETE FROM task_summary_projection AS projection" in batch_sql
    assert "WHERE projection.task_id = batch.id" in batch_sql
    assert "DELETE FROM tasks AS t" in batch_sql
    assert "WHERE t.id = batch.id" in batch_sql
    assert batch_sql.index("DELETE FROM task_summary_projection") < batch_sql.index(
        "DELETE FROM tasks AS t"
    )


def test_retention_scope_and_batch_budget_remain_unchanged():
    assert 'DEFAULT_PACK_PATTERNS = ("ig_%", "ig.%", "ig/%")' in SCRIPT
    assert 'DEFAULT_STATUSES = ("succeeded", "failed", "cancelled_by_user")' in SCRIPT
    assert 'default=30' in SCRIPT
    assert 'default=500' in SCRIPT
    assert 'action="store_true"' in SCRIPT
