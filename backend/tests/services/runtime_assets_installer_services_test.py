from pathlib import Path
import sys
from types import SimpleNamespace

LOCAL_CORE_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "mindscape-ai-local-core"
)
BACKEND_ROOT = LOCAL_CORE_ROOT / "backend"
for candidate in (LOCAL_CORE_ROOT, BACKEND_ROOT):
    candidate_str = str(candidate)
    if candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

from backend.app.services.install_result import InstallResult
from backend.app.services.runtime_assets_installer import RuntimeAssetsInstaller
from backend.app.services.runtime_assets_installer_core import migrations as migrations_module


def test_install_services_copies_init_and_subdirectories(tmp_path):
    cap_dir = tmp_path / "capability_src"
    services_dir = cap_dir / "services"
    adapters_dir = services_dir / "adapters"
    adapters_dir.mkdir(parents=True)

    (services_dir / "__init__.py").write_text("# init\n", encoding="utf-8")
    (services_dir / "production_orchestrator.py").write_text(
        "VALUE = 'ok'\n",
        encoding="utf-8",
    )
    (adapters_dir / "__init__.py").write_text("# adapters\n", encoding="utf-8")
    (adapters_dir / "human_adapter.py").write_text(
        "class HumanAdapter: pass\n",
        encoding="utf-8",
    )

    local_core_root = tmp_path / "local_core"
    capabilities_dir = local_core_root / "backend" / "app" / "capabilities"
    capabilities_dir.mkdir(parents=True)

    installer = RuntimeAssetsInstaller(
        local_core_root=local_core_root,
        capabilities_dir=capabilities_dir,
    )
    result = InstallResult(capability_code="demo_capability")

    installer.install_services(cap_dir, "demo_capability", result)

    target_services_dir = capabilities_dir / "demo_capability" / "services"
    assert (target_services_dir / "__init__.py").exists()
    assert (target_services_dir / "production_orchestrator.py").exists()
    assert (target_services_dir / "adapters" / "__init__.py").exists()
    assert (target_services_dir / "adapters" / "human_adapter.py").exists()
    assert "production_orchestrator" in result.installed["services"]
    assert "adapters" in result.installed["service_dirs"]


def test_execute_migrations_falls_back_to_latest_declared_revision(tmp_path, monkeypatch):
    local_core_root = tmp_path / "local_core"
    capabilities_dir = local_core_root / "backend" / "app" / "capabilities"
    capability_dir = capabilities_dir / "ig"
    versions_dir = capability_dir / "migrations" / "versions"
    versions_dir.mkdir(parents=True, exist_ok=True)
    (local_core_root / "backend" / "alembic.ini").parent.mkdir(parents=True, exist_ok=True)
    (local_core_root / "backend" / "alembic.ini").write_text("[alembic]\n", encoding="utf-8")
    (local_core_root / "backend" / "alembic_migrations" / "postgres" / "versions").mkdir(
        parents=True,
        exist_ok=True,
    )
    (local_core_root / "backend" / "alembic" / "postgres" / "versions").mkdir(
        parents=True,
        exist_ok=True,
    )
    (capability_dir / "migrations.yaml").write_text(
        "revisions:\n"
        '  - "20260124170000"\n'
        '  - "20260329010000"\n'
        '  - "20260410000000"\n'
        'migration_paths:\n'
        '  - "migrations/versions/"\n',
        encoding="utf-8",
    )
    for revision in ("20260124170000", "20260329010000", "20260410000000"):
        (versions_dir / f"{revision}_stub.py").write_text(
            f'revision = "{revision}"\n'
            'down_revision = None\n'
            'branch_labels = None\n'
            'depends_on = None\n',
            encoding="utf-8",
        )

    class _FakeResult:
        def __init__(self, rows):
            self._rows = rows

        def __iter__(self):
            return iter(self._rows)

    class _FakeConnection:
        def execute(self, *_args, **_kwargs):
            return _FakeResult([])

        def commit(self):
            return None

    class _FakeEngine:
        def connect(self):
            class _Ctx:
                def __enter__(self_inner):
                    return _FakeConnection()

                def __exit__(self_inner, exc_type, exc, tb):
                    return False

            return _Ctx()

    called_revisions = []

    class _FakeOrchestrator:
        def __init__(self, *_args, **_kwargs):
            pass

        def _run_alembic_upgrade(self, _config, revision):
            called_revisions.append(revision)
            return revision == "20260410000000"

    monkeypatch.setattr(migrations_module, "pack_has_branch_label", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(migrations_module, "detect_revision_conflicts", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        "app.services.migrations.orchestrator.MigrationOrchestrator",
        _FakeOrchestrator,
    )
    monkeypatch.setattr(
        "backend.app.services.migrations.orchestrator.MigrationOrchestrator",
        _FakeOrchestrator,
    )
    monkeypatch.setattr("sqlalchemy.create_engine", lambda *_args, **_kwargs: _FakeEngine())
    monkeypatch.setattr("sqlalchemy.inspect", lambda *_args, **_kwargs: SimpleNamespace(get_table_names=lambda: []))
    monkeypatch.setattr("app.database.config.get_postgres_url_core", lambda: "postgresql://test")
    monkeypatch.setattr("backend.app.database.config.get_postgres_url_core", lambda: "postgresql://test")

    result = InstallResult(capability_code="ig")

    migrations_module.execute_migrations(
        local_core_root=local_core_root,
        capabilities_dir=capabilities_dir,
        capability_code="ig",
        result=result,
    )

    assert called_revisions == ["ig@head", "20260410000000"]
    assert result.migration_status["ig"] == "applied"
