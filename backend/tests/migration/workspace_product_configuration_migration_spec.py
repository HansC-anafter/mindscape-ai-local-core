from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
MIGRATION = (
    ROOT
    / "backend/alembic_migrations/postgres/versions/"
    "20260725120000_add_workspace_product_configuration.py"
)


def test_workspace_product_configuration_uses_gate0_branch() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "20260725120000"' in source
    assert 'down_revision = "20260715130000"' in source
    assert 'depends_on = "20260716020000"' in source
    assert "product_capability_catalog_versions" in source
    assert "workspace_product_configuration_scopes" in source
    assert "workspace_product_configuration_assignments" in source
    assert "workspace_product_configuration_receipts" in source
    assert "sqlite" not in source.lower()


def test_active_catalog_and_scope_constraints_are_database_owned() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    assert "uq_product_catalog_one_active" in source
    assert "chk_workspace_product_admission_owner" in source
    assert "chk_workspace_product_receipt_revision" in source
