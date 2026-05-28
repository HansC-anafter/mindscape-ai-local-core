import pytest

from app.services.runtime_assets_installer_core import migrations
from app.services.install_result import InstallResult
from backend.app.database.write_readiness import (
    DatabaseWriteNotReadyError,
    DatabaseWriteReadiness,
)


class _FakeOrchestrator:
    def __init__(self, applied):
        self.applied = applied
        self.calls = []

    def _get_applied_revisions(self, db_type, current_revisions):
        self.calls.append((db_type, current_revisions))
        return self.applied


class _FailingOrchestrator:
    def _get_applied_revisions(self, db_type, current_revisions):
        raise RuntimeError("script directory unavailable")


def test_pending_revisions_excludes_applied_ancestry():
    orchestrator = _FakeOrchestrator({"rev_1", "rev_2", "rev_3"})

    applied = migrations._resolve_applied_revisions(orchestrator, {"rev_3"})
    pending = migrations._pending_revisions(
        ["rev_1", "rev_2", "rev_3", "rev_4"],
        applied,
    )

    assert orchestrator.calls == [("postgres", {"rev_3"})]
    assert pending == ["rev_4"]


def test_applied_revision_resolution_falls_back_to_current_heads():
    applied = migrations._resolve_applied_revisions(
        _FailingOrchestrator(),
        {"head_a", "head_b"},
    )

    assert applied == {"head_a", "head_b"}


def test_execute_migrations_maps_write_not_ready_to_waiting_db(monkeypatch, tmp_path):
    local_core_root = tmp_path / "local-core"
    backend_root = local_core_root / "backend"
    capabilities_dir = backend_root / "app" / "capabilities"
    capability_dir = capabilities_dir / "demo"
    capability_dir.mkdir(parents=True)
    (backend_root / "alembic.ini").write_text("[alembic]\n", encoding="utf-8")
    (capability_dir / "migrations.yaml").write_text(
        "revisions:\n  - demo_rev\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        migrations,
        "check_core_write_readiness",
        lambda **_kwargs: DatabaseWriteReadiness(
            ready=False,
            reason="postgres_recovery_in_progress",
            retry_after_seconds=13,
        ),
    )

    result = InstallResult(capability_code="demo")

    with pytest.raises(DatabaseWriteNotReadyError):
        migrations.execute_migrations(
            local_core_root=local_core_root,
            capabilities_dir=capabilities_dir,
            capability_code="demo",
            result=result,
        )

    assert result.migration_status == {"demo": "waiting_db"}
