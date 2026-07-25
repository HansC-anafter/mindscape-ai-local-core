from pathlib import Path

from backend.app.services.migrations import cli as migration_cli
from backend.app.services.migrations.orchestrator import MigrationOrchestrator


class _FakeRevision:
    def __init__(self, revision: str, down_revision: str | None = "parent"):
        self.revision = revision
        self.down_revision = down_revision


class _FakeScriptDirectory:
    def iterate_revisions(self, head: str, _base: str):
        assert head == "20260715130000"
        return [
            _FakeRevision("20260715130000"),
            _FakeRevision("20260715120000"),
        ]

    def get_revision(self, revision: str):
        return _FakeRevision(revision)


def test_apply_revision_rejects_symbolic_heads(tmp_path: Path) -> None:
    orchestrator = MigrationOrchestrator(
        tmp_path,
        {"postgres": tmp_path / "alembic.postgres.ini"},
    )

    result = orchestrator.apply_revision("postgres", "heads")

    assert result["status"] == "invalid_revision"


def test_apply_revision_runs_only_exact_target_chain(tmp_path: Path, monkeypatch) -> None:
    orchestrator = MigrationOrchestrator(
        tmp_path,
        {"postgres": tmp_path / "alembic.postgres.ini"},
    )
    monkeypatch.setattr(
        orchestrator.validator,
        "validate_environment",
        lambda _db_type, _requirements: {"database_connection": True},
    )
    monkeypatch.setattr(
        orchestrator,
        "_get_env_requirements",
        lambda _db_type: {},
    )
    monkeypatch.setattr(
        orchestrator,
        "_load_script_directory",
        lambda _db_type: _FakeScriptDirectory(),
    )
    monkeypatch.setattr(orchestrator, "_get_current_revisions", lambda _db_type: [])
    monkeypatch.setattr(
        orchestrator,
        "_get_applied_revisions",
        lambda _db_type, _heads: set(),
    )
    captured: dict[str, object] = {}

    def _upgrade(config: Path, revision: str) -> bool:
        captured["config"] = config
        captured["revision"] = revision
        return True

    monkeypatch.setattr(orchestrator, "_run_alembic_upgrade", _upgrade)

    result = orchestrator.apply_revision("postgres", "20260715130000")

    assert result == {
        "status": "completed",
        "target_revision": "20260715130000",
        "migrations_applied": 2,
        "revisions": ["20260715120000", "20260715130000"],
    }
    assert captured == {
        "config": tmp_path / "alembic.postgres.ini",
        "revision": "20260715130000",
    }


def test_plan_revision_matches_apply_revision_chain(tmp_path: Path, monkeypatch) -> None:
    orchestrator = MigrationOrchestrator(
        tmp_path,
        {"postgres": tmp_path / "alembic.postgres.ini"},
    )
    monkeypatch.setattr(
        orchestrator,
        "_load_script_directory",
        lambda _db_type: _FakeScriptDirectory(),
    )
    monkeypatch.setattr(orchestrator, "_get_current_revisions", lambda _db_type: [])
    monkeypatch.setattr(
        orchestrator,
        "_get_applied_revisions",
        lambda _db_type, _heads: set(),
    )

    result = orchestrator.plan_revision("postgres", "20260715130000")

    assert result == {
        "status": "success",
        "target_revision": "20260715130000",
        "migrations_pending": 2,
        "revisions": ["20260715120000", "20260715130000"],
    }


