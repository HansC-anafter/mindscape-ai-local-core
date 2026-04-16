from pathlib import Path

from alembic.config import Config

from app.services.migrations.runtime_locations import configure_runtime_version_locations


def _write_revision(path: Path, revision: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                f'revision = "{revision}"',
                'down_revision = None',
                'branch_labels = None',
            ]
        ),
        encoding="utf-8",
    )


def _build_config(tmp_path: Path, declared_versions_dir: Path) -> Config:
    scripts_dir = tmp_path / "alembic_migrations"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    (scripts_dir / "env.py").write_text("# env placeholder\n", encoding="utf-8")

    config_path = tmp_path / "alembic.ini"
    config_path.write_text(
        "\n".join(
            [
                "[alembic]",
                "script_location = alembic_migrations",
                f"version_locations = {declared_versions_dir.as_posix()}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return Config(config_path.as_posix())


def test_configure_runtime_version_locations_skips_fully_vendored_capability_paths(
    tmp_path: Path,
) -> None:
    declared_versions_dir = tmp_path / "declared_versions"
    _write_revision(declared_versions_dir / "20260329010000_create_ig_seed_collections.py", "20260329010000")

    capabilities_root = tmp_path / "capabilities"
    capability_dir = capabilities_root / "ig"
    capability_dir.mkdir(parents=True, exist_ok=True)
    (capability_dir / "migrations.yaml").write_text(
        "\n".join(
            [
                "db: postgres",
                "revisions:",
                '  - "20260329010000"',
                "migration_paths:",
                '  - "migrations/versions/"',
            ]
        ),
        encoding="utf-8",
    )
    _write_revision(
        capability_dir / "migrations" / "versions" / "20260329010000_create_ig_seed_collections.py",
        "20260329010000",
    )

    config = _build_config(tmp_path, declared_versions_dir)

    locations = configure_runtime_version_locations(
        config,
        capabilities_root=capabilities_root,
        db_type="postgres",
    )

    assert locations == [declared_versions_dir.as_posix()]


def test_configure_runtime_version_locations_stages_only_missing_runtime_revisions(
    tmp_path: Path,
) -> None:
    declared_versions_dir = tmp_path / "declared_versions"
    _write_revision(declared_versions_dir / "20260328003000_shared.py", "20260328003000")

    capabilities_root = tmp_path / "capabilities"
    capability_dir = capabilities_root / "performance_direction"
    capability_dir.mkdir(parents=True, exist_ok=True)
    (capability_dir / "migrations.yaml").write_text(
        "\n".join(
            [
                "db: postgres",
                "revisions:",
                '  - "20260328003000"',
                '  - "20260330000001"',
                "migration_paths:",
                '  - "migrations/versions/"',
            ]
        ),
        encoding="utf-8",
    )
    capability_versions_dir = capability_dir / "migrations" / "versions"
    _write_revision(capability_versions_dir / "20260328003000_shared.py", "20260328003000")
    _write_revision(capability_versions_dir / "20260330000001_unique.py", "20260330000001")

    config = _build_config(tmp_path, declared_versions_dir)

    locations = configure_runtime_version_locations(
        config,
        capabilities_root=capabilities_root,
        db_type="postgres",
    )

    assert locations[0] == declared_versions_dir.as_posix()
    assert len(locations) == 2

    staged_dir = Path(locations[1])
    assert staged_dir != capability_versions_dir
    assert sorted(path.name for path in staged_dir.glob("*.py")) == [
        "20260330000001_unique.py",
    ]
