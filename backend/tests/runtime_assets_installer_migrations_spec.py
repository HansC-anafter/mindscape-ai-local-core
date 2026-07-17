import pytest

from app.services.runtime_assets_installer_core import migrations
from app.services.install_result import InstallResult
from app.services.runtime_assets_installer import RuntimeAssetsInstaller
from backend.app.database.write_readiness import (
    DatabaseWriteNotReadyError,
    DatabaseWriteReadiness,
)
from backend.app.services.migrations.execution_policy import (
    apply_migration_subprocess_policy,
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
        return _FakeRows()

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


class _FakeRows(list):
    def fetchall(self):
        return list(self)


def test_migration_subprocess_policy_preserves_existing_options_and_adds_bounds():
    environment = {"PGOPTIONS": "-c application_name=migration-test"}

    apply_migration_subprocess_policy(environment)

    assert environment["PGOPTIONS"] == (
        "-c application_name=migration-test "
        "-c lock_timeout=5000 -c statement_timeout=120000"
    )


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


def test_extract_revision_id_prefers_declared_value_over_filename(tmp_path):
    migration_file = tmp_path / "20260317000000_create_direction_tables.py"
    migration_file.write_text(
        '\n'.join(
            [
                'revision = "001_create_direction_tables"',
                'down_revision = None',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    revision_id = RuntimeAssetsInstaller._extract_revision_id(migration_file)

    assert revision_id == "001_create_direction_tables"


def test_install_migrations_only_requires_branch_label_on_root_revision(tmp_path):
    local_core_root = tmp_path / "local-core"
    capabilities_dir = local_core_root / "backend" / "app" / "capabilities"
    alembic_versions_dir = (
        local_core_root / "backend" / "alembic_migrations" / "postgres" / "versions"
    )
    capabilities_dir.mkdir(parents=True)
    alembic_versions_dir.mkdir(parents=True)

    cap_dir = tmp_path / "extracted" / "performance_direction"
    versions_dir = cap_dir / "migrations" / "versions"
    versions_dir.mkdir(parents=True)
    (cap_dir / "migrations.yaml").write_text(
        "\n".join(
            [
                "db: postgres",
                "depends_on: []",
                "revisions:",
                '  - "20260317000000"',
                '  - "20260322000001"',
                "migration_paths:",
                '  - "migrations/versions/"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (versions_dir / "20260317000000_create_direction_tables.py").write_text(
        "\n".join(
            [
                'revision = "20260317000000"',
                "down_revision = None",
                'branch_labels = ("performance_direction",)',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (versions_dir / "20260322000001_add_storyboard_manifest_artifact_type.py").write_text(
        "\n".join(
            [
                'revision = "20260322000001"',
                'down_revision = "20260317000000"',
                "branch_labels = None",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    installer = RuntimeAssetsInstaller(
        local_core_root=local_core_root,
        capabilities_dir=capabilities_dir,
    )
    result = InstallResult(capability_code="performance_direction")

    installer.install_migrations(cap_dir, "performance_direction", result)

    assert set(result.installed.get("migrations", [])) == {
        "20260317000000_create_direction_tables.py",
        "20260322000001_add_storyboard_manifest_artifact_type.py",
    }
    assert not (
        alembic_versions_dir / "20260317000000_create_direction_tables.py"
    ).exists()
    assert not (
        alembic_versions_dir
        / "20260322000001_add_storyboard_manifest_artifact_type.py"
    ).exists()
    assert not any("has no branch_labels" in warning for warning in result.warnings)


def test_install_migrations_blocks_conflicting_revision_before_copy(tmp_path):
    local_core_root = tmp_path / "local-core"
    capabilities_dir = local_core_root / "backend" / "app" / "capabilities"
    alembic_versions_dir = (
        local_core_root / "backend" / "alembic_migrations" / "postgres" / "versions"
    )
    capabilities_dir.mkdir(parents=True)
    alembic_versions_dir.mkdir(parents=True)

    existing_migration = alembic_versions_dir / "20260328000000_other_capability.py"
    existing_migration.write_text(
        "\n".join(
            [
                'revision = "20260328000000"',
                "down_revision = None",
                'branch_labels = ("other_capability",)',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    cap_dir = tmp_path / "extracted" / "character_training"
    versions_dir = cap_dir / "migrations" / "versions"
    versions_dir.mkdir(parents=True)
    (cap_dir / "migrations.yaml").write_text(
        "\n".join(
            [
                "db: postgres",
                "depends_on: []",
                "revisions:",
                '  - "20260328000000"',
                "migration_paths:",
                '  - "migrations/versions/"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    incoming_migration = (
        versions_dir / "20260328000000_add_character_package_contract_fields.py"
    )
    incoming_migration.write_text(
        "\n".join(
            [
                'revision = "20260328000000"',
                "down_revision = None",
                'branch_labels = ("character_training",)',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    installer = RuntimeAssetsInstaller(
        local_core_root=local_core_root,
        capabilities_dir=capabilities_dir,
    )
    result = InstallResult(capability_code="character_training")

    installer.install_migrations(cap_dir, "character_training", result)

    assert result.migration_status == {"character_training": "conflict"}
    assert any(
        "Migration revision ID conflict detected for character_training" in error
        for error in result.errors
    )
    assert not (alembic_versions_dir / incoming_migration.name).exists()


def test_install_migrations_allows_same_filename_reinstall_without_conflict(tmp_path):
    local_core_root = tmp_path / "local-core"
    capabilities_dir = local_core_root / "backend" / "app" / "capabilities"
    alembic_versions_dir = (
        local_core_root / "backend" / "alembic_migrations" / "postgres" / "versions"
    )
    capabilities_dir.mkdir(parents=True)
    alembic_versions_dir.mkdir(parents=True)

    existing_migration = (
        alembic_versions_dir / "20260328000001_add_character_package_contract_fields.py"
    )
    existing_migration.write_text(
        "\n".join(
            [
                'revision = "20260328000001"',
                "down_revision = None",
                'branch_labels = ("legacy_capability_name",)',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    cap_dir = tmp_path / "extracted" / "character_training"
    versions_dir = cap_dir / "migrations" / "versions"
    versions_dir.mkdir(parents=True)
    (cap_dir / "migrations.yaml").write_text(
        "\n".join(
            [
                "db: postgres",
                "depends_on: []",
                "revisions:",
                '  - "20260328000001"',
                "migration_paths:",
                '  - "migrations/versions/"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    incoming_migration = versions_dir / existing_migration.name
    incoming_migration.write_text(
        "\n".join(
            [
                'revision = "20260328000001"',
                "down_revision = None",
                'branch_labels = ("character_training",)',
                "UPGRADED = True",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    installer = RuntimeAssetsInstaller(
        local_core_root=local_core_root,
        capabilities_dir=capabilities_dir,
    )
    result = InstallResult(capability_code="character_training")

    installer.install_migrations(cap_dir, "character_training", result)

    assert not result.errors
    assert result.migration_status in (None, {})
    assert result.installed.get("migrations") == [incoming_migration.name]
    assert "UPGRADED = True" not in existing_migration.read_text(encoding="utf-8")


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
    class FakeScriptDirectory:
        def get_revision(self, revision):
            return object() if revision == "demo_rev" else None

        def get_heads(self):
            return ["demo_rev"]

    class FakeMigrationOrchestrator:
        def __init__(self, *_args, **_kwargs):
            pass

        def _get_applied_revisions(self, _db_type, _current_revisions):
            return set()

        def _load_script_directory(self, _db_type):
            return FakeScriptDirectory()

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
