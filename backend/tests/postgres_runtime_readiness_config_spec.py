import os
import subprocess
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
    assert "archive_mode=${LOCAL_CORE_POSTGRES_ARCHIVE_MODE:-off}" in compose
    assert (
        "archive_command=/usr/local/bin/mindscape-archive-wal %p %f "
        "/var/lib/postgresql/wal_archive"
    ) in compose
    assert "archive_command=test ! -f" not in compose
    postgres_dockerfile = (repo_root / "docker/postgres/Dockerfile").read_text(
        encoding="utf-8"
    )
    assert "COPY docker/postgres/archive-wal.sh /usr/local/bin/mindscape-archive-wal" in postgres_dockerfile
    assert "chmod 0755 /usr/local/bin/mindscape-archive-wal" in postgres_dockerfile


def test_postgres_archive_wal_accepts_base_backup_history_files(tmp_path):
    repo_root = _repo_root()
    if repo_root is None:
        pytest.skip("Repository root files are not mounted in this container")

    wal_file = "000000010000032100000001.002CC200.backup"
    source_path = tmp_path / wal_file
    archive_dir = tmp_path / "archive"
    source_bytes = b"START WAL LOCATION: 321/10002CC2 (file 000000010000032100000001)\n"

    archive_dir.mkdir()
    source_path.write_bytes(source_bytes)

    subprocess.run(
        [
            "sh",
            str(repo_root / "docker/postgres/archive-wal.sh"),
            str(source_path),
            wal_file,
            str(archive_dir),
        ],
        check=True,
    )

    assert (archive_dir / wal_file).read_bytes() == source_bytes


def test_postgres_completion_runtime_defines_pooling_replica_and_redis_aof():
    repo_root = _repo_root()
    if repo_root is None:
        pytest.skip("Repository root files are not mounted in this container")

    compose = (repo_root / "docker-compose.yml").read_text(encoding="utf-8")

    assert "pgbouncer:" in compose
    assert "postgres-replica:" in compose
    assert "LOCAL_CORE_DB_POOL_HOST:-pgbouncer" in compose
    assert "DATABASE_URL_CORE_READONLY" in compose
    assert "DATABASE_URL_VECTOR_READONLY" in compose
    assert "mindscape_core_readonly" in compose
    assert "mindscape_vectors_readonly" in compose
    assert "--appendonly" in compose
    assert '"yes"' in compose
    assert "LOCAL_CORE_REDIS_HOST_DIR" in compose

    pgbouncer_ini = (repo_root / "docker/pgbouncer/pgbouncer.ini").read_text(
        encoding="utf-8"
    )
    assert (
        "mindscape_core_readonly = host=postgres-replica port=5432 "
        "dbname=mindscape_core pool_size=10 min_pool_size=0"
    ) in pgbouncer_ini
    assert (
        "mindscape_vectors_readonly = host=postgres-replica port=5432 "
        "dbname=mindscape_vectors user=mindscape_vector_runtime "
        "pool_size=5 min_pool_size=0"
    ) in pgbouncer_ini


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
    assert "pgbouncer" in postgres_dockerfile
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


def test_postgres_reclaim_preflight_wrapper_mounts_verified_backup_dir():
    repo_root = _repo_root()
    if repo_root is None:
        pytest.skip("Repository root files are not mounted in this container")

    script = (
        repo_root / "scripts/maintenance/postgres_reclaim_preflight.sh"
    ).read_text(encoding="utf-8")

    assert "$REPO_ROOT:/repo:ro" in script
    assert "$BACKUP_DIR:/verified-backup:ro" in script
    assert "--verified-backup-dir /verified-backup" in script
    assert "postgres_runtime_preflight_report.py" in script
    assert "PYTHONPYCACHEPREFIX=/tmp/pycache" in script
