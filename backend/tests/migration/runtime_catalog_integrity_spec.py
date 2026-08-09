import importlib.util
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from backend.app.services.migrations.orchestrator import MigrationOrchestrator
from backend.app.services.migrations.runtime_catalog_integrity_facade import (
    resolve_runtime_catalog_snapshot,
)
from backend.app.services.migrations.runtime_locations import (
    configure_runtime_version_locations,
)
from backend.app.services.migrations.scanner import MigrationMetadata


def _write_revision(path: Path, revision: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"revision = '{revision}'\ndown_revision = None\nbranch_labels = None\n",
        encoding="utf-8",
    )


def _config(tmp_path: Path, declared: Path) -> Config:
    scripts = tmp_path / "alembic_migrations"
    scripts.mkdir(exist_ok=True)
    (scripts / "env.py").write_text("# test\n", encoding="utf-8")
    ini = tmp_path / "alembic.ini"
    ini.write_text(
        "[alembic]\n"
        "script_location = alembic_migrations\n"
        f"version_locations = {declared.as_posix()}\n"
        "version_path_separator = os\n",
        encoding="utf-8",
    )
    return Config(ini.as_posix())


def test_active_capability_revision_replaces_same_id_pack_tombstone(
    tmp_path: Path,
) -> None:
    revision = "20260311000000"
    declared = tmp_path / "declared"
    _write_revision(
        declared / f"{revision}_pack_schema_tombstone.py",
        revision,
    )
    _write_revision(declared / "core_revision.py", "core_revision")
    capability = tmp_path / "capabilities" / "ig"
    (capability / "migrations.yaml").parent.mkdir(parents=True)
    (capability / "migrations.yaml").write_text(
        "db: postgres\n"
        f"revisions:\n  - \"{revision}\"\n"
        "migration_paths:\n  - \"migrations/versions/\"\n",
        encoding="utf-8",
    )
    _write_revision(
        capability / "migrations" / "versions" / f"{revision}_create_ig.py",
        revision,
    )
    config = _config(tmp_path, declared)

    locations = configure_runtime_version_locations(
        config,
        capabilities_root=tmp_path / "capabilities",
        db_type="postgres",
    )
    config.set_main_option("script_location", (tmp_path / "alembic_migrations").as_posix())
    script = ScriptDirectory.from_config(config)

    assert declared.as_posix() not in locations
    assert script.get_revision(revision).path.endswith(f"{revision}_create_ig.py")
    assert script.get_revision("core_revision") is not None


def test_catalog_integrity_facade_returns_complete_runtime_snapshot() -> None:
    result = resolve_runtime_catalog_snapshot(
        db_type="postgres",
        current_revisions={"head_revision"},
        runtime_known_revisions_resolver=lambda _db_type: {
            "base_revision",
            "head_revision",
        },
        applied_revisions_resolver=lambda _db_type, _heads: {
            "base_revision",
            "head_revision",
        },
    )

    assert result == {
        "status": "success",
        "catalog_complete": True,
        "current_revisions": ["head_revision"],
        "unresolved_current_heads": [],
        "runtime_known_revisions": ["base_revision", "head_revision"],
        "applied_revisions": ["base_revision", "head_revision"],
    }


def test_two_active_capabilities_cannot_share_revision_id(tmp_path: Path) -> None:
    revision = "shared_revision"
    declared = tmp_path / "declared"
    _write_revision(declared / "core_revision.py", "core_revision")
    for code in ("alpha", "beta"):
        capability = tmp_path / "capabilities" / code
        capability.mkdir(parents=True)
        (capability / "migrations.yaml").write_text(
            "db: postgres\n"
            f"revisions:\n  - \"{revision}\"\n"
            "migration_paths:\n  - \"migrations/versions/\"\n",
            encoding="utf-8",
        )
        _write_revision(
            capability / "migrations" / "versions" / f"{revision}.py",
            revision,
        )

    with pytest.raises(ValueError, match="revision collision"):
        configure_runtime_version_locations(
            _config(tmp_path, declared),
            capabilities_root=tmp_path / "capabilities",
            db_type="postgres",
        )


