import sys
import errno
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from backend.app.services.install_result import InstallResult  # noqa: E402
from backend.app.services.install_integrity import (  # noqa: E402
    compute_dir_hashes,
    prune_stale_installed_files,
    save_install_manifest,
)
from backend.app.services.runtime_assets_installer import (  # noqa: E402
    RuntimeAssetsInstaller,
    _build_staging_root,
)


def _write_pack(cap_dir: Path) -> None:
    tools_dir = cap_dir / "tools"
    services_dir = cap_dir / "services"
    repositories_dir = cap_dir / "repositories"
    helper_dir = tools_dir / "following_analyzer"
    core_dir = services_dir / "reference_catalog_store_core"
    helper_dir.mkdir(parents=True)
    core_dir.mkdir(parents=True)
    repositories_dir.mkdir(parents=True)

    (cap_dir / "manifest.yaml").write_text(
        "code: ig\nversion: 1.2.3\n",
        encoding="utf-8",
    )
    (tools_dir / "__init__.py").write_text("", encoding="utf-8")
    (tools_dir / "ig_analyze_reference.py").write_text(
        "VALUE = 'new-reference'\n",
        encoding="utf-8",
    )
    (helper_dir / "__init__.py").write_text("", encoding="utf-8")
    (helper_dir / "browser_session.py").write_text(
        "BROWSER_SESSION = True\n",
        encoding="utf-8",
    )
    (services_dir / "__init__.py").write_text("", encoding="utf-8")
    (services_dir / "reference_index.py").write_text(
        "REFERENCE_INDEX = True\n",
        encoding="utf-8",
    )
    (core_dir / "__init__.py").write_text("", encoding="utf-8")
    (core_dir / "writer.py").write_text("WRITER = True\n", encoding="utf-8")
    (repositories_dir / "__init__.py").write_text("", encoding="utf-8")
    (repositories_dir / "goal_repository.py").write_text(
        "GOAL_REPOSITORY = True\n", encoding="utf-8"
    )


