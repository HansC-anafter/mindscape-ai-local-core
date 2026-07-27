from pathlib import Path

from alembic.config import Config

from app.services.migrations.runtime_locations import (
    append_runtime_version_locations,
    configure_runtime_version_locations,
)


def _write_revision(path: Path, revision: str, *, typed: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    revision_line = (
        f'revision: str = "{revision}"' if typed else f'revision = "{revision}"'
    )
    path.write_text(
        "\n".join(
            [
                revision_line,
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


def test_configure_runtime_version_locations_stages_revision_package_dir(
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
    capability_versions_dir.mkdir(parents=True, exist_ok=True)
    _write_revision(capability_versions_dir / "20260328003000_shared.py", "20260328003000")
    _write_revision(capability_versions_dir / "20260330000001_unique.py", "20260330000001")

    helpers_dir = capability_versions_dir / "helpers"
    helpers_dir.mkdir()
    (helpers_dir / "__init__.py").write_text("", encoding="utf-8")
    (helpers_dir / "reference_catalog_summary_totals.py").write_text(
        "def calculate(x):\n    return x\n",
        encoding="utf-8",
    )

    config = _build_config(tmp_path, declared_versions_dir)

    locations = configure_runtime_version_locations(
        config,
        capabilities_root=capabilities_root,
        db_type="postgres",
    )

    staged_dir = Path(locations[1])
    assert (staged_dir / "helpers" / "__init__.py").exists()
    assert (staged_dir / "helpers" / "reference_catalog_summary_totals.py").exists()


def test_configure_runtime_version_locations_dedupes_typed_revision_assignments(
    tmp_path: Path,
) -> None:
    declared_versions_dir = tmp_path / "declared_versions"
    _write_revision(
        declared_versions_dir / "20260326160000_create_character_training_tables.py",
        "20260326160000",
        typed=True,
    )
    _write_revision(
        declared_versions_dir / "20260327235959_add_character_package_contract_fields.py",
        "20260327235959",
        typed=True,
    )

    capabilities_root = tmp_path / "capabilities"
    capability_dir = capabilities_root / "character_training"
    capability_dir.mkdir(parents=True, exist_ok=True)
    (capability_dir / "migrations.yaml").write_text(
        "\n".join(
            [
                "db: postgres",
                "revisions:",
                '  - "20260326160000"',
                '  - "20260327235959"',
                '  - "20260403143000"',
                "migration_paths:",
                '  - "migrations/versions/"',
            ]
        ),
        encoding="utf-8",
    )
    capability_versions_dir = capability_dir / "migrations" / "versions"
    _write_revision(
        capability_versions_dir / "20260326160000_create_character_training_tables.py",
        "20260326160000",
        typed=True,
    )
    _write_revision(
        capability_versions_dir / "20260327235959_add_character_package_contract_fields.py",
        "20260327235959",
        typed=True,
    )
    _write_revision(
        capability_versions_dir / "20260403143000_add_training_job_runtime_status.py",
        "20260403143000",
        typed=True,
    )

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
        "20260403143000_add_training_job_runtime_status.py",
    ]


def test_candidate_overlay_excludes_same_owner_live_tree(tmp_path: Path) -> None:
    declared_versions_dir = tmp_path / "declared_versions"
    _write_revision(declared_versions_dir / "core_revision.py", "core_revision")

    capabilities_root = tmp_path / "capabilities"
    live_yoga = capabilities_root / "yogacoach"
    live_other = capabilities_root / "ig"
    for capability_dir, revision in (
        (live_yoga, "yoga_revision"),
        (live_other, "ig_revision"),
    ):
        capability_dir.mkdir(parents=True, exist_ok=True)
        (capability_dir / "migrations.yaml").write_text(
            "db: postgres\n"
            f"revisions:\n  - \"{revision}\"\n"
            "migration_paths:\n  - \"migrations/versions/\"\n",
            encoding="utf-8",
        )
        _write_revision(
            capability_dir / "migrations" / "versions" / f"{revision}.py",
            revision,
        )

    candidate_yoga = tmp_path / "candidate" / "yogacoach" / "migrations" / "versions"
    _write_revision(candidate_yoga / "yoga_revision.py", "yoga_revision")
    config = _build_config(tmp_path, declared_versions_dir)

    locations = configure_runtime_version_locations(
        config,
        capabilities_root=capabilities_root,
        db_type="postgres",
        excluded_capability_codes={"yogacoach"},
    )
    locations = append_runtime_version_locations(config, [candidate_yoga])

    assert live_yoga.joinpath("migrations", "versions").as_posix() not in locations
    assert live_other.joinpath("migrations", "versions").as_posix() in locations
    assert candidate_yoga.resolve().as_posix() in locations
