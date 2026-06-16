from pathlib import Path

import yaml

from backend.app.services import model_weights_installer as public_module
from backend.app.services.model_weights_installer import (
    HardwareRequirements,
    LicenseInfo,
    ModelFile,
    ModelInfo,
    ModelProvider,
    ModelStatus,
    ModelWeightsInstaller,
)


def test_model_weights_installer_facade_exposes_planned_seams(tmp_path):
    installer = ModelWeightsInstaller(cache_root=str(tmp_path / "cache"))

    for method_name in [
        "load_manifest",
        "ensure_model",
        "_download_model",
        "_publish_model_view",
        "_materialize_local_bundle",
        "_get_model_fingerprint",
        "_verify_model_files",
        "get_disk_usage",
    ]:
        assert callable(getattr(installer, method_name))

    assert public_module.aiohttp.ClientSession is not None
    assert public_module.asyncio.sleep is not None


def test_load_manifest_clears_stale_by_pack_view_path(monkeypatch, tmp_path):
    manifest_path = tmp_path / "model-manifest.yaml"
    manifest_path.write_text(
        yaml.safe_dump({"models": [{"model_id": "hero_lora"}]}),
        encoding="utf-8",
    )
    installer = ModelWeightsInstaller(cache_root=str(tmp_path / "cache"))
    model_info = ModelInfo(
        model_id="hero_lora",
        pack_code="character_training",
        display_name="Hero LoRA",
        provider=ModelProvider.LOCAL_BUNDLE,
        files=[
            ModelFile(
                filename="hero.safetensors",
                expected_hash="placeholder",
                size_bytes=1,
            )
        ],
        license=LicenseInfo(
            spdx_id="MIT",
            redistribution_allowed=True,
            commercial_use_allowed=True,
        ),
        hardware_requirements=HardwareRequirements(),
        role="lora",
        local_bundle={
            "bundle_id": "character-pack-001",
            "relative_path": "hero.safetensors",
        },
        manifest_dir=manifest_path.parent,
        status=ModelStatus.NOT_DOWNLOADED,
    )
    cleaned_paths = []
    stale_view_path = (
        installer.cache_root
        / "loras"
        / "by_pack"
        / "character_training"
        / model_info.model_id
    )

    monkeypatch.setattr(
        installer,
        "_parse_model_info",
        lambda pack_code, data, manifest_dir=None: model_info,
    )
    monkeypatch.setattr(
        installer,
        "_safe_path_exists",
        lambda path: False if path == stale_view_path else path.exists(),
    )
    monkeypatch.setattr(
        installer,
        "_safe_path_lstat",
        lambda path: object() if path == stale_view_path else None,
    )
    monkeypatch.setattr(
        installer,
        "_clear_path_artifact",
        lambda path: cleaned_paths.append(path),
    )

    installer.load_manifest("character_training", manifest_path)

    assert cleaned_paths == [stale_view_path]
    assert installer.get_model_info("character_training", model_info.model_id) is model_info
    assert model_info.local_path is None
    assert model_info.status == ModelStatus.NOT_DOWNLOADED
