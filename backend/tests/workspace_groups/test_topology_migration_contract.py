from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
MIGRATION = (
    ROOT
    / "backend"
    / "alembic_migrations"
    / "postgres"
    / "versions"
    / "20260715120000_converge_workspace_group_topology.py"
)


def test_workspace_group_foundation_has_an_independent_named_branch():
    source = MIGRATION.read_text(encoding="utf-8")

    assert 'revision = "20260715120000"' in source
    assert "down_revision = None" in source
    assert 'branch_labels = ("workspace_group_knowledge_foundation",)' in source
    assert "20260715010000" not in source
    assert "SET lock_timeout = '15s'" in source
    assert "SET statement_timeout = '120s'" in source
