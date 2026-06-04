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


class _FakeConnection:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, _query):
        return []

    def commit(self):
        return None


class _FakeEngine:
    def connect(self):
        return _FakeConnection()

    def dispose(self):
        return None


class _FakeInspector:
    def get_table_names(self):
        return []


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


def test_execute_migrations_uses_declared_revisions_before_branch_scope(
    monkeypatch,
    tmp_path,
):
    calls = []
    local_core_root, capabilities_dir = _prepare_demo_capability(
        tmp_path,
        include_migrations_yaml=True,
    )
    _patch_migration_runtime(monkeypatch, calls)

    result = InstallResult(capability_code="demo")
    migrations.execute_migrations(
        local_core_root=local_core_root,
        capabilities_dir=capabilities_dir,
        capability_code="demo",
        result=result,
    )

    assert calls == ["demo_rev"]
    assert result.migration_status == {"demo": "applied"}


def test_execute_migrations_keeps_branch_scope_for_auto_discovered_pack(
    monkeypatch,
    tmp_path,
):
    calls = []
    local_core_root, capabilities_dir = _prepare_demo_capability(
        tmp_path,
        include_migrations_yaml=False,
    )
    _patch_migration_runtime(monkeypatch, calls)

    result = InstallResult(capability_code="demo")
    migrations.execute_migrations(
        local_core_root=local_core_root,
        capabilities_dir=capabilities_dir,
        capability_code="demo",
        result=result,
    )

    assert calls == ["demo@head"]
    assert result.migration_status == {"demo": "applied"}


def _prepare_demo_capability(tmp_path, *, include_migrations_yaml: bool):
    local_core_root = tmp_path / "local-core"
    backend_root = local_core_root / "backend"
    capabilities_dir = backend_root / "app" / "capabilities"
    capability_dir = capabilities_dir / "demo"
    versions_dir = capability_dir / "migrations" / "versions"
    versions_dir.mkdir(parents=True)
    (backend_root / "alembic.ini").write_text("[alembic]\n", encoding="utf-8")
    (versions_dir / "demo_rev_create_demo_table.py").write_text(
        '\n'.join(
            [
                'revision = "demo_rev"',
                "down_revision = None",
                'branch_labels = ("demo",)',
                "depends_on = None",
                "",
                "def upgrade():",
                "    pass",
                "",
            ]
        ),
        encoding="utf-8",
    )
    if include_migrations_yaml:
        (capability_dir / "migrations.yaml").write_text(
            "db: postgres\n"
            "revisions:\n"
            '  - "demo_rev"\n'
            "migration_paths:\n"
            '  - "migrations/versions/"\n',
            encoding="utf-8",
        )
    return local_core_root, capabilities_dir


def _patch_migration_runtime(monkeypatch, calls):
    class FakeMigrationOrchestrator:
        def __init__(self, *_args, **_kwargs):
            pass

        def _get_applied_revisions(self, _db_type, _current_revisions):
            return set()

        def _run_alembic_upgrade(self, _alembic_config, revision):
            calls.append(revision)
            return True

    monkeypatch.setattr(
        migrations,
        "check_core_write_readiness",
        lambda **_kwargs: DatabaseWriteReadiness(
            ready=True,
            reason="ready",
            retry_after_seconds=0,
        ),
    )
    monkeypatch.setattr(
        "app.services.migrations.orchestrator.MigrationOrchestrator",
        FakeMigrationOrchestrator,
    )
    monkeypatch.setattr(
        "app.database.config.get_postgres_url_core_session",
        lambda: "postgresql://example",
    )
    monkeypatch.setattr(
        "app.database.engine_factory.create_session_semantics_engine",
        lambda *_args, **_kwargs: _FakeEngine(),
    )
    monkeypatch.setattr("sqlalchemy.inspect", lambda _engine: _FakeInspector())
