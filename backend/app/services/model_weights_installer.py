"""
Model Weights Installer - Core service for managing ML model weights.

Responsibilities:
- Download model weights from approved sources
- Verify hash integrity
- Manage version locking
- Check license compliance
- Provide model paths to pack's model_provider
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Callable
from pathlib import Path
from enum import Enum
import hashlib
import json
import yaml
import logging
import asyncio
import aiohttp
import os
import re
import shutil
from datetime import datetime, timezone
from contextlib import suppress


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)

logger = logging.getLogger(__name__)

DOWNLOAD_RETRY_ATTEMPTS = 5
DOWNLOAD_RETRY_BASE_DELAY_SECONDS = 2
DOWNLOAD_CONNECT_TIMEOUT_SECONDS = 30
DOWNLOAD_READ_TIMEOUT_SECONDS = 300


class DownloadStrategy(str, Enum):
    """Model download strategy."""

    LAZY = "lazy"  # Download on first use
    EAGER = "eager"  # Pre-download with pack install
    MANUAL = "manual"  # Manual download (offline environment)


class ModelProvider(str, Enum):
    """Supported model providers."""

    HUGGINGFACE = "huggingface"
    OSS = "oss"
    DIRECT_URL = "direct_url"
    LOCAL_BUNDLE = "local_bundle"


class ModelStatus(str, Enum):
    """Model availability status."""

    NOT_DOWNLOADED = "not_downloaded"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    VERIFIED = "verified"
    CORRUPTED = "corrupted"
    LICENSE_BLOCKED = "license_blocked"


@dataclass
class ModelFile:
    """Individual file within a model."""

    filename: str
    expected_hash: str
    size_bytes: int
    local_path: Optional[Path] = None
    is_downloaded: bool = False
    is_verified: bool = False


@dataclass
class LicenseInfo:
    """Model license information."""

    spdx_id: str
    url: Optional[str] = None
    redistribution_allowed: bool = False
    commercial_use_allowed: bool = False


@dataclass
class HardwareRequirements:
    """Hardware requirements for running a model."""

    min_vram_gb: float = 0
    recommended_vram_gb: float = 0
    supports_cpu_fallback: bool = True
    quantization_options: List[str] = field(default_factory=lambda: ["fp32"])


@dataclass
class QualityProfile:
    """Quality profile configuration."""

    quantization: str = "fp32"
    batch_size: int = 1
    additional_config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelInfo:
    """Complete model metadata from model-manifest.yaml."""

    model_id: str
    pack_code: str
    display_name: str
    provider: ModelProvider
    files: List[ModelFile]
    license: LicenseInfo
    hardware_requirements: HardwareRequirements
    role: str = "other"  # Role for path mapping (checkpoints, loras, etc.)
    quality_profiles: Dict[str, QualityProfile] = field(default_factory=dict)
    repo_id: Optional[str] = None
    revision: Optional[str] = None
    download_urls: Optional[List[str]] = None
    local_bundle: Optional[Dict[str, Any]] = None
    dependencies: Dict[str, Any] = field(default_factory=dict)
    data_locality: Dict[str, bool] = field(default_factory=dict)
    family: str = "other"  # llm | diffusion | controlnet | etc.
    format: str = "pytorch"  # pytorch | safetensors | gguf
    local_path: Optional[Path] = None
    status: ModelStatus = ModelStatus.NOT_DOWNLOADED
    downloaded_at: Optional[datetime] = None
    manifest_dir: Optional[Path] = None


class ModelNotFoundError(Exception):
    """Raised when model_id is not in manifest."""

    pass


class DownloadError(Exception):
    """Raised when download fails."""

    pass


class HashMismatchError(Exception):
    """Raised when verification fails."""

    pass


class LicenseError(Exception):
    """Raised when license check fails."""

    pass


class SourceNotAllowedError(Exception):
    """Raised when download source is not in allowlist."""

    pass


class ModelWeightsInstaller:
    """
    Core service for model weights management.

    Provides unified interface for downloading, verifying, and managing
    ML model weights across all capability packs.
    """

    CORE_ALLOWLIST = [
        "huggingface.co",
        "cdn-lfs.huggingface.co",
        "cdn-lfs-us-1.huggingface.co",
        "storage.googleapis.com",
    ]

    ROLE_MAP = {
        "diffusion_checkpoint": "checkpoints",
        "lora": "loras",
        "vae": "vae",
        "controlnet": "controlnet",
        "clip_vision": "clip_vision",
        "segmentation": "segmentation",
        "matting": "matting",
        "pose_detector": "pose_detector",
        "upscale": "upscale",
        "inpainting": "inpainting",
        "llm": "llms",
    }

    def __init__(
        self, cache_root: str = "~/.mindscape/models", config_path: Optional[str] = None
    ):
        """
        Initialize ModelWeightsInstaller.

        Args:
            cache_root: Root directory for model cache
            config_path: Optional path to global config file
        """
        self.cache_root = Path(cache_root).expanduser()
        self.cache_root.mkdir(parents=True, exist_ok=True)

        self.config_path = config_path
        self._manifests: Dict[str, Dict] = {}  # pack_code -> manifest
        self._models: Dict[str, ModelInfo] = {}  # f"{pack}:{model_id}" -> ModelInfo
        self._download_progress: Dict[str, float] = {}  # model_key -> progress (0-1)
        self._download_callbacks: Dict[str, List[Callable]] = {}

        # Load any persisted state
        self._load_state()

        # Proactively scan for manifests of core packs
        self._scan_for_manifests()

    def _load_state(self) -> None:
        """Load persisted installer state."""
        state_file = self.cache_root / ".installer_state.json"
        if state_file.exists():
            try:
                with open(state_file) as f:
                    state = json.load(f)
                    # Restore download status for known models
                    for key, info in state.get("models", {}).items():
                        if key in self._models:
                            self._models[key].status = ModelStatus(
                                info.get("status", "not_downloaded")
                            )
            except Exception as e:
                logger.warning(f"Failed to load installer state: {e}")

    def _save_state(self) -> None:
        """Persist installer state."""
        state_file = self.cache_root / ".installer_state.json"
        try:
            state = {
                "models": {
                    key: {"status": info.status.value}
                    for key, info in self._models.items()
                },
                "updated_at": _utc_now().isoformat(),
            }
            with open(state_file, "w") as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save installer state: {e}")

    def _resolve_allowlist(
        self, pack_allowlist: Optional[List[str]] = None
    ) -> List[str]:
        """
        Resolve effective allowlist.

        Rule: Use intersection with core allowlist unless admin override is enabled.
        """
        if not pack_allowlist:
            return self.CORE_ALLOWLIST.copy()
        return [host for host in pack_allowlist if host in self.CORE_ALLOWLIST]

    def _get_model_key(self, pack_code: str, model_id: str) -> str:
        """Get unique key for a model."""
        return f"{pack_code}:{model_id}"

    def load_manifest(self, pack_code: str, manifest_path: Path) -> None:
        """
        Load and parse a pack's model-manifest.yaml.

        Args:
            pack_code: The capability pack code
            manifest_path: Path to model-manifest.yaml
        """
        if not manifest_path.exists():
            logger.debug(f"No model manifest for pack {pack_code}")
            return

        with open(manifest_path) as f:
            manifest = yaml.safe_load(f)

        self._manifests[pack_code] = manifest

        # Parse models
        for model_data in manifest.get("models", []):
            model_info = self._parse_model_info(
                pack_code, model_data, manifest_dir=manifest_path.parent
            )
            key = self._get_model_key(pack_code, model_info.model_id)
            self._models[key] = model_info

            # Check if already downloaded (using CAS + Symlink structure)
            role_subfolder = self.ROLE_MAP.get(model_info.role, model_info.role)
            view_path = (
                self.cache_root
                / role_subfolder
                / "by_pack"
                / pack_code
                / model_info.model_id
            )

            if view_path.exists():
                model_info.local_path = view_path
                model_info.status = ModelStatus.DOWNLOADED
                # Verify on load
                if self._verify_model_files(model_info):
                    model_info.status = ModelStatus.VERIFIED
                else:
                    model_info.status = ModelStatus.CORRUPTED

    def _parse_model_info(
        self, pack_code: str, data: Dict, manifest_dir: Optional[Path] = None
    ) -> ModelInfo:
        """Parse model info from manifest data."""
        files = [
            ModelFile(
                filename=f["filename"],
                expected_hash=f.get("expected_hash", ""),
                size_bytes=f.get("size_bytes", 0),
            )
            for f in data.get("files", [])
        ]

        license_data = data.get("license", {})
        license_info = LicenseInfo(
            spdx_id=license_data.get("spdx_id", "UNKNOWN"),
            url=license_data.get("url"),
            redistribution_allowed=license_data.get("redistribution_allowed", False),
            commercial_use_allowed=license_data.get("commercial_use_allowed", False),
        )

        hw_data = data.get("hardware_requirements", {})
        hardware = HardwareRequirements(
            min_vram_gb=hw_data.get("min_vram_gb", 0),
            recommended_vram_gb=hw_data.get("recommended_vram_gb", 0),
            supports_cpu_fallback=hw_data.get("supports_cpu_fallback", True),
            quantization_options=hw_data.get("quantization_options", ["fp32"]),
        )

        quality_profiles = {}
        for profile_name, profile_data in data.get("quality_profiles", {}).items():
            quality_profiles[profile_name] = QualityProfile(
                quantization=profile_data.get("quantization", "fp32"),
                batch_size=profile_data.get("batch_size", 1),
                additional_config=profile_data.get("additional_config", {}),
            )

        return ModelInfo(
            model_id=data["model_id"],
            pack_code=pack_code,
            display_name=data.get("display_name", data["model_id"]),
            provider=ModelProvider(data.get("provider", "huggingface")),
            role=data.get("role", "other"),
            files=files,
            license=license_info,
            hardware_requirements=hardware,
            quality_profiles=quality_profiles,
            repo_id=data.get("repo_id"),
            revision=data.get("revision", "main"),
            download_urls=data.get("download_urls"),
            local_bundle=data.get("local_bundle"),
            dependencies=data.get("dependencies", {}),
            data_locality=data.get("data_locality", {}),
            family=data.get("family", "other"),
            format=data.get("format", "pytorch"),
            manifest_dir=manifest_dir,
        )

    async def ensure_model(
        self,
        pack_code: str,
        model_id: str,
        force_download: bool = False,
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> ModelInfo:
        """
        Ensure model is available locally.

        Args:
            pack_code: The capability pack code
            model_id: Model identifier from model-manifest.yaml
            force_download: Force re-download even if exists
            progress_callback: Optional callback for download progress

        Returns:
            ModelInfo with local_path populated

        Raises:
            ModelNotFoundError: If model_id not in manifest
            DownloadError: If download fails
            HashMismatchError: If verification fails
            LicenseError: If license check fails
        """
        key = self._get_model_key(pack_code, model_id)

        if key not in self._models:
            # Try to load manifest
            manifest_path = self._find_manifest_path(pack_code)
            if manifest_path:
                self.load_manifest(pack_code, manifest_path)

        if key not in self._models:
            raise ModelNotFoundError(
                f"Model {model_id} not found in {pack_code} manifest"
            )

        model_info = self._models[key]

        # Check license compliance
        self._check_license(model_info)

        # Check if already downloaded and verified
        if not force_download and model_info.status == ModelStatus.VERIFIED:
            return model_info

        # Download if needed
        if force_download or model_info.status in [
            ModelStatus.NOT_DOWNLOADED,
            ModelStatus.CORRUPTED,
        ]:
            await self._download_model(model_info, progress_callback)

        # Verify
        if not self._verify_model_files(model_info):
            model_info.status = ModelStatus.CORRUPTED
            self._save_state()
            raise HashMismatchError(f"Model {model_id} failed hash verification")

        model_info.status = ModelStatus.VERIFIED
        self._save_state()
        return model_info

    def _find_manifest_path(self, pack_code: str) -> Optional[Path]:
        """Find model-manifest.yaml for a pack."""
        # Try common locations
        app_root = Path(__file__).resolve().parent.parent
        possible_paths = [
            Path(f"capabilities/{pack_code}/model-manifest.yaml"),
            app_root / "capabilities" / pack_code / "model-manifest.yaml",
            app_root.parent.parent / "capabilities" / pack_code / "model-manifest.yaml",
            Path(
                f"~/.mindscape/capabilities/{pack_code}/model-manifest.yaml"
            ).expanduser(),
        ]
        for path in possible_paths:
            if path.exists():
                return path
        return None

    def _check_license(self, model_info: ModelInfo) -> None:
        """Check license compliance."""
        blocked_licenses = ["non-commercial", "research-only"]
        if model_info.license.spdx_id.lower() in blocked_licenses:
            if not model_info.license.commercial_use_allowed:
                raise LicenseError(
                    f"Model {model_info.model_id} has restricted license: {model_info.license.spdx_id}"
                )

    @staticmethod
    def _parse_content_range_total(content_range: Optional[str]) -> Optional[int]:
        """Extract total size from a Content-Range header like 'bytes */205803670'."""
        if not content_range:
            return None
        match = re.match(r"bytes\s+\*/(\d+)$", content_range.strip())
        if not match:
            return None
        try:
            return int(match.group(1))
        except ValueError:
            return None

    async def _download_model(
        self,
        model_info: ModelInfo,
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> None:
        """Download model files with role-aware path mapping."""
        model_info.status = ModelStatus.DOWNLOADING
        key = self._get_model_key(model_info.pack_code, model_info.model_id)

        role_subfolder = self.ROLE_MAP.get(model_info.role, model_info.role)

        # 1. Generate fingerprint for de-duplication
        fingerprint = self._get_model_fingerprint(model_info)

        # 2. Store Path: cache_root / {role} / store / {fingerprint}
        store_dir = self.cache_root / role_subfolder / "store" / fingerprint
        store_dir.mkdir(parents=True, exist_ok=True)

        # 3. View Path: cache_root / {role} / by_pack / {pack} / {id}
        view_dir = (
            self.cache_root
            / role_subfolder
            / "by_pack"
            / model_info.pack_code
            / model_info.model_id
        )
        view_dir.parent.mkdir(parents=True, exist_ok=True)

        if model_info.provider == ModelProvider.LOCAL_BUNDLE:
            self._materialize_local_bundle(model_info, store_dir, view_dir)
            if progress_callback:
                progress_callback(1.0)
            self._download_progress[key] = 1.0
            return

        total_size = sum(f.size_bytes for f in model_info.files)
        downloaded_size = 0

        for file_info in model_info.files:
            file_path = store_dir / file_info.filename
            file_path.parent.mkdir(parents=True, exist_ok=True)
            partial_path = file_path.parent / f"{file_path.name}.partial"

            # Get download URL
            url = self._get_download_url(model_info, file_info.filename)
            if not url:
                raise DownloadError(f"No download URL for {file_info.filename}")

            # Check allowlist
            if not self._is_url_allowed(url, pack_code=model_info.pack_code):
                raise SourceNotAllowedError(f"Download source not allowed: {url}")

            request_headers: Optional[Dict[str, str]] = None
            if model_info.provider == ModelProvider.HUGGINGFACE:
                try:
                    from backend.app.services.huggingface_auth_resolver import (
                        resolve_huggingface_auth,
                    )

                    hf_auth = resolve_huggingface_auth()
                    headers = hf_auth.authorization_headers()
                    if headers:
                        request_headers = headers
                except Exception as exc:
                    logger.debug(
                        "Failed to resolve Hugging Face auth for %s: %s",
                        model_info.model_id,
                        exc,
                    )

            timeout = aiohttp.ClientTimeout(
                total=None,
                sock_connect=DOWNLOAD_CONNECT_TIMEOUT_SECONDS,
                sock_read=DOWNLOAD_READ_TIMEOUT_SECONDS,
            )
            last_error: Optional[BaseException] = None
            expected_size = int(file_info.size_bytes or 0)
            base_headers = dict(request_headers or {})

            # Recover from older downloader behavior that wrote partial data to the
            # final filename directly. Convert it back into a resumable partial file.
            if (
                not partial_path.exists()
                and file_path.exists()
                and expected_size > 0
                and file_path.stat().st_size < expected_size
            ):
                os.replace(file_path, partial_path)

            for attempt in range(1, DOWNLOAD_RETRY_ATTEMPTS + 1):
                try:
                    existing_size = partial_path.stat().st_size if partial_path.exists() else 0
                    headers = dict(base_headers)
                    write_mode = "ab" if existing_size > 0 else "wb"
                    remote_size_hint: Optional[int] = None

                    if existing_size > 0:
                        headers["Range"] = f"bytes={existing_size}-"
                        downloaded_size = existing_size
                    else:
                        downloaded_size = 0

                    async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
                        async with session.get(url) as response:
                            if existing_size > 0 and response.status == 200:
                                # Origin ignored Range; restart from zero to avoid corrupt append.
                                with suppress(FileNotFoundError):
                                    partial_path.unlink()
                                existing_size = 0
                                downloaded_size = 0
                                raise DownloadError(
                                    "Origin ignored HTTP Range resume request; restarting download"
                                )

                            if response.status == 416 and existing_size > 0:
                                remote_size_hint = self._parse_content_range_total(
                                    response.headers.get("Content-Range")
                                )
                                if remote_size_hint is not None and remote_size_hint == existing_size:
                                    # The remote origin is telling us the requested range starts
                                    # exactly at EOF. Treat the existing partial as complete.
                                    final_size = existing_size
                                else:
                                    raise DownloadError(
                                        f"HTTP 416 downloading {url}"
                                    )
                            elif response.status not in {200, 206}:
                                raise DownloadError(
                                    f"HTTP {response.status} downloading {url}"
                                )

                            if response.status != 416:
                                with open(partial_path, write_mode) as f:
                                    async for chunk in response.content.iter_chunked(8192):
                                        f.write(chunk)
                                        downloaded_size += len(chunk)
                                        if progress_callback:
                                            progress = (
                                                downloaded_size / total_size
                                                if total_size > 0
                                                else 0
                                            )
                                            progress_callback(progress)
                                            self._download_progress[key] = progress

                    final_size = partial_path.stat().st_size if partial_path.exists() else 0
                    effective_expected_size = remote_size_hint or expected_size
                    if effective_expected_size > 0 and final_size < effective_expected_size:
                        raise DownloadError(
                            f"Incomplete download for {file_info.filename}: "
                            f"{final_size}/{effective_expected_size} bytes"
                        )

                    if file_path.exists():
                        file_path.unlink()
                    os.replace(partial_path, file_path)
                    file_info.local_path = file_path
                    file_info.is_downloaded = True
                    break

                except Exception as e:
                    last_error = e
                    logger.warning(
                        "Download attempt %s/%s failed for %s (%s): %r",
                        attempt,
                        DOWNLOAD_RETRY_ATTEMPTS,
                        file_info.filename,
                        type(e).__name__,
                        e,
                    )
                    if attempt >= DOWNLOAD_RETRY_ATTEMPTS:
                        with suppress(FileNotFoundError):
                            partial_path.unlink()
                        model_info.status = ModelStatus.NOT_DOWNLOADED
                        detail = f"{type(e).__name__}: {e!r}"
                        raise DownloadError(
                            f"Failed to download {file_info.filename}: {detail}"
                        ) from e
                    await asyncio.sleep(DOWNLOAD_RETRY_BASE_DELAY_SECONDS * attempt)
                    continue

            if last_error is not None and not file_info.is_downloaded:
                model_info.status = ModelStatus.NOT_DOWNLOADED
                detail = f"{type(last_error).__name__}: {last_error!r}"
                raise DownloadError(
                    f"Failed to download {file_info.filename}: {detail}"
                ) from last_error

        self._publish_model_view(model_info, store_dir, view_dir)

    def _publish_model_view(
        self, model_info: ModelInfo, store_dir: Path, view_dir: Path
    ) -> None:
        """Expose the store directory through the pack-scoped view path."""
        if view_dir.exists() or view_dir.is_symlink():
            if view_dir.is_symlink() or view_dir.is_file():
                view_dir.unlink()
            else:
                shutil.rmtree(view_dir)

        os.symlink(store_dir, view_dir)
        model_info.local_path = view_dir
        model_info.status = ModelStatus.DOWNLOADED
        model_info.downloaded_at = _utc_now()

    def _materialize_local_bundle(
        self, model_info: ModelInfo, store_dir: Path, view_dir: Path
    ) -> None:
        """Materialize a model from pack-local bundle files without network download."""
        bundle_source = self._resolve_local_bundle_source(model_info)
        if bundle_source is None:
            raise DownloadError(
                f"Local bundle source not found for {model_info.pack_code}:{model_info.model_id}"
            )

        if store_dir.exists() or store_dir.is_symlink():
            if store_dir.is_symlink() or store_dir.is_file():
                store_dir.unlink()
            else:
                shutil.rmtree(store_dir)
        store_dir.mkdir(parents=True, exist_ok=True)

        if bundle_source.is_file():
            if len(model_info.files) != 1:
                raise DownloadError(
                    "local_bundle file source requires exactly one declared model file"
                )
            file_info = model_info.files[0]
            target_path = store_dir / file_info.filename
            target_path.parent.mkdir(parents=True, exist_ok=True)
            self._link_or_copy_local_bundle_file(bundle_source, target_path)
            file_info.local_path = target_path
            file_info.is_downloaded = True
        elif bundle_source.is_dir():
            for file_info in model_info.files:
                source_file = bundle_source / file_info.filename
                if not source_file.exists() or not source_file.is_file():
                    raise DownloadError(
                        f"Local bundle missing file {file_info.filename} for "
                        f"{model_info.pack_code}:{model_info.model_id}"
                    )
                target_path = store_dir / file_info.filename
                target_path.parent.mkdir(parents=True, exist_ok=True)
                self._link_or_copy_local_bundle_file(source_file, target_path)
                file_info.local_path = target_path
                file_info.is_downloaded = True
        else:
            raise DownloadError(
                f"Local bundle source is neither file nor directory: {bundle_source}"
            )

        self._publish_model_view(model_info, store_dir, view_dir)

    def _resolve_local_bundle_source(self, model_info: ModelInfo) -> Optional[Path]:
        """Resolve the source path for a local bundle-backed model."""
        local_bundle = model_info.local_bundle or {}
        bundle_id = str(local_bundle.get("bundle_id") or "").strip()
        relative_path_raw = str(local_bundle.get("relative_path") or "").strip()
        if not bundle_id or not relative_path_raw:
            return None

        bundle_id_path = Path(bundle_id)
        if (
            bundle_id_path.is_absolute()
            or bundle_id_path.name != bundle_id
            or any(part in {"..", "."} for part in bundle_id_path.parts)
        ):
            raise DownloadError(f"Invalid local bundle id: {bundle_id}")

        relative_path = Path(relative_path_raw)
        if relative_path.is_absolute() or any(
            part in {"..", "."} for part in relative_path.parts
        ):
            raise DownloadError(
                f"Invalid local bundle relative path: {relative_path_raw}"
            )

        app_root = Path(__file__).resolve().parent.parent
        candidate_roots = []
        if model_info.manifest_dir is not None:
            candidate_roots.append(model_info.manifest_dir)
        candidate_roots.extend(
            [
                Path(f"capabilities/{model_info.pack_code}"),
                app_root / "capabilities" / model_info.pack_code,
                app_root.parent.parent / "capabilities" / model_info.pack_code,
                Path(f"~/.mindscape/capabilities/{model_info.pack_code}").expanduser(),
            ]
        )

        seen_roots = set()
        for root in candidate_roots:
            root_key = str(root.expanduser())
            if root_key in seen_roots:
                continue
            seen_roots.add(root_key)
            candidate = root / "bundles" / bundle_id / relative_path
            if candidate.exists():
                return candidate

        return None

    def _link_or_copy_local_bundle_file(
        self, source_path: Path, target_path: Path
    ) -> None:
        """Populate the cache store from a local bundle file."""
        if target_path.exists() or target_path.is_symlink():
            if target_path.is_symlink() or target_path.is_file():
                target_path.unlink()
            else:
                shutil.rmtree(target_path)

        try:
            os.symlink(source_path.resolve(), target_path)
        except OSError:
            shutil.copy2(source_path, target_path)

    def _get_download_url(self, model_info: ModelInfo, filename: str) -> Optional[str]:
        """Get download URL for a file."""
        if model_info.provider == ModelProvider.HUGGINGFACE:
            repo_id = model_info.repo_id
            revision = model_info.revision or "main"
            return f"https://huggingface.co/{repo_id}/resolve/{revision}/{filename}"

        elif model_info.provider == ModelProvider.DIRECT_URL:
            if model_info.download_urls:
                for url in model_info.download_urls:
                    if url.endswith(filename):
                        return url
                return model_info.download_urls[0]  # Fallback to first URL

        elif model_info.provider == ModelProvider.OSS:
            logger.warning(
                f"OSS provider download not yet implemented for {model_info.model_id}"
            )
            return None

        elif model_info.provider == ModelProvider.LOCAL_BUNDLE:
            logger.info(
                f"Model {model_info.model_id} is a local bundle, no download needed."
            )
            return None

        return None

    def _is_url_allowed(self, url: str, pack_code: Optional[str] = None) -> bool:
        """Check if URL host is in allowlist."""
        from urllib.parse import urlparse

        parsed = urlparse(url)

        # Get effective allowlist for this pack
        pack_manifest = self._manifests.get(pack_code, {})
        pack_allowlist = pack_manifest.get("download_policy", {}).get(
            "source_allowlist", []
        )
        effective_allowlist = self._resolve_allowlist(pack_allowlist)

        return parsed.netloc in effective_allowlist

    def _get_model_fingerprint(self, model_info: ModelInfo) -> str:
        """Generate a unique fingerprint for model de-duplication."""
        fingerprint_data = {
            "provider": model_info.provider.value,
            "repo_id": model_info.repo_id,
            "revision": model_info.revision,
            "files": sorted([f.filename for f in model_info.files]),
            "hashes": sorted(
                [f.expected_hash for f in model_info.files if f.expected_hash]
            ),
            "local_bundle": model_info.local_bundle or {},
        }
        data_str = json.dumps(fingerprint_data, sort_keys=True)
        return hashlib.sha256(data_str.encode()).hexdigest()[:16]

    def _verify_model_files(self, model_info: ModelInfo) -> bool:
        """Verify all model files against expected hashes."""
        if not model_info.local_path:
            return False

        for file_info in model_info.files:
            file_path = model_info.local_path / file_info.filename
            if not file_path.exists():
                return False

            if file_info.expected_hash and not self._is_placeholder_hash(
                file_info.expected_hash
            ):
                # Parse hash format: "sha256:abc123..."
                if ":" in file_info.expected_hash:
                    algo, expected = file_info.expected_hash.split(":", 1)
                else:
                    algo, expected = "sha256", file_info.expected_hash

                actual = self._compute_hash(file_path, algo)
                if actual != expected:
                    logger.warning(
                        f"Hash mismatch for {file_path}: expected {expected}, got {actual}"
                    )
                    file_info.is_verified = False
                    return False

            file_info.is_verified = True

        return True

    def _is_placeholder_hash(self, expected_hash: str) -> bool:
        normalized = str(expected_hash or "").strip().lower()
        if not normalized:
            return True
        if ":" in normalized:
            _, normalized = normalized.split(":", 1)
        return normalized.startswith("placeholder_hash_") or normalized in {
            "placeholder",
            "tbd",
            "todo",
        }

    def _compute_hash(self, file_path: Path, algorithm: str = "sha256") -> str:
        """Compute file hash."""
        hash_func = hashlib.new(algorithm)
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hash_func.update(chunk)
        return hash_func.hexdigest()

    def get_model_path(self, pack_code: str, model_id: str) -> Optional[Path]:
        """Get local path for a model (None if not downloaded)."""
        key = self._get_model_key(pack_code, model_id)
        model_info = self._models.get(key)
        if model_info and model_info.status in [
            ModelStatus.DOWNLOADED,
            ModelStatus.VERIFIED,
        ]:
            return model_info.local_path
        return None

    def list_models(self, pack_code: Optional[str] = None) -> List[ModelInfo]:
        """List all models defined in manifests."""
        if pack_code:
            return [
                info
                for key, info in self._models.items()
                if info.pack_code == pack_code
            ]
        return list(self._models.values())

    def get_model_info(self, pack_code: str, model_id: str) -> Optional[ModelInfo]:
        """Get model info by pack and model_id."""
        key = self._get_model_key(pack_code, model_id)
        return self._models.get(key)

    def verify_model(self, pack_code: str, model_id: str) -> bool:
        """Verify model integrity against expected hash."""
        key = self._get_model_key(pack_code, model_id)
        model_info = self._models.get(key)
        if not model_info:
            return False
        return self._verify_model_files(model_info)

    async def delete_model(self, pack_code: str, model_id: str) -> bool:
        """Delete a downloaded model to free space."""
        key = self._get_model_key(pack_code, model_id)
        model_info = self._models.get(key)
        if not model_info or not model_info.local_path:
            return False

        import shutil

        try:
            shutil.rmtree(model_info.local_path)
            model_info.local_path = None
            model_info.status = ModelStatus.NOT_DOWNLOADED
            for file_info in model_info.files:
                file_info.local_path = None
                file_info.is_downloaded = False
                file_info.is_verified = False
            self._save_state()
            return True
        except Exception as e:
            logger.error(f"Failed to delete model {model_id}: {e}")
            return False

    def get_disk_usage(self, pack_code: Optional[str] = None) -> Dict[str, int]:
        """
        Get disk usage for models (total or per-pack).
        For per-pack usage, we traverse the 'by_pack' view to count logical consumption.
        """
        usage = {}

        def get_path_size(path: Path) -> int:
            total = 0
            if path.exists():
                if path.is_symlink():
                    # Follow symlink to get actual size of the target
                    target = path.resolve()
                    if target.exists():
                        for entry in target.rglob("*"):
                            if entry.is_file():
                                total += entry.stat().st_size
                elif path.is_dir():
                    for entry in path.rglob("*"):
                        if entry.is_file():
                            total += entry.stat().st_size
            return total

        if pack_code:
            pack_total = 0
            # Traverse by_pack for this specific pack across all roles
            for role_dir in self.cache_root.iterdir():
                if role_dir.is_dir() and role_dir.name in self.ROLE_MAP.values():
                    pack_view = role_dir / "by_pack" / pack_code
                    if pack_view.exists():
                        for model_entry in pack_view.iterdir():
                            pack_total += get_path_size(model_entry)
            usage[pack_code] = pack_total
        else:
            # Global usage (physical store usage)
            global_total = 0
            for role_dir in self.cache_root.iterdir():
                if role_dir.is_dir() and role_dir.name in self.ROLE_MAP.values():
                    store_dir = role_dir / "store"
                    if store_dir.exists():
                        for entry in store_dir.rglob("*"):
                            if entry.is_file():
                                global_total += entry.stat().st_size
            usage["total"] = global_total

        return usage

    def _scan_for_manifests(self) -> None:
        """Proactively scan for known pack manifests."""
        core_packs = ["layer_asset_forge", "video_renderer"]
        for pack in core_packs:
            path = self._find_manifest_path(pack)
            if path:
                self.load_manifest(pack, path)

    def get_download_progress(self, pack_code: str, model_id: str) -> float:
        """Get current download progress (0-1)."""
        key = self._get_model_key(pack_code, model_id)
        return self._download_progress.get(key, 0.0)


# Singleton instance
_MODEL_WEIGHTS_INSTALLER: Optional[ModelWeightsInstaller] = None


def get_model_weights_installer(
    cache_root: str = "~/.mindscape/models",
) -> ModelWeightsInstaller:
    """Get or create singleton ModelWeightsInstaller instance."""
    global _MODEL_WEIGHTS_INSTALLER
    if _MODEL_WEIGHTS_INSTALLER is None:
        _MODEL_WEIGHTS_INSTALLER = ModelWeightsInstaller(cache_root=cache_root)
    return _MODEL_WEIGHTS_INSTALLER


def reset_model_weights_installer() -> None:
    """Reset singleton instance (for testing)."""
    global _MODEL_WEIGHTS_INSTALLER
    _MODEL_WEIGHTS_INSTALLER = None
