import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from backend.app.services.install_result import InstallResult  # noqa: E402
from backend.app.services.runtime_assets_installer import (  # noqa: E402
    RuntimeAssetsInstaller,
)


def _write_pack(cap_dir: Path) -> None:
    tools_dir = cap_dir / "tools"
    services_dir = cap_dir / "services"
    helper_dir = tools_dir / "following_analyzer"
    core_dir = services_dir / "reference_catalog_store_core"
    helper_dir.mkdir(parents=True)
    core_dir.mkdir(parents=True)

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
    assert not (capabilities_dir.parent / ".capability-install-staging").exists()


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
