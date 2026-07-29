from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (
    ROOT
    / "alembic_migrations"
    / "postgres"
    / "versions"
    / "20260729120000_create_workspace_access_control.py"
)


def test_migration_owns_exact_six_tables_and_partial_active_grant_unique_index():
    source = MIGRATION.read_text(encoding="utf-8")
    for table in (
        "access_principals",
        "access_identity_bindings",
        "access_scope_policies",
        "access_grants",
        "access_invitations",
        "access_audit_events",
    ):
        assert source.count(f'"{table}"') >= 2
    assert "uq_access_grant_active_scope" in source
    assert "postgresql_where=sa.text(\"status = 'active'\")" in source
    assert "token_hash" in source
    assert 'sa.Column("invitation_token"' not in source
