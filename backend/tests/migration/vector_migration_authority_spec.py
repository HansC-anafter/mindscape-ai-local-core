from pathlib import Path

from backend.app.services.migrations.database_plan import (
    AUTHORITATIVE_DATABASE_ORDER,
    authoritative_alembic_configs,
)
from backend.app.services.migrations.orchestrator import MigrationOrchestrator


class _Script:
    def __init__(self, revision: str):
        self.revision = revision


class _VectorScripts:
    def walk_revisions(self):
        return [
            _Script("20260727030000"),
            _Script("20260727020000"),
            _Script("20260727010000"),
        ]


class _CoreScripts:
    def get_heads(self):
        return ["core-head-a", "core-head-b"]


def test_authoritative_database_plan_has_one_core_and_vector_config(
    tmp_path: Path,
) -> None:
    configs = authoritative_alembic_configs(tmp_path)

    assert AUTHORITATIVE_DATABASE_ORDER == ("postgres", "vector")
    assert configs == {
        "postgres": tmp_path / "alembic.postgres.ini",
        "vector": tmp_path / "alembic.vector.ini",
    }


def test_vector_dry_run_uses_only_the_host_vector_catalog(
    tmp_path: Path,
    monkeypatch,
) -> None:
    orchestrator = MigrationOrchestrator(
        tmp_path,
        {
            "postgres": tmp_path / "alembic.postgres.ini",
            "vector": tmp_path / "alembic.vector.ini",
        },
    )
    monkeypatch.setattr(
        orchestrator,
        "_load_script_directory",
        lambda db_type: _VectorScripts() if db_type == "vector" else None,
    )
    monkeypatch.setattr(
        orchestrator,
        "_get_current_revisions",
        lambda _db_type: ["20260727010000"],
    )
    monkeypatch.setattr(
        orchestrator,
        "_get_applied_revisions",
        lambda _db_type, _heads: {"20260727010000"},
    )

    result = orchestrator.dry_run("vector")

    assert [item["revision"] for item in result["migrations"]] == [
        "20260727020000",
        "20260727030000",
    ]
    assert {item["capability"] for item in result["migrations"]} == {
        "local_core_host"
    }


def test_vector_target_is_blocked_until_all_core_heads_are_applied(
    tmp_path: Path,
    monkeypatch,
) -> None:
    orchestrator = MigrationOrchestrator(
        tmp_path,
        {
            "postgres": tmp_path / "alembic.postgres.ini",
            "vector": tmp_path / "alembic.vector.ini",
        },
    )
    monkeypatch.setattr(
        orchestrator,
        "_load_script_directory",
        lambda db_type: _CoreScripts() if db_type == "postgres" else None,
    )
    monkeypatch.setattr(
        orchestrator,
        "_get_current_revisions",
        lambda _db_type: ["core-head-a"],
    )
    monkeypatch.setattr(
        orchestrator,
        "_get_applied_revisions",
        lambda _db_type, _heads: {"core-head-a"},
    )

    result = orchestrator.apply_vector_revision_after_core_ready(
        "20260727030000",
        dry_run=True,
    )

    assert result == {
        "status": "core_not_ready",
        "missing_core_heads": ["core-head-b"],
    }


def test_vector_target_uses_exact_revision_after_core_head_readback(
    tmp_path: Path,
    monkeypatch,
) -> None:
    orchestrator = MigrationOrchestrator(
        tmp_path,
        {
            "postgres": tmp_path / "alembic.postgres.ini",
            "vector": tmp_path / "alembic.vector.ini",
        },
    )
    monkeypatch.setattr(
        orchestrator,
        "_load_script_directory",
        lambda db_type: _CoreScripts() if db_type == "postgres" else None,
    )
    monkeypatch.setattr(
        orchestrator,
        "_get_current_revisions",
        lambda _db_type: ["core-head-a", "core-head-b"],
    )
    monkeypatch.setattr(
        orchestrator,
        "_get_applied_revisions",
        lambda _db_type, _heads: {"core-head-a", "core-head-b"},
    )
    captured = {}
    monkeypatch.setattr(
        orchestrator,
        "apply_revision",
        lambda db_type, revision: captured.update(
            {"db_type": db_type, "revision": revision}
        )
        or {
            "status": "completed",
            "target_revision": revision,
        },
    )

    result = orchestrator.apply_vector_revision_after_core_ready(
        "20260727030000"
    )

    assert captured == {
        "db_type": "vector",
        "revision": "20260727030000",
    }
    assert result["status"] == "completed"
    assert result["core_heads_verified"] == ["core-head-a", "core-head-b"]


def test_vector_config_and_env_never_reference_core_or_sqlite() -> None:
    backend_dir = Path(__file__).resolve().parents[2]
    ini = (backend_dir / "alembic.vector.ini").read_text()
    env = (
        backend_dir / "alembic_migrations" / "vector" / "env.py"
    ).read_text()

    assert "alembic_migrations/vector" in ini
    assert "get_postgres_url_vector_session" in env
    assert "pool.NullPool" in env
    assert "get_postgres_url_core_session" not in env
    assert "sqlite" not in env.lower()
