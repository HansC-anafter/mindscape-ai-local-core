"""Shared model weights installer types and constants."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


DOWNLOAD_RETRY_ATTEMPTS = 5
DOWNLOAD_RETRY_BASE_DELAY_SECONDS = 2
DOWNLOAD_CONNECT_TIMEOUT_SECONDS = 30
DOWNLOAD_READ_TIMEOUT_SECONDS = 300


class DownloadStrategy(str, Enum):
    """Model download strategy."""

    LAZY = "lazy"
    EAGER = "eager"
    MANUAL = "manual"


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
    role: str = "other"
    quality_profiles: Dict[str, QualityProfile] = field(default_factory=dict)
    repo_id: Optional[str] = None
    revision: Optional[str] = None
    download_urls: Optional[List[str]] = None
    local_bundle: Optional[Dict[str, Any]] = None
    dependencies: Dict[str, Any] = field(default_factory=dict)
    data_locality: Dict[str, bool] = field(default_factory=dict)
    family: str = "other"
    format: str = "pytorch"
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
