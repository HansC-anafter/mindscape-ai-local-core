from app.services.install_result import InstallResult
from app.services.runtime_assets_installer import RuntimeAssetsInstaller


def test_install_capability_models_copies_runtime_assets(tmp_path):
    local_core_root = tmp_path / "local-core"
    capabilities_dir = local_core_root / "backend" / "app" / "capabilities"
    capabilities_dir.mkdir(parents=True)

    cap_dir = tmp_path / "extracted" / "ig"
    models_dir = cap_dir / "models"
    nested_dir = models_dir / "nested"
    pycache_dir = models_dir / "__pycache__"
    nested_dir.mkdir(parents=True)
    pycache_dir.mkdir(parents=True)

    (models_dir / "__init__.py").write_text("# package\n", encoding="utf-8")
    (models_dir / "vision_schema.py").write_text("SCHEMA = True\n", encoding="utf-8")
    (models_dir / "tag_vocabulary.json").write_text('{"tags": []}\n', encoding="utf-8")
    (nested_dir / "config.yaml").write_text("version: 1\n", encoding="utf-8")
    (pycache_dir / "vision_schema.cpython-312.pyc").write_bytes(b"compiled")

    installer = RuntimeAssetsInstaller(
        local_core_root=local_core_root,
        capabilities_dir=capabilities_dir,
    )
    result = InstallResult(capability_code="ig")

    installer.install_capability_models(cap_dir, "ig", result)

    target_models_dir = capabilities_dir / "ig" / "models"
    assert (target_models_dir / "__init__.py").exists()
    assert (target_models_dir / "vision_schema.py").read_text(encoding="utf-8") == "SCHEMA = True\n"
    assert (target_models_dir / "tag_vocabulary.json").read_text(encoding="utf-8") == '{"tags": []}\n'
    assert (target_models_dir / "nested" / "config.yaml").read_text(encoding="utf-8") == "version: 1\n"
    assert not (target_models_dir / "__pycache__" / "vision_schema.cpython-312.pyc").exists()
    assert set(result.installed.get("capability_models", [])) == {
        "vision_schema.py",
        "tag_vocabulary.json",
        "nested/config.yaml",
    }


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
    assert not any("has no branch_labels" in warning for warning in result.warnings)


def test_install_bundles_copies_pack_local_bundle_assets(tmp_path):
    local_core_root = tmp_path / "local-core"
    capabilities_dir = local_core_root / "backend" / "app" / "capabilities"
    capabilities_dir.mkdir(parents=True)

    cap_dir = tmp_path / "extracted" / "character_training"
    bundle_dir = cap_dir / "bundles" / "character-pack-001" / "loras"
    bundle_dir.mkdir(parents=True)
    (bundle_dir / "hero.safetensors").write_bytes(b"hero-lora")

    installer = RuntimeAssetsInstaller(
        local_core_root=local_core_root,
        capabilities_dir=capabilities_dir,
    )
    result = InstallResult(capability_code="character_training")

    installer.install_bundles(cap_dir, "character_training", result)

    target_file = (
        capabilities_dir
        / "character_training"
        / "bundles"
        / "character-pack-001"
        / "loras"
        / "hero.safetensors"
    )
    assert target_file.read_bytes() == b"hero-lora"
    assert result.installed.get("bundles") == [
        "character-pack-001/loras/hero.safetensors"
    ]
