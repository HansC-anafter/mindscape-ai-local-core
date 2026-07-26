from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pytest

from backend.app.routes.core.capability_install_core.install_commit_core.filesystem_saga import (
    PreparedCapabilityTree,
)
from backend.app.services.install_result import InstallResult
from backend.app.services.runtime_assets_installer import RuntimeAssetsInstaller


def _canonical(value: dict) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def _fixture(tmp_path: Path) -> tuple[Path, dict, dict]:
    cap_dir = tmp_path / "incoming" / "demo"
    scripts = cap_dir / "scripts"
    scripts.mkdir(parents=True)
    asset = scripts / "host_runtime_entry.py"
    asset.write_text("print('host')\n", encoding="utf-8")
    asset.chmod(0o644)
    requirement = {
        "requirement_code": "demo",
        "entrypoint": "scripts/host_runtime_entry.py",
        "operations": ["watch-screenshots"],
        "permission_classes": ["filesystem.read"],
        "resource_lane": "host.io.light",
        "share_policy": "workspace_grants",
        "runtime_assets": ["scripts/host_runtime_entry.py"],
    }
    manifest = {
        "code": "demo",
        "version": "1.2.3",
        "host_requirements": {
            "schema_version": "mindscape.pack-host-requirements.v1",
            "requirements": [requirement],
        },
    }
    content = {
        "schema_version": "mindscape.capability-host-assets.v1",
        "capability_code": "demo",
        "capability_version": "1.2.3",
        "requirements": [requirement],
        "assets": [
            {
                "path": "scripts/host_runtime_entry.py",
                "sha256": sha256(asset.read_bytes()).hexdigest(),
                "size_bytes": len(asset.read_bytes()),
                "mode": "0644",
            }
        ],
    }
    inventory = {
        **content,
        "tree_sha256": sha256(_canonical(content)).hexdigest(),
    }
    (cap_dir / "host_assets.json").write_bytes(_canonical(inventory) + b"\n")
    return cap_dir, manifest, inventory


def _prepared(tmp_path: Path) -> PreparedCapabilityTree:
    return PreparedCapabilityTree(
        install_id="install-a",
        capability_code="demo",
        staging_root=tmp_path / "cap-staging",
        staging_cap_dir=tmp_path / "cap-staging" / "demo",
        target_cap_dir=tmp_path / "capabilities" / "demo",
        previous_root=tmp_path / "previous",
        previous_cap_dir=tmp_path / "previous" / "demo",
    )


def test_host_assets_prepare_publish_and_readback_are_content_addressed(
    tmp_path: Path,
    monkeypatch,
):
    host_root = tmp_path / "host-runtimes"
    monkeypatch.setenv("MINDSCAPE_CAPABILITY_HOST_RUNTIMES_DIR", str(host_root))
    cap_dir, manifest, inventory = _fixture(tmp_path)
    installer = RuntimeAssetsInstaller(
        local_core_root=tmp_path / "local-core",
        capabilities_dir=tmp_path / "capabilities",
    )
    prepared = _prepared(tmp_path)
    result = InstallResult(capability_code="demo")

    installer.prepare_host_assets(
        cap_dir=cap_dir,
        manifest=manifest,
        prepared=prepared,
        result=result,
    )
    installer.publish_host_assets(prepared)

    expected = (
        host_root
        / "demo"
        / f"1.2.3-{inventory['tree_sha256']}"
    )
    assert prepared.host_runtime_target_dir == expected
    assert prepared.host_runtime_published is True
    assert (expected / "scripts" / "host_runtime_entry.py").read_bytes() == (
        cap_dir / "scripts" / "host_runtime_entry.py"
    ).read_bytes()
    assert result.installed["host_runtime_assets"] == [
        inventory["tree_sha256"]
    ]


def test_host_asset_digest_mismatch_fails_before_publish_and_cleans_staging(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.setenv(
        "MINDSCAPE_CAPABILITY_HOST_RUNTIMES_DIR",
        str(tmp_path / "host-runtimes"),
    )
    cap_dir, manifest, _ = _fixture(tmp_path)
    inventory = json.loads((cap_dir / "host_assets.json").read_text())
    inventory["assets"][0]["sha256"] = "0" * 64
    content = {k: v for k, v in inventory.items() if k != "tree_sha256"}
    inventory["tree_sha256"] = sha256(_canonical(content)).hexdigest()
    (cap_dir / "host_assets.json").write_bytes(_canonical(inventory) + b"\n")
    installer = RuntimeAssetsInstaller(
        local_core_root=tmp_path / "local-core",
        capabilities_dir=tmp_path / "capabilities",
    )
    prepared = _prepared(tmp_path)

    with pytest.raises(ValueError, match="asset_digest_mismatch"):
        installer.prepare_host_assets(
            cap_dir=cap_dir,
            manifest=manifest,
            prepared=prepared,
            result=InstallResult(capability_code="demo"),
        )

    assert not (tmp_path / "host-runtimes" / ".staging").exists()


def test_manifest_requirement_without_inventory_fails_closed(tmp_path: Path):
    cap_dir = tmp_path / "incoming" / "demo"
    cap_dir.mkdir(parents=True)
    installer = RuntimeAssetsInstaller(
        local_core_root=tmp_path / "local-core",
        capabilities_dir=tmp_path / "capabilities",
    )

    with pytest.raises(ValueError, match="inventory_missing"):
        installer.prepare_host_assets(
            cap_dir=cap_dir,
            manifest={"host_requirements": {"requirements": []}},
            prepared=_prepared(tmp_path),
            result=InstallResult(capability_code="demo"),
        )


def test_inventory_requirement_drift_fails_before_staging(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.setenv(
        "MINDSCAPE_CAPABILITY_HOST_RUNTIMES_DIR",
        str(tmp_path / "host-runtimes"),
    )
    cap_dir, manifest, _ = _fixture(tmp_path)
    inventory = json.loads((cap_dir / "host_assets.json").read_text())
    inventory["requirements"][0]["operations"] = ["mobile-upload-funnel"]
    content = {key: value for key, value in inventory.items() if key != "tree_sha256"}
    inventory["tree_sha256"] = sha256(_canonical(content)).hexdigest()
    (cap_dir / "host_assets.json").write_bytes(_canonical(inventory) + b"\n")
    installer = RuntimeAssetsInstaller(
        local_core_root=tmp_path / "local-core",
        capabilities_dir=tmp_path / "capabilities",
    )

    with pytest.raises(ValueError, match="requirements_mismatch"):
        installer.prepare_host_assets(
            cap_dir=cap_dir,
            manifest=manifest,
            prepared=_prepared(tmp_path),
            result=InstallResult(capability_code="demo"),
        )


def test_configured_host_runtime_root_symlink_fails_closed(
    tmp_path: Path,
    monkeypatch,
):
    target = tmp_path / "actual-host-root"
    target.mkdir()
    redirected = tmp_path / "host-runtimes"
    redirected.symlink_to(target, target_is_directory=True)
    monkeypatch.setenv(
        "MINDSCAPE_CAPABILITY_HOST_RUNTIMES_DIR",
        str(redirected),
    )
    cap_dir, manifest, _ = _fixture(tmp_path)
    installer = RuntimeAssetsInstaller(
        local_core_root=tmp_path / "local-core",
        capabilities_dir=tmp_path / "capabilities",
    )

    with pytest.raises(ValueError, match="root_redirected"):
        installer.prepare_host_assets(
            cap_dir=cap_dir,
            manifest=manifest,
            prepared=_prepared(tmp_path),
            result=InstallResult(capability_code="demo"),
        )
