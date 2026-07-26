from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATION = (
    REPO_ROOT
    / "backend"
    / "alembic_migrations"
    / "postgres"
    / "versions"
    / "20260727120000_add_host_runtime_bindings.py"
)


def test_host_runtime_binding_migration_is_normalized_and_indexed():
    source = MIGRATION.read_text(encoding="utf-8")

    for table in (
        "host_runtime_bindings",
        "host_runtime_attestations",
        "workspace_host_grants",
        "host_runtime_receipts",
    ):
        assert f'"{table}"' in source
    assert "uq_host_runtime_binding_identity" in source
    assert "idx_workspace_host_grants_effective" in source
    assert "idx_host_runtime_attestations_latest" in source
    assert "chk_host_runtime_binding_digest_identity" in source
    assert "chk_workspace_host_grant_operation" in source
    assert "chk_workspace_host_grant_voice_scope" in source
    assert "SET lock_timeout = '15s'" in source
    assert "SET statement_timeout = '120s'" in source
    assert "worker" not in source.lower()