def test_apply_revision_uses_transactional_executor_for_one_independent_branch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    target = _FakeRevision("20260716020000", down_revision=None)
    target.branch_labels = ("capability_pack_install_atomicity",)
    target.module = object()

    class _IndependentScriptDirectory:
        def get_revision(self, revision: str):
            assert revision == target.revision
            return target

        def iterate_revisions(self, head: str, _base: str):
            assert head == target.revision
            return [target]

    orchestrator = MigrationOrchestrator(
        tmp_path,
        {"postgres": tmp_path / "alembic.postgres.ini"},
    )
    monkeypatch.setattr(
        orchestrator.validator,
        "validate_environment",
        lambda _db_type, _requirements: {"database_connection": True},
    )
    monkeypatch.setattr(
        orchestrator,
        "_get_env_requirements",
        lambda _db_type: {"postgres_url": "postgresql://example"},
    )
    monkeypatch.setattr(
        orchestrator,
        "_load_script_directory",
        lambda _db_type: _IndependentScriptDirectory(),
    )
    monkeypatch.setattr(orchestrator, "_get_current_revisions", lambda _db_type: [])
    monkeypatch.setattr(
        orchestrator,
        "_get_applied_revisions",
        lambda _db_type, _heads: set(),
    )
    monkeypatch.setattr(
        "backend.app.services.migrations.orchestrator.require_migration_execution_allowed",
        lambda _config, _revision: None,
    )
    captured = {}
    monkeypatch.setattr(
        "backend.app.services.migrations.orchestrator.execute_independent_revision",
        lambda **kwargs: captured.update(kwargs) or True,
    )
    monkeypatch.setattr(
        orchestrator,
        "_run_alembic_upgrade",
        lambda *_args: (_ for _ in ()).throw(
            AssertionError("independent revision must not traverse unrelated heads")
        ),
    )

    result = orchestrator.apply_revision("postgres", target.revision)

    assert result["status"] == "completed"
    assert result["revisions"] == [target.revision]
    assert captured == {
        "revision_script": target,
        "postgres_url": "postgresql://example",
        "revision": target.revision,
    }


def test_apply_revision_uses_transactional_executor_for_direct_applied_parent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    target = _FakeRevision("20260725140000", down_revision="20260725130000")
    target.module = object()

    class _LinearScriptDirectory:
        def get_revision(self, revision: str):
            assert revision == target.revision
            return target

        def iterate_revisions(self, head: str, _base: str):
            assert head == target.revision
            return [target]

    orchestrator = MigrationOrchestrator(
        tmp_path,
        {"postgres": tmp_path / "alembic.postgres.ini"},
    )
    monkeypatch.setattr(
        orchestrator.validator,
        "validate_environment",
        lambda _db_type, _requirements: {"database_connection": True},
    )
    monkeypatch.setattr(
        orchestrator,
        "_get_env_requirements",
        lambda _db_type: {"postgres_url": "postgresql://example"},
    )
    monkeypatch.setattr(
        orchestrator,
        "_load_script_directory",
        lambda _db_type: _LinearScriptDirectory(),
    )
    monkeypatch.setattr(
        orchestrator,
        "_get_current_revisions",
        lambda _db_type: ["20260725130000", "unrelated-head"],
    )
    monkeypatch.setattr(
        orchestrator,
        "_get_applied_revisions",
        lambda _db_type, _heads: {"20260725130000", "unrelated-head"},
    )
    monkeypatch.setattr(
        "backend.app.services.migrations.orchestrator.require_migration_execution_allowed",
        lambda _config, _revision: None,
    )
    captured = {}
    monkeypatch.setattr(
        "backend.app.services.migrations.orchestrator.execute_linear_revision",
        lambda **kwargs: captured.update(kwargs) or True,
    )
    monkeypatch.setattr(
        orchestrator,
        "_run_alembic_upgrade",
        lambda *_args: (_ for _ in ()).throw(
            AssertionError("direct child must not traverse unrelated heads")
        ),
    )

    result = orchestrator.apply_revision("postgres", target.revision)

    assert result["status"] == "completed"
    assert result["revisions"] == [target.revision]
    assert captured == {
        "revision_script": target,
        "postgres_url": "postgresql://example",
        "revision": target.revision,
        "expected_parent_revision": "20260725130000",
    }


def test_cli_targeted_dry_run_uses_the_same_revision_plan(monkeypatch, capsys) -> None:
    class _FakeOrchestrator:
        def plan_revision(self, db_type: str, revision: str):
            assert db_type == "postgres"
            assert revision == "20260715130000"
            return {
                "status": "success",
                "target_revision": revision,
                "migrations_pending": 2,
                "revisions": ["20260715120000", revision],
            }

        def apply_revision(self, _db_type: str, _revision: str):
            raise AssertionError("targeted dry-run must not apply migrations")

    monkeypatch.setattr(
        migration_cli,
        "_build_orchestrator",
        lambda: _FakeOrchestrator(),
    )

    migration_cli.apply_command(
        "postgres",
        dry_run=True,
        revision="20260715130000",
    )

    output = capsys.readouterr().out
    assert "Targeted Dry-Run" in output
    assert "20260715120000" in output
    assert "20260715130000" in output
