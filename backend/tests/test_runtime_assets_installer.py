import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.install_result import InstallResult
from app.services.runtime_assets_installer import RuntimeAssetsInstaller


def test_install_scripts_copies_runtime_assets(tmp_path):
    local_core_root = tmp_path / "local-core"
    capabilities_dir = local_core_root / "backend" / "app" / "capabilities"
    capabilities_dir.mkdir(parents=True)

    cap_dir = tmp_path / "extracted" / "layer_asset_forge"
    scripts_dir = cap_dir / "scripts"
    nested_dir = scripts_dir / "nested"
    pycache_dir = scripts_dir / "__pycache__"
    cache_file_dir = scripts_dir / "nested" / "__pycache__"
    nested_dir.mkdir(parents=True)
    pycache_dir.mkdir(parents=True)
    cache_file_dir.mkdir(parents=True)

    (scripts_dir / "__init__.py").write_text("# package\n", encoding="utf-8")
    (scripts_dir / "laf_pose_worker.py").write_text("MAX_INSTANCES = 8\n", encoding="utf-8")
    (scripts_dir / "run_pose_worker.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    (scripts_dir / ".DS_Store").write_text("ignore-me\n", encoding="utf-8")
    (nested_dir / "helper.py").write_text("HELPER = True\n", encoding="utf-8")
    (nested_dir / "config.yaml").write_text("version: 1\n", encoding="utf-8")
    (pycache_dir / "laf_pose_worker.cpython-312.pyc").write_bytes(b"compiled")
    (cache_file_dir / "helper.cpython-312.pyc").write_bytes(b"compiled")

    stale_target_dir = capabilities_dir / "layer_asset_forge" / "scripts"
    stale_target_dir.mkdir(parents=True)
    (stale_target_dir / "obsolete.py").write_text("OBSOLETE = True\n", encoding="utf-8")

    installer = RuntimeAssetsInstaller(
        local_core_root=local_core_root,
        capabilities_dir=capabilities_dir,
    )
    result = InstallResult(capability_code="layer_asset_forge")

    installer.install_scripts(cap_dir, "layer_asset_forge", result)

    target_scripts_dir = capabilities_dir / "layer_asset_forge" / "scripts"
    assert (target_scripts_dir / "__init__.py").exists()
    assert (target_scripts_dir / "laf_pose_worker.py").read_text(encoding="utf-8") == "MAX_INSTANCES = 8\n"
    assert (target_scripts_dir / "run_pose_worker.sh").read_text(encoding="utf-8") == "#!/usr/bin/env bash\n"
    assert (target_scripts_dir / "nested" / "helper.py").read_text(encoding="utf-8") == "HELPER = True\n"
    assert (target_scripts_dir / "nested" / "config.yaml").read_text(encoding="utf-8") == "version: 1\n"
    assert not (target_scripts_dir / "__pycache__" / "laf_pose_worker.cpython-312.pyc").exists()
    assert not (target_scripts_dir / "nested" / "__pycache__" / "helper.cpython-312.pyc").exists()
    assert not (target_scripts_dir / ".DS_Store").exists()
    assert not (target_scripts_dir / "obsolete.py").exists()
    assert set(result.installed.get("scripts", [])) == {
        "laf_pose_worker.py",
        "run_pose_worker.sh",
        "nested/helper.py",
        "nested/config.yaml",
    }


def test_install_tools_replaces_existing_runtime_tree(tmp_path):
    local_core_root = tmp_path / "local-core"
    capabilities_dir = local_core_root / "backend" / "app" / "capabilities"
    capabilities_dir.mkdir(parents=True)

    cap_dir = tmp_path / "extracted" / "content_variant_strategy"
    tools_dir = cap_dir / "tools"
    tools_dir.mkdir(parents=True)
    (tools_dir / "__init__.py").write_text("# tools\n", encoding="utf-8")
    (tools_dir / "variant_projection_targets.py").write_text("TARGETS = True\n", encoding="utf-8")

    stale_target_dir = capabilities_dir / "content_variant_strategy" / "tools"
    stale_target_dir.mkdir(parents=True)
    (stale_target_dir / "cross_pack_projection.py").write_text("STALE = True\n", encoding="utf-8")

    installer = RuntimeAssetsInstaller(
        local_core_root=local_core_root,
        capabilities_dir=capabilities_dir,
    )
    result = InstallResult(capability_code="content_variant_strategy")

    installer.install_tools(cap_dir, "content_variant_strategy", result)

    target_tools_dir = capabilities_dir / "content_variant_strategy" / "tools"
    assert (target_tools_dir / "__init__.py").exists()
    assert (target_tools_dir / "variant_projection_targets.py").read_text(encoding="utf-8") == "TARGETS = True\n"
    assert not (target_tools_dir / "cross_pack_projection.py").exists()


def test_install_services_replaces_existing_runtime_tree(tmp_path):
    local_core_root = tmp_path / "local-core"
    capabilities_dir = local_core_root / "backend" / "app" / "capabilities"
    capabilities_dir.mkdir(parents=True)

    cap_dir = tmp_path / "extracted" / "content_variant_strategy"
    services_dir = cap_dir / "services"
    object_layer_dir = services_dir / "object_layer"
    object_layer_dir.mkdir(parents=True)
    (services_dir / "__init__.py").write_text("# services\n", encoding="utf-8")
    (services_dir / "projection_envelope_service.py").write_text("ENVELOPE = True\n", encoding="utf-8")
    (object_layer_dir / "__init__.py").write_text("# package\n", encoding="utf-8")

    stale_target_dir = capabilities_dir / "content_variant_strategy" / "services"
    stale_target_dir.mkdir(parents=True)
    (stale_target_dir / "cross_pack_projection_service.py").write_text("STALE = True\n", encoding="utf-8")
    (stale_target_dir / "variant_projection_service.py").write_text("STALE = True\n", encoding="utf-8")

    installer = RuntimeAssetsInstaller(
        local_core_root=local_core_root,
        capabilities_dir=capabilities_dir,
    )
    result = InstallResult(capability_code="content_variant_strategy")

    installer.install_services(cap_dir, "content_variant_strategy", result)

    target_services_dir = capabilities_dir / "content_variant_strategy" / "services"
    assert (target_services_dir / "__init__.py").exists()
    assert (target_services_dir / "projection_envelope_service.py").read_text(encoding="utf-8") == "ENVELOPE = True\n"
    assert (target_services_dir / "object_layer" / "__init__.py").exists()
    assert not (target_services_dir / "cross_pack_projection_service.py").exists()
    assert not (target_services_dir / "variant_projection_service.py").exists()


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
    assert not (
        alembic_versions_dir / "20260317000000_create_direction_tables.py"
    ).exists()
    assert not (
        alembic_versions_dir
        / "20260322000001_add_storyboard_manifest_artifact_type.py"
    ).exists()
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
