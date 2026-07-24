from pathlib import Path

from backend.app.routes.core.workspace_product_configuration import (
    _translate_error,
)
from backend.app.services.workspace_product_configuration.errors import (
    CatalogRevisionConflictError,
    ScopeRevisionConflictError,
)


ROOT = Path(__file__).resolve().parents[3]


def test_facade_modules_and_bootstrap_remain_bounded() -> None:
    facade = (
        ROOT
        / "backend/app/services/workspace_product_configuration/facade.py"
    )
    bootstrap = ROOT / "backend/app/app_bootstrap/routes.py"
    assert len(facade.read_text(encoding="utf-8").splitlines()) < 500
    assert len(bootstrap.read_text(encoding="utf-8").splitlines()) < 500


def test_effective_repository_uses_one_indexed_install_truth_aggregate() -> None:
    source = (
        ROOT
        / "backend/app/services/workspace_product_configuration/repository.py"
    ).read_text(encoding="utf-8")
    assert "AS readiness" in source
    assert "pack_install_commit_receipts" in source
    assert "install_commit.committed_at DESC" in source
    assert "install_commit.install_id DESC" in source
    assert "AS commit" not in source
    assert "installed.metadata" not in source
    assert "def load_pack_readiness" not in source


def test_scope_create_uses_cas_safe_conflict_path() -> None:
    source = (
        ROOT
        / "backend/app/services/workspace_product_configuration/repository.py"
    ).read_text(encoding="utf-8")
    assert "ON CONFLICT (scope_kind, scope_id) DO NOTHING" in source
    assert "RETURNING revision" in source
    assert "concurrent.revision" in source


def test_revision_conflict_returns_current_catalog_identity() -> None:
    catalog_hash = "a" * 64
    translated = _translate_error(
        ScopeRevisionConflictError(
            expected_revision=3,
            actual_revision=4,
            current_catalog_hash=catalog_hash,
        )
    )

    assert translated.status_code == 409
    assert translated.detail == {
        "error": "workspace_product_scope_revision_conflict",
        "expected_revision": 3,
        "server_revision": 4,
        "current_catalog_hash": catalog_hash,
    }


def test_catalog_conflict_is_a_revision_409() -> None:
    expected_hash = "a" * 64
    current_hash = "b" * 64
    translated = _translate_error(
        CatalogRevisionConflictError(
            expected_catalog_hash=expected_hash,
            current_catalog_hash=current_hash,
        )
    )

    assert translated.status_code == 409
    assert translated.detail == {
        "error": "product_catalog_revision_conflict",
        "expected_catalog_hash": expected_hash,
        "current_catalog_hash": current_hash,
    }
