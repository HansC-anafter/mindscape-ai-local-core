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
from datetime import datetime

logger = logging.getLogger(__name__)


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
    role: str = "other"  # Role for path mapping (checkpoints, loras, etc.)
    files: List[ModelFile]
    license: LicenseInfo
    hardware_requirements: HardwareRequirements
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
                "updated_at": datetime.utcnow().isoformat(),
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
            model_info = self._parse_model_info(pack_code, model_data)
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

    def _parse_model_info(self, pack_code: str, data: Dict) -> ModelInfo:
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
        possible_paths = [
            Path(f"capabilities/{pack_code}/model-manifest.yaml"),
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

        total_size = sum(f.size_bytes for f in model_info.files)
        downloaded_size = 0

        for file_info in model_info.files:
            file_path = store_dir / file_info.filename

            # Get download URL
            url = self._get_download_url(model_info, file_info.filename)
            if not url:
                raise DownloadError(f"No download URL for {file_info.filename}")

            # Check allowlist
            if not self._is_url_allowed(url, pack_code=model_info.pack_code):
                raise SourceNotAllowedError(f"Download source not allowed: {url}")

            # Download file
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as response:
                        if response.status != 200:
                            raise DownloadError(
                                f"HTTP {response.status} downloading {url}"
                            )

                        with open(file_path, "wb") as f:
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

                file_info.local_path = file_path
                file_info.is_downloaded = True

            except Exception as e:
                model_info.status = ModelStatus.NOT_DOWNLOADED
                raise DownloadError(f"Failed to download {file_info.filename}: {e}")

        # 4. Create Symlink View
        if view_dir.exists():
            if view_dir.is_symlink():
                view_dir.unlink()
            elif view_dir.is_dir():
                import shutil

                shutil.rmtree(view_dir)

        # Use relative symlink for portability if possible, but absolute is safer for start
        os.symlink(store_dir, view_dir)

        model_info.local_path = view_dir
        model_info.status = ModelStatus.DOWNLOADED
        model_info.downloaded_at = datetime.utcnow()

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
            "provider": model_info.provider,
            "repo_id": model_info.repo_id,
            "revision": model_info.revision,
            "files": sorted([f.filename for f in model_info.files]),
            "hashes": sorted(
                [f.expected_hash for f in model_info.files if f.expected_hash]
            ),
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

            if file_info.expected_hash:
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
