import os
from pathlib import Path

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _repo_root() -> Path | None:
    candidates = [Path(__file__).resolve().parents[2]]
    project_root = os.getenv("LOCAL_CORE_PROJECT_ROOT")
    if project_root:
        candidates.append(Path(project_root))
    for candidate in candidates:
        if (candidate / "docker-compose.yml").is_file():
            return candidate
    return None


def test_postgres_compose_uses_managed_runtime_image():
    repo_root = _repo_root()
    if repo_root is None:
        pytest.skip("Repository root files are not mounted in this container")

    compose = (repo_root / "docker-compose.yml").read_text(encoding="utf-8")

    assert "dockerfile: docker/postgres/Dockerfile" in compose
    assert "shared_preload_libraries=pg_stat_statements" in compose
    assert "pg_stat_statements.track=all" in compose


def test_runtime_images_include_reclaim_client_package():
    repo_root = _repo_root()
    if repo_root is None:
        pytest.skip("Repository root files are not mounted in this container")

    backend_dockerfile = (repo_root / "Dockerfile.backend").read_text(encoding="utf-8")
    postgres_dockerfile = (
        repo_root / "docker/postgres/Dockerfile"
    ).read_text(encoding="utf-8")

    assert "postgresql-${PG_MAJOR}-repack" in backend_dockerfile
    assert "postgresql-${PG_MAJOR}-repack" in postgres_dockerfile
    assert "postgresql-client-${PG_MAJOR}" in backend_dockerfile


def test_postgres_extension_migration_is_single_existing_db_enablement_path():
    migration = (
        BACKEND_ROOT
        / "alembic_migrations/postgres/versions/"
        / "20260513203000_enable_postgres_observability_extensions.py"
    ).read_text(encoding="utf-8")

    assert 'op.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")' in migration
    assert 'op.execute("CREATE EXTENSION IF NOT EXISTS pg_repack")' in migration
    assert "DROP EXTENSION" not in migration