def test_dry_run_fails_closed_when_catalog_is_unavailable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    orchestrator = MigrationOrchestrator(
        tmp_path,
        {"postgres": tmp_path / "alembic.ini"},
    )
    metadata = MigrationMetadata(
        capability_code="ig",
        db_type="postgres",
        revisions=["ig_revision"],
    )
    monkeypatch.setattr(orchestrator.scanner, "scan_capabilities", lambda: [metadata])
    monkeypatch.setattr(
        orchestrator.dependency_resolver,
        "topological_sort",
        lambda items: items,
    )
    monkeypatch.setattr(
        orchestrator,
        "_get_current_revisions",
        lambda _db_type: ["live_head"],
    )
    monkeypatch.setattr(
        orchestrator,
        "_get_runtime_known_revisions",
        lambda _db_type: set(),
    )

    result = orchestrator.dry_run("postgres")

    assert result["status"] == "error"
    assert result["catalog_complete"] is False
    assert result["unresolved_current_heads"] == ["live_head"]


def test_dry_run_checks_catalog_when_no_capability_metadata_exists(
    tmp_path: Path,
    monkeypatch,
) -> None:
    orchestrator = MigrationOrchestrator(
        tmp_path,
        {"postgres": tmp_path / "alembic.ini"},
    )
    monkeypatch.setattr(orchestrator.scanner, "scan_capabilities", lambda: [])
    monkeypatch.setattr(
        orchestrator,
        "_get_current_revisions",
        lambda _db_type: ["unresolved_live_head"],
    )
    monkeypatch.setattr(
        orchestrator,
        "_get_runtime_known_revisions",
        lambda _db_type: {"known_revision"},
    )

    result = orchestrator.dry_run("postgres")

    assert result["status"] == "error"
    assert result["catalog_complete"] is False
    assert result["unresolved_current_heads"] == ["unresolved_live_head"]


def test_vector_dry_run_reports_catalog_failure_without_secondary_exception(
    tmp_path: Path,
    monkeypatch,
) -> None:
    orchestrator = MigrationOrchestrator(
        tmp_path,
        {"vector": tmp_path / "alembic.ini"},
    )
    monkeypatch.setattr(orchestrator, "_load_script_directory", lambda _db_type: object())
    monkeypatch.setattr(
        orchestrator,
        "_get_current_revisions",
        lambda _db_type: ["unresolved_live_head"],
    )
    monkeypatch.setattr(
        orchestrator,
        "_strict_catalog_snapshot",
        lambda _db_type, _current_revisions: {
            "status": "error",
            "catalog_complete": False,
            "unresolved_current_heads": ["unresolved_live_head"],
        },
    )

    result = orchestrator.dry_run("vector")

    assert result["status"] == "revision_catalog_unavailable"
    assert result["unresolved_current_heads"] == ["unresolved_live_head"]


def test_apply_never_executes_after_fail_closed_dry_run(
    tmp_path: Path,
    monkeypatch,
) -> None:
    orchestrator = MigrationOrchestrator(
        tmp_path,
        {"postgres": tmp_path / "alembic.ini"},
    )
    monkeypatch.setattr(
        orchestrator.validator,
        "validate_environment",
        lambda *_args: {"database": True},
    )
    monkeypatch.setattr(
        orchestrator,
        "_get_env_requirements",
        lambda _db_type: {"postgres_url": "postgresql://test"},
    )
    monkeypatch.setattr(
        orchestrator,
        "dry_run",
        lambda _db_type: {"status": "error", "error": "catalog incomplete"},
    )
    monkeypatch.setattr(
        orchestrator,
        "_run_alembic_upgrade",
        lambda *_args: pytest.fail("upgrade must not execute"),
    )

    assert orchestrator.apply("postgres")["status"] == "error"


def test_migration_cli_returns_nonzero_for_fail_closed_results() -> None:
    cli_path = (
        Path(__file__).resolve().parents[3]
        / "backend"
        / "app"
        / "services"
        / "migrations"
        / "cli.py"
    )
    spec = importlib.util.spec_from_file_location(
        "migration_cli_exit_test_module",
        cli_path,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)

    assert module._result_exit_code({"status": "error"}) == 2
    assert module._result_exit_code({"status": "success"}) == 0
