from pathlib import Path

from app.services.runtime_assets_installer import RuntimeAssetsInstaller


def test_runtime_assets_installer_facade_exposes_split_seam_methods(tmp_path):
    installer = RuntimeAssetsInstaller(
        local_core_root=tmp_path / "local-core",
        capabilities_dir=tmp_path / "local-core" / "backend" / "app" / "capabilities",
    )

    assert installer.local_core_root == tmp_path / "local-core"
    assert installer.capabilities_dir == (
        tmp_path / "local-core" / "backend" / "app" / "capabilities"
    )
    for method_name in (
        "install_all",
        "install_scripts",
        "install_database_models",
        "install_ui_components",
        "install_manifest",
        "install_migrations",
        "execute_migrations",
    ):
        assert callable(getattr(installer, method_name))


def test_runtime_assets_installer_static_migration_helpers_remain_on_facade(tmp_path):
    migration_file = tmp_path / "20260317000000_create_tables.py"
    migration_file.write_text(
        "\n".join(
            [
                'revision = "001_create_tables"',
                "down_revision = None",
                'branch_labels = ("demo_pack",)',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    assert RuntimeAssetsInstaller._extract_revision_id(migration_file) == "001_create_tables"
    assert RuntimeAssetsInstaller._extract_down_revision(migration_file) is None
    assert RuntimeAssetsInstaller._extract_branch_labels(migration_file) == ("demo_pack",)


def test_runtime_assets_installer_facade_has_no_extra_constructor_state(tmp_path):
    installer = RuntimeAssetsInstaller(Path(tmp_path), Path(tmp_path) / "capabilities")

    assert sorted(vars(installer)) == ["capabilities_dir", "local_core_root"]
