"""
Model Weights Installer - public facade for managing ML model weights.

This module remains the compatibility import surface for callers and tests.
Implementation is split into focused mixins to keep resource-sensitive model
download, cache, and pack activation seams independently reviewable.
"""

import asyncio
import logging
from typing import Optional

import aiohttp

from .model_weights_installer_catalog import ModelWeightsInstallerCatalogMixin
from .model_weights_installer_downloads import ModelWeightsInstallerDownloadMixin
from .model_weights_installer_local_bundle import ModelWeightsInstallerLocalBundleMixin
from .model_weights_installer_manifest import ModelWeightsInstallerManifestMixin
from .model_weights_installer_types import (
    DOWNLOAD_CONNECT_TIMEOUT_SECONDS,
    DOWNLOAD_READ_TIMEOUT_SECONDS,
    DOWNLOAD_RETRY_ATTEMPTS,
    DOWNLOAD_RETRY_BASE_DELAY_SECONDS,
    DownloadError,
    DownloadStrategy,
    HardwareRequirements,
    HashMismatchError,
    LicenseError,
    LicenseInfo,
    ModelFile,
    ModelInfo,
    ModelNotFoundError,
    ModelProvider,
    ModelStatus,
    QualityProfile,
    SourceNotAllowedError,
    _utc_now,
)

logger = logging.getLogger(__name__)


class ModelWeightsInstaller(
    ModelWeightsInstallerManifestMixin,
    ModelWeightsInstallerDownloadMixin,
    ModelWeightsInstallerLocalBundleMixin,
    ModelWeightsInstallerCatalogMixin,
):
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
