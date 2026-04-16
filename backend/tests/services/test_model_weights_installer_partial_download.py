import os
from pathlib import Path

import pytest

from backend.app.services.model_weights_installer import (
    ComplianceInfo,
    DownloadError,
    HardwareRequirements,
    LicenseInfo,
    ModelFile,
    ModelInfo,
    ModelProvider,
    ModelStatus,
    ModelWeightsInstaller,
)


class _FakeContent:
    def __init__(self, chunks, fail_after=None):
        self._chunks = list(chunks)
        self._fail_after = fail_after

    async def iter_chunked(self, _size):
        for index, chunk in enumerate(self._chunks):
            if self._fail_after is not None and index >= self._fail_after:
                raise RuntimeError("stream interrupted")
            yield chunk


class _FakeResponse:
    def __init__(self, chunks, status=200, fail_after=None, headers=None):
        self.status = status
        self.content = _FakeContent(chunks, fail_after=fail_after)
        self.headers = headers or {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeSession:
    responses = []

    def __init__(self, headers=None, timeout=None):
        self.headers = headers or {}
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def get(self, url):
        assert url == "https://example.com/model.bin"
        assert self.responses
        response = self.responses.pop(0)
        if callable(response):
            return response(self.headers)
        return response


def _mock_safetensors_bytes(payload: bytes = b"\x00\x00") -> bytes:
    header = b"{}"
    return len(header).to_bytes(8, "little", signed=False) + header + payload


def _make_model_info() -> ModelInfo:
    return ModelInfo(
        model_id="test_model",
        pack_code="layer_asset_forge",
        display_name="Test Model",
        provider=ModelProvider.DIRECT_URL,
        role="inpainting",
        files=[
            ModelFile(
                filename="model.bin",
                expected_hash="",
                size_bytes=6,
            )
        ],
        license=LicenseInfo(spdx_id="Apache-2.0"),
        compliance=ComplianceInfo(),
        hardware_requirements=HardwareRequirements(),
        download_urls=["https://example.com/model.bin"],
        status=ModelStatus.NOT_DOWNLOADED,
    )


def _make_nested_model_info() -> ModelInfo:
    return ModelInfo(
        model_id="nested_model",
        pack_code="layer_asset_forge",
        display_name="Nested Model",
        provider=ModelProvider.DIRECT_URL,
        role="matting",
        files=[
            ModelFile(
                filename="models/model.bin",
                expected_hash="",
                size_bytes=6,
            )
        ],
        license=LicenseInfo(spdx_id="Apache-2.0"),
        compliance=ComplianceInfo(),
        hardware_requirements=HardwareRequirements(),
        download_urls=["https://example.com/model.bin"],
        status=ModelStatus.NOT_DOWNLOADED,
    )


def _make_local_bundle_file_model_info(capability_dir: Path) -> ModelInfo:
    return ModelInfo(
        model_id="hero_lora",
        pack_code="character_training",
        display_name="Hero LoRA",
        provider=ModelProvider.LOCAL_BUNDLE,
        role="lora",
        files=[
            ModelFile(
                filename="hero.safetensors",
                expected_hash="",
                size_bytes=11,
            )
        ],
        license=LicenseInfo(spdx_id="Apache-2.0"),
        compliance=ComplianceInfo(),
        hardware_requirements=HardwareRequirements(),
        local_bundle={
            "bundle_id": "character-pack-001",
            "relative_path": "hero.safetensors",
        },
        status=ModelStatus.NOT_DOWNLOADED,
        manifest_dir=capability_dir,
    )


def _make_local_bundle_directory_model_info(capability_dir: Path) -> ModelInfo:
    return ModelInfo(
        model_id="hero_bundle",
        pack_code="character_training",
        display_name="Hero Bundle",
        provider=ModelProvider.LOCAL_BUNDLE,
        role="lora",
        files=[
            ModelFile(
                filename="loras/hero.safetensors",
                expected_hash="",
                size_bytes=10,
            )
        ],
        license=LicenseInfo(spdx_id="Apache-2.0"),
        compliance=ComplianceInfo(),
        hardware_requirements=HardwareRequirements(),
        local_bundle={
            "bundle_id": "character-pack-001",
            "relative_path": "assets",
        },
        status=ModelStatus.NOT_DOWNLOADED,
        manifest_dir=capability_dir,
    )


@pytest.mark.asyncio
async def test_download_model_uses_partial_file_then_materializes(monkeypatch, tmp_path):
    installer = ModelWeightsInstaller(cache_root=str(tmp_path))
    model_info = _make_model_info()

    _FakeSession.responses = [_FakeResponse([b"abc", b"def"])]

    monkeypatch.setattr(
        "backend.app.services.model_weights_installer.aiohttp.ClientSession",
        _FakeSession,
    )
    monkeypatch.setattr(installer, "_is_url_allowed", lambda *args, **kwargs: True)

    await installer._download_model(model_info)

    assert model_info.status == ModelStatus.DOWNLOADED
    assert model_info.local_path is not None
    final_file = model_info.local_path / "model.bin"
    partial_file = model_info.local_path.resolve() / "model.bin.partial"

    assert final_file.read_bytes() == b"abcdef"
    assert not partial_file.exists()


@pytest.mark.asyncio
async def test_download_model_cleans_partial_file_on_failure(monkeypatch, tmp_path):
    installer = ModelWeightsInstaller(cache_root=str(tmp_path))
    model_info = _make_model_info()

    _FakeSession.responses = [
        _FakeResponse([b"abc", b"def"], fail_after=1)
        for _ in range(5)
    ]

    monkeypatch.setattr(
        "backend.app.services.model_weights_installer.aiohttp.ClientSession",
        _FakeSession,
    )
    monkeypatch.setattr(installer, "_is_url_allowed", lambda *args, **kwargs: True)

    with pytest.raises(DownloadError):
        await installer._download_model(model_info)

    store_dir = (
        Path(installer.cache_root)
        / "inpainting"
        / "store"
        / installer._get_model_fingerprint(model_info)
    )
    assert not (store_dir / "model.bin").exists()
    assert not (store_dir / "model.bin.partial").exists()
    assert model_info.local_path is None
    assert model_info.status == ModelStatus.NOT_DOWNLOADED


@pytest.mark.asyncio
async def test_download_model_retries_with_range_resume(monkeypatch, tmp_path):
    installer = ModelWeightsInstaller(cache_root=str(tmp_path))
    model_info = _make_model_info()

    def _resume_response(headers):
        assert headers.get("Range") == "bytes=3-"
        return _FakeResponse([b"def"], status=206)

    _FakeSession.responses = [
        _FakeResponse([b"abc", b"def"], fail_after=1),
        _resume_response,
    ]

    monkeypatch.setattr(
        "backend.app.services.model_weights_installer.aiohttp.ClientSession",
        _FakeSession,
    )
    monkeypatch.setattr(installer, "_is_url_allowed", lambda *args, **kwargs: True)

    await installer._download_model(model_info)

    final_file = model_info.local_path / "model.bin"
    assert final_file.read_bytes() == b"abcdef"


@pytest.mark.asyncio
async def test_download_model_treats_http_416_at_eof_as_complete(monkeypatch, tmp_path):
    installer = ModelWeightsInstaller(cache_root=str(tmp_path))
    model_info = _make_model_info()
    store_dir = (
        Path(installer.cache_root)
        / "inpainting"
        / "store"
        / installer._get_model_fingerprint(model_info)
    )
    store_dir.mkdir(parents=True, exist_ok=True)
    partial_file = store_dir / "model.bin.partial"
    partial_file.write_bytes(b"abcdef")

    def _eof_response(headers):
        assert headers.get("Range") == "bytes=6-"
        return _FakeResponse(
            [],
            status=416,
            headers={"Content-Range": "bytes */6"},
        )

    _FakeSession.responses = [_eof_response]

    monkeypatch.setattr(
        "backend.app.services.model_weights_installer.aiohttp.ClientSession",
        _FakeSession,
    )
    monkeypatch.setattr(installer, "_is_url_allowed", lambda *args, **kwargs: True)

    await installer._download_model(model_info)

    final_file = model_info.local_path / "model.bin"
    assert final_file.read_bytes() == b"abcdef"


@pytest.mark.asyncio
async def test_download_model_recovers_legacy_incomplete_final_file(monkeypatch, tmp_path):
    installer = ModelWeightsInstaller(cache_root=str(tmp_path))
    model_info = _make_model_info()
    store_dir = (
        Path(installer.cache_root)
        / "inpainting"
        / "store"
        / installer._get_model_fingerprint(model_info)
    )
    store_dir.mkdir(parents=True, exist_ok=True)
    legacy_final_file = store_dir / "model.bin"
    legacy_final_file.write_bytes(b"abc")

    def _resume_response(headers):
        assert headers.get("Range") == "bytes=3-"
        return _FakeResponse([b"def"], status=206)

    _FakeSession.responses = [_resume_response]

    monkeypatch.setattr(
        "backend.app.services.model_weights_installer.aiohttp.ClientSession",
        _FakeSession,
    )
    monkeypatch.setattr(installer, "_is_url_allowed", lambda *args, **kwargs: True)

    await installer._download_model(model_info)

    final_file = model_info.local_path / "model.bin"
    assert final_file.read_bytes() == b"abcdef"


@pytest.mark.asyncio
async def test_download_model_supports_nested_filename_paths(monkeypatch, tmp_path):
    installer = ModelWeightsInstaller(cache_root=str(tmp_path))
    model_info = _make_nested_model_info()

    _FakeSession.responses = [_FakeResponse([b"abc", b"def"])]

    monkeypatch.setattr(
        "backend.app.services.model_weights_installer.aiohttp.ClientSession",
        _FakeSession,
    )
    monkeypatch.setattr(installer, "_is_url_allowed", lambda *args, **kwargs: True)

    await installer._download_model(model_info)

    final_file = model_info.local_path / "models" / "model.bin"
    assert final_file.read_bytes() == b"abcdef"


@pytest.mark.asyncio
async def test_ensure_model_materializes_local_bundle_file(tmp_path):
    capability_dir = tmp_path / "capabilities" / "character_training"
    bundle_dir = capability_dir / "bundles" / "character-pack-001"
    source_file = bundle_dir / "hero.safetensors"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_bytes(_mock_safetensors_bytes())

    installer = ModelWeightsInstaller(cache_root=str(tmp_path / "model-cache"))
    model_info = _make_local_bundle_file_model_info(capability_dir)
    model_key = installer._get_model_key(model_info.pack_code, model_info.model_id)
    installer._models[model_key] = model_info

    resolved = await installer.ensure_model(model_info.pack_code, model_info.model_id)

    store_dir = (
        Path(installer.cache_root)
        / "loras"
        / "store"
        / installer._get_model_fingerprint(model_info)
    )
    final_file = resolved.local_path / "hero.safetensors"
    assert resolved.status == ModelStatus.VERIFIED
    assert resolved.local_path.is_symlink()
    assert not os.readlink(resolved.local_path).startswith("/")
    assert resolved.local_path.resolve() == store_dir.resolve()
    assert final_file.exists()
    assert not final_file.is_symlink()
    assert final_file.read_bytes() == _mock_safetensors_bytes()


@pytest.mark.asyncio
async def test_ensure_model_materializes_local_bundle_directory(tmp_path):
    capability_dir = tmp_path / "capabilities" / "character_training"
    source_file = (
        capability_dir
        / "bundles"
        / "character-pack-001"
        / "assets"
        / "loras"
        / "hero.safetensors"
    )
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_bytes(_mock_safetensors_bytes(b"\x01\x02"))

    installer = ModelWeightsInstaller(cache_root=str(tmp_path / "model-cache"))
    model_info = _make_local_bundle_directory_model_info(capability_dir)
    model_key = installer._get_model_key(model_info.pack_code, model_info.model_id)
    installer._models[model_key] = model_info

    resolved = await installer.ensure_model(model_info.pack_code, model_info.model_id)

    store_dir = (
        Path(installer.cache_root)
        / "loras"
        / "store"
        / installer._get_model_fingerprint(model_info)
    )
    final_file = resolved.local_path / "loras" / "hero.safetensors"
    assert resolved.status == ModelStatus.VERIFIED
    assert resolved.local_path.is_symlink()
    assert not os.readlink(resolved.local_path).startswith("/")
    assert resolved.local_path.resolve() == store_dir.resolve()
    assert final_file.exists()
    assert not final_file.is_symlink()
    assert final_file.read_bytes() == _mock_safetensors_bytes(b"\x01\x02")


@pytest.mark.asyncio
async def test_ensure_model_rejects_invalid_local_bundle_safetensors(tmp_path):
    capability_dir = tmp_path / "capabilities" / "character_training"
    bundle_dir = capability_dir / "bundles" / "character-pack-001"
    source_file = bundle_dir / "hero.safetensors"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_text("soft-gaze-runtime-smoke", encoding="utf-8")

    installer = ModelWeightsInstaller(cache_root=str(tmp_path / "model-cache"))
    model_info = _make_local_bundle_file_model_info(capability_dir)
    model_key = installer._get_model_key(model_info.pack_code, model_info.model_id)
    installer._models[model_key] = model_info

    with pytest.raises(Exception):
        await installer.ensure_model(model_info.pack_code, model_info.model_id)

    assert model_info.status == ModelStatus.CORRUPTED


@pytest.mark.asyncio
async def test_ensure_model_reverifies_already_verified_invalid_safetensors(tmp_path):
    cache_root = tmp_path / "model-cache"
    installer = ModelWeightsInstaller(cache_root=str(cache_root))

    view_dir = cache_root / "loras" / "by_pack" / "character_training" / "verified_demo"
    store_dir = cache_root / "loras" / "store" / "verified-demo-fingerprint"
    store_dir.mkdir(parents=True, exist_ok=True)
    bad_file = store_dir / "hero.safetensors"
    bad_file.write_text("soft-gaze-runtime-smoke", encoding="utf-8")
    bundle_source = tmp_path / "bundles" / "demo" / "hero.safetensors"
    bundle_source.parent.mkdir(parents=True, exist_ok=True)
    bundle_source.write_text("soft-gaze-runtime-smoke", encoding="utf-8")
    view_dir.parent.mkdir(parents=True, exist_ok=True)
    view_dir.symlink_to(os.path.relpath(store_dir, start=view_dir.parent))

    model_info = ModelInfo(
        model_id="verified_demo",
        pack_code="character_training",
        display_name="Verified Demo",
        provider=ModelProvider.LOCAL_BUNDLE,
        role="lora",
        files=[
            ModelFile(
                filename="hero.safetensors",
                expected_hash="placeholder",
                size_bytes=bad_file.stat().st_size,
                local_path=bad_file,
                is_downloaded=True,
                is_verified=True,
            )
        ],
        license=LicenseInfo(
            spdx_id="MIT",
            redistribution_allowed=True,
            commercial_use_allowed=True,
        ),
        compliance=ComplianceInfo(),
        hardware_requirements=HardwareRequirements(),
        local_bundle={"bundle_id": "demo", "relative_path": "hero.safetensors"},
        manifest_dir=tmp_path,
        local_path=view_dir,
        status=ModelStatus.VERIFIED,
    )
    model_key = installer._get_model_key(model_info.pack_code, model_info.model_id)
    installer._models[model_key] = model_info

    with pytest.raises(Exception):
        await installer.ensure_model(model_info.pack_code, model_info.model_id)

    assert model_info.status == ModelStatus.CORRUPTED


def test_get_model_info_discovers_runtime_install_manifest_from_local_storage(
    monkeypatch, tmp_path
):
    storage_root = tmp_path / "vr_storage"
    manifest_path = (
        storage_root
        / "default"
        / "character_training"
        / "runtime_installs"
        / "ctp_demo"
        / "sdxl"
        / "hybrid"
        / "model-manifest.yaml"
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        "\n".join(
            [
                "manifest_version: 1.0.0",
                "pack_code: character_training",
                "models:",
                '  - model_id: "ctp_demo_sdxl_lora_hero_v1"',
                '    display_name: "Hero LoRA"',
                '    role: "lora"',
                '    provider: "local_bundle"',
                "    files:",
                '      - filename: "hero.safetensors"',
                '        expected_hash: "placeholder"',
                "        size_bytes: 12",
                "    local_bundle:",
                '      bundle_id: "ctp_demo"',
                '      relative_path: "hero.safetensors"',
                "profiles:",
                '  - profile_id: "package_ctp_demo"',
                '    model_ids: ["ctp_demo_sdxl_lora_hero_v1"]',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("LOCAL_STORAGE_PATH", str(storage_root))
    installer = ModelWeightsInstaller(cache_root=str(tmp_path / "model-cache"))

    model_info = installer.get_model_info(
        "character_training",
        "ctp_demo_sdxl_lora_hero_v1",
    )

    assert model_info is not None
    assert model_info.model_id == "ctp_demo_sdxl_lora_hero_v1"
    assert model_info.manifest_dir == manifest_path.parent