def _write_ui_dist(cap_dir: Path) -> None:
    components_dir = cap_dir / "ui_dist" / "components"
    components_dir.mkdir(parents=True)
    (components_dir / "IGRunsWorkspaceToolPanel.mjs").write_text(
        "export default function IGRunsWorkspaceToolPanel() {}\n",
        encoding="utf-8",
    )
    (cap_dir / "ui_dist" / "ui_dist_manifest.json").write_text(
        json.dumps(
            {
                "components": [
                    {
                        "code": "IGRunsWorkspaceToolPanel",
                        "asset_path": "components/IGRunsWorkspaceToolPanel.mjs",
                        "export": "default",
                        "runtime": "mindscape-react-bridge-v1",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def test_runtime_assets_publish_complete_tree_from_staging(tmp_path: Path):
    root = tmp_path / "local-core"
    capabilities_dir = root / "backend" / "app" / "capabilities"
    capabilities_dir.mkdir(parents=True)

    existing_tools = capabilities_dir / "ig" / "tools"
    existing_tools.mkdir(parents=True)
    (existing_tools / "old.py").write_text("OLD = True\n", encoding="utf-8")

    cap_dir = tmp_path / "pack" / "ig"
    cap_dir.mkdir(parents=True)
    _write_pack(cap_dir)

    result = InstallResult(capability_code="ig")
    installer = RuntimeAssetsInstaller(
        local_core_root=root,
        capabilities_dir=capabilities_dir,
    )
    installer.install_all(cap_dir, "ig", {"code": "ig", "version": "1.2.3"}, result)

    target = capabilities_dir / "ig"
    assert (target / "manifest.yaml").exists()
    assert (target / "tools" / "ig_analyze_reference.py").exists()
    assert (target / "tools" / "following_analyzer" / "browser_session.py").exists()
    assert (target / "services" / "reference_index.py").exists()
    assert (target / "services" / "reference_catalog_store_core" / "writer.py").exists()
    assert (target / "repositories" / "goal_repository.py").exists()
    assert "repositories" in result.installed["runtime_namespace_dirs"]
    assert not (capabilities_dir.parent / ".capability-install-staging").exists()


def test_runtime_assets_staging_root_stays_outside_watched_app_tree(
    monkeypatch,
    tmp_path: Path,
):
    root = tmp_path / "local-core"
    capabilities_dir = root / "backend" / "app" / "capabilities"
    capabilities_dir.mkdir(parents=True)

    cap_dir = tmp_path / "pack" / "ig"
    cap_dir.mkdir(parents=True)
    _write_pack(cap_dir)

    staging_base = tmp_path / "runtime-staging"
    monkeypatch.setenv(
        "MINDSCAPE_CAPABILITY_INSTALL_STAGING_ROOT",
        str(staging_base),
    )

    result = InstallResult(capability_code="ig")
    installer = RuntimeAssetsInstaller(
        local_core_root=root,
        capabilities_dir=capabilities_dir,
    )
    installer.install_all(cap_dir, "ig", {"code": "ig", "version": "1.2.3"}, result)

    assert not (capabilities_dir.parent / ".capability-install-staging").exists()
    assert not staging_base.exists()


def test_default_staging_root_uses_local_core_data_filesystem(
    monkeypatch,
    tmp_path: Path,
):
    monkeypatch.delenv(
        "MINDSCAPE_CAPABILITY_INSTALL_STAGING_ROOT",
        raising=False,
    )
    local_core_root = tmp_path / "local-core"

    staging_root = _build_staging_root(
        "ig",
        local_core_root=local_core_root,
    )

    expected_parent = (
        local_core_root / "data" / "mindscape-capability-install-staging"
    )
    assert staging_root.parent == expected_parent
    assert staging_root.name.startswith("ig-")
    assert not staging_root.is_relative_to(local_core_root / "backend" / "app")


def test_publish_staged_capability_tree_copies_across_filesystems(
    monkeypatch,
    tmp_path: Path,
):
    root = tmp_path / "local-core"
    capabilities_dir = root / "backend" / "app" / "capabilities"
    target = capabilities_dir / "ig"
    staging = tmp_path / "runtime-staging" / "capabilities" / "ig"
    (target / "tools").mkdir(parents=True)
    (staging / "tools").mkdir(parents=True)
    (target / "tools" / "old.py").write_text("OLD = True\n", encoding="utf-8")
    (staging / "tools" / "new.py").write_text("NEW = True\n", encoding="utf-8")

    original_rename = Path.rename

    def fake_rename(self, target_path):
        if self == staging:
            raise OSError(errno.EXDEV, "Invalid cross-device link")
        return original_rename(self, target_path)

    monkeypatch.setattr(Path, "rename", fake_rename)

    installer = RuntimeAssetsInstaller(
        local_core_root=root,
        capabilities_dir=capabilities_dir,
    )
    installer._publish_staged_capability_tree(
        staging_cap_dir=staging,
        target_cap_dir=target,
        capability_code="ig",
    )

    assert (target / "tools" / "new.py").read_text(encoding="utf-8") == "NEW = True\n"
    assert not (target / "tools" / "old.py").exists()
    assert not staging.exists()


def test_runtime_assets_failure_keeps_existing_live_tree(monkeypatch, tmp_path: Path):
    root = tmp_path / "local-core"
    capabilities_dir = root / "backend" / "app" / "capabilities"
    live_tools = capabilities_dir / "ig" / "tools"
    live_tools.mkdir(parents=True)
    (live_tools / "ig_analyze_reference.py").write_text(
        "VALUE = 'old-reference'\n",
        encoding="utf-8",
    )

    cap_dir = tmp_path / "pack" / "ig"
    cap_dir.mkdir(parents=True)
    _write_pack(cap_dir)

    def fail_services(self, *_args, **_kwargs):
        raise RuntimeError("forced service install failure")

    monkeypatch.setattr(RuntimeAssetsInstaller, "install_services", fail_services)

    result = InstallResult(capability_code="ig")
    installer = RuntimeAssetsInstaller(
        local_core_root=root,
        capabilities_dir=capabilities_dir,
    )

    with pytest.raises(RuntimeError, match="forced service install failure"):
        installer.install_all(cap_dir, "ig", {"code": "ig", "version": "1.2.3"}, result)

    assert (live_tools / "ig_analyze_reference.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 'old-reference'\n"
    assert not (live_tools / "following_analyzer" / "browser_session.py").exists()


def test_stale_prune_preserves_generated_runtime_asset_sidecars(tmp_path: Path):
    installed = tmp_path / "installed" / "ig"
    incoming = tmp_path / "incoming" / "ig"
    (installed / "tools").mkdir(parents=True)
    incoming.mkdir(parents=True)

    (installed / "manifest.yaml").write_text(
        "code: ig\nversion: 1.0.19\n",
        encoding="utf-8",
    )
    (installed / "ui_runtime_assets.json").write_text(
        '{"components": []}\n',
        encoding="utf-8",
    )
    (installed / "tools" / "removed.py").write_text(
        "REMOVED = True\n",
        encoding="utf-8",
    )
    save_install_manifest(installed, "1.0.19", compute_dir_hashes(installed))

    (incoming / "manifest.yaml").write_text(
        "code: ig\nversion: 1.0.19\n",
        encoding="utf-8",
    )

    pruned = prune_stale_installed_files(installed, incoming)

    assert (installed / "ui_runtime_assets.json").exists()
    assert not (installed / "tools" / "removed.py").exists()
    assert "tools/removed.py" in pruned
    assert "ui_runtime_assets.json" not in pruned


def test_runtime_assets_install_all_preserves_ui_runtime_sidecar_after_prune(
    tmp_path: Path,
):
    root = tmp_path / "local-core"
    capabilities_dir = root / "backend" / "app" / "capabilities"
    target = capabilities_dir / "ig"
    (target / "tools").mkdir(parents=True)
    (target / "manifest.yaml").write_text(
        "code: ig\nversion: 1.0.19\n",
        encoding="utf-8",
    )
    (target / "ui_runtime_assets.json").write_text(
        '{"version": "1.0.19", "components": []}\n',
        encoding="utf-8",
    )
    (target / "tools" / "removed.py").write_text(
        "REMOVED = True\n",
        encoding="utf-8",
    )
    save_install_manifest(target, "1.0.19", compute_dir_hashes(target))

    cap_dir = tmp_path / "pack" / "ig"
    cap_dir.mkdir(parents=True)
    _write_pack(cap_dir)
    _write_ui_dist(cap_dir)

    result = InstallResult(capability_code="ig")
    installer = RuntimeAssetsInstaller(
        local_core_root=root,
        capabilities_dir=capabilities_dir,
    )
    installer.install_all(
        cap_dir,
        "ig",
        {
            "code": "ig",
            "version": "1.0.20",
            "ui_components": [{"code": "IGRunsWorkspaceToolPanel"}],
        },
        result,
    )

    sidecar = target / "ui_runtime_assets.json"
    assert sidecar.exists()
    sidecar_payload = json.loads(sidecar.read_text(encoding="utf-8"))
    assert sidecar_payload["version"] == "1.0.20"
    assert sidecar_payload["components"][0]["asset_path"] == (
        "1.0.20/components/IGRunsWorkspaceToolPanel.mjs"
    )
    assert not (target / "tools" / "removed.py").exists()
