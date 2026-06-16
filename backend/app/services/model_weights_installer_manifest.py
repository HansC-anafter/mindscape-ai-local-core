"""Manifest, state, and orchestration seam for model weights installer."""

import json
import logging
import shutil
from pathlib import Path
from typing import Callable, Dict, List, Optional

import yaml

from .model_weights_installer_types import (
    HashMismatchError,
    HardwareRequirements,
    LicenseError,
    LicenseInfo,
    ModelFile,
    ModelInfo,
    ModelNotFoundError,
    ModelProvider,
    ModelStatus,
    QualityProfile,
    _utc_now,
)

logger = logging.getLogger(f"{__package__}.model_weights_installer")


class ModelWeightsInstallerManifestMixin:
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
        self._manifests: Dict[str, Dict] = {}
        self._models: Dict[str, ModelInfo] = {}
        self._download_progress: Dict[str, float] = {}
        self._download_callbacks: Dict[str, List[Callable]] = {}

        self._load_state()
        self._scan_for_manifests()

    def _load_state(self) -> None:
        """Load persisted installer state."""
        state_file = self.cache_root / ".installer_state.json"
        if state_file.exists():
            try:
                with open(state_file) as f:
                    state = json.load(f)
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

    def _safe_path_exists(self, path: Path) -> bool:
        """Return path existence without treating broken symlinks as valid views."""
        return path.exists()

    def _safe_path_lstat(self, path: Path):
        """Return lstat when an artifact exists, including broken symlinks."""
        try:
            return path.lstat()
        except FileNotFoundError:
            return None

    def _clear_path_artifact(self, path: Path) -> None:
        """Remove a single path artifact at a known cache view location."""
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)

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

        for model_data in manifest.get("models", []):
            model_info = self._parse_model_info(
                pack_code, model_data, manifest_dir=manifest_path.parent
            )
            key = self._get_model_key(pack_code, model_info.model_id)
            self._models[key] = model_info

            role_subfolder = self.ROLE_MAP.get(model_info.role, model_info.role)
            view_path = (
                self.cache_root
                / role_subfolder
                / "by_pack"
                / pack_code
                / model_info.model_id
            )

            if self._safe_path_exists(view_path):
                model_info.local_path = view_path
                model_info.status = ModelStatus.DOWNLOADED
                if self._verify_model_files(model_info):
                    model_info.status = ModelStatus.VERIFIED
                else:
                    model_info.status = ModelStatus.CORRUPTED
            elif self._safe_path_lstat(view_path) is not None:
                self._clear_path_artifact(view_path)

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
        """Ensure model is available locally."""
        key = self._get_model_key(pack_code, model_id)

        if key not in self._models:
            manifest_path = self._find_manifest_path(pack_code)
            if manifest_path:
                self.load_manifest(pack_code, manifest_path)

        if key not in self._models:
            raise ModelNotFoundError(
                f"Model {model_id} not found in {pack_code} manifest"
            )

        model_info = self._models[key]
        self._check_license(model_info)

        if not force_download and model_info.status == ModelStatus.VERIFIED:
            return model_info

        if force_download or model_info.status in [
            ModelStatus.NOT_DOWNLOADED,
            ModelStatus.CORRUPTED,
        ]:
            await self._download_model(model_info, progress_callback)

        if not self._verify_model_files(model_info):
            model_info.status = ModelStatus.CORRUPTED
            self._save_state()
            raise HashMismatchError(f"Model {model_id} failed hash verification")

        model_info.status = ModelStatus.VERIFIED
        self._save_state()
        return model_info

    def _find_manifest_path(self, pack_code: str) -> Optional[Path]:
        """Find model-manifest.yaml for a pack."""
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
