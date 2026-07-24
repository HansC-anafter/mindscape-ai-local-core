from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
MIGRATION = (
    ROOT
    / "backend/alembic_migrations/postgres/versions/"
    "20260725130000_create_deployment_control_state.py"
)


def test_deployment_control_migration_follows_wpc_head():
    source = MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "20260725130000"' in source
    assert 'down_revision = "20260725120000"' in source
    assert "deployment_control_state" in source
    assert "chk_deployment_control_singleton" in source
    assert "chk_deployment_control_state_shape" in source
    assert "sqlite" not in source.lower()


def test_repository_owns_atomic_cas_and_monotonic_revision():
    source = (
        ROOT
        / "backend/app/services/deployment_control/state_repository.py"
    ).read_text(encoding="utf-8")
    assert "FOR UPDATE" in source
    assert "FOR SHARE" in source
    assert "ON CONFLICT (id) DO NOTHING" in source
    assert "DeploymentControlStateRevisionConflict" in source
    assert "DeploymentEnvelopeRevisionConflict" in source


def test_facade_and_route_entrypoints_remain_bounded():
    targets = [
        ROOT / "backend/app/services/deployment_control/facade.py",
        ROOT / "backend/app/routes/core/deployment_control.py",
        ROOT / "backend/app/app_bootstrap/routes.py",
    ]
    for target in targets:
        assert len(target.read_text(encoding="utf-8").splitlines()) < 500
