"""The lexical hot path must use one concurrent GIN index."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (
    ROOT
    / "alembic_migrations"
    / "vector"
    / "versions"
    / "20260729010000_external_docs_lexical_index.py"
)


def test_external_docs_lexical_index_is_concurrent_and_expression_exact() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert 'down_revision = "20260727050000"' in source
    assert "CREATE INDEX CONCURRENTLY IF NOT EXISTS" in source
    assert "USING gin" in source
    assert "COALESCE(title, '')" in source
    assert "COALESCE(content, '')" in source
    assert "op.get_context().autocommit_block()" in source
    assert "DROP INDEX CONCURRENTLY IF EXISTS" in source
