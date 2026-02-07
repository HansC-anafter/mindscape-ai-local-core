"""
Model Manifest Schema and Validator.

Provides Pydantic models for validating model-manifest.yaml files
used by ModelWeightsInstaller.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, validator
from enum import Enum


class ModelProviderEnum(str, Enum):
    """Supported model providers."""

    HUGGINGFACE = "huggingface"
    OSS = "oss"
    DIRECT_URL = "direct_url"
    LOCAL_BUNDLE = "local_bundle"


class DownloadStrategyEnum(str, Enum):
    """Model download strategy."""

    LAZY = "lazy"
    EAGER = "eager"
    MANUAL = "manual"


class ModelRoleEnum(str, Enum):
    """Roles for models in the pipeline (aligns with ComfyUI assets)."""

    SEGMENTATION = "segmentation"
    POSE_DETECTOR = "pose_detector"
    OBJECT_DETECTOR = "object_detector"
    DIFFUSION_CHECKPOINT = "diffusion_checkpoint"
    TEXT_ENCODER = "text_encoder"
    VAE = "vae"
    CLIP_VISION = "clip_vision"
    LORA = "lora"
    CONTROLNET = "controlnet"
    UPSCALE = "upscale"
    FRAME_INTERPOLATION = "frame_interpolation"
    MATTING = "matting"
    INPAINTING = "inpainting"
    OTHER = "other"


class ModelFileSchema(BaseModel):
    """Schema for individual model file."""

    filename: str
    expected_hash: Optional[str] = None
    size_bytes: int = 0


class LicenseSchema(BaseModel):
    """Schema for license information."""

    spdx_id: str
    url: Optional[str] = None
    redistribution_allowed: bool = False
    commercial_use_allowed: bool = False


class HardwareRequirementsSchema(BaseModel):
    """Schema for hardware requirements."""

    min_vram_gb: float = 0
    recommended_vram_gb: float = 0
    supports_cpu_fallback: bool = True
    quantization_options: List[str] = Field(default_factory=lambda: ["fp32"])


class QualityProfileSchema(BaseModel):
    """Schema for quality profile."""

    quantization: str = "fp32"
    batch_size: int = 1
    additional_config: Dict[str, Any] = Field(default_factory=dict)


class DependenciesSchema(BaseModel):
    """Schema for model dependencies."""

    python_packages: List[str] = Field(default_factory=list)
    system_tools: List[str] = Field(default_factory=list)


class DataLocalitySchema(BaseModel):
    """Schema for data locality settings."""

    weights_local_only: bool = True
    inference_local_only: bool = True


class LocalBundleSchema(BaseModel):
    """Schema for local bundle configuration."""

    bundle_id: str
    relative_path: str


class ModelSchema(BaseModel):
    """Schema for individual model definition."""

    model_id: str
    display_name: Optional[str] = None
    role: ModelRoleEnum = ModelRoleEnum.OTHER
    provider: ModelProviderEnum = ModelProviderEnum.HUGGINGFACE
    repo_id: Optional[str] = None
    revision: str = "main"
    files: List[ModelFileSchema]
    download_urls: Optional[List[str]] = None
    local_bundle: Optional[LocalBundleSchema] = None
    license: LicenseSchema
    hardware_requirements: HardwareRequirementsSchema = Field(
        default_factory=HardwareRequirementsSchema
    )
    quality_profiles: Dict[str, QualityProfileSchema] = Field(default_factory=dict)
    dependencies: DependenciesSchema = Field(default_factory=DependenciesSchema)
    data_locality: DataLocalitySchema = Field(default_factory=DataLocalitySchema)

    @validator("repo_id")
    def validate_repo_id(cls, v, values):
        """Validate repo_id is present for huggingface provider."""
        if values.get("provider") == ModelProviderEnum.HUGGINGFACE and not v:
            raise ValueError("repo_id is required for huggingface provider")
        return v

    @validator("download_urls")
    def validate_download_urls(cls, v, values):
        """Validate download_urls is present for direct_url provider."""
        if values.get("provider") == ModelProviderEnum.DIRECT_URL and not v:
            raise ValueError("download_urls is required for direct_url provider")
        return v

    @validator("local_bundle")
    def validate_local_bundle(cls, v, values):
        """Validate local_bundle is present for local_bundle provider."""
        if values.get("provider") == ModelProviderEnum.LOCAL_BUNDLE and not v:
            raise ValueError("local_bundle is required for local_bundle provider")
        return v


class DownloadPolicySchema(BaseModel):
    """Schema for download policy."""

    strategy: DownloadStrategyEnum = DownloadStrategyEnum.LAZY
    eager_trigger: str = "preflight_profile_pull"
    source_allowlist: List[str] = Field(default_factory=list)
    verify_hash_on_load: bool = True
    cache_path_template: str = "~/.mindscape/models/{role}/{model_id}/"


class ProfileSchema(BaseModel):
    """Schema for model profile (bundle of models)."""

    profile_id: str
    display_name: str
    description: Optional[str] = None
    model_ids: List[str]


class ModelManifestSchema(BaseModel):
    """
    Complete schema for model-manifest.yaml.

    Example:
    ```yaml
    manifest_version: "1.0.0"
    pack_code: "layer_asset_forge"

    models:
      - model_id: sam2_hiera_large
        display_name: "SAM2 Hiera Large"
        provider: huggingface
        repo_id: "facebook/sam2-hiera-large"
        revision: "main"
        files:
          - filename: "sam2_hiera_large.pt"
            expected_hash: "sha256:abc123..."
            size_bytes: 2400000000
        license:
          spdx_id: "Apache-2.0"
          redistribution_allowed: true
        hardware_requirements:
          min_vram_gb: 4

    download_policy:
      strategy: lazy
      verify_hash_on_load: true

    profiles:
      - profile_id: laf_minimal
        display_name: "LAF Minimal"
        model_ids:
          - sam2_hiera_large
    ```
    """

    manifest_version: str = "1.0.0"
    pack_code: str
    models: List[ModelSchema] = Field(default_factory=list)
    download_policy: DownloadPolicySchema = Field(default_factory=DownloadPolicySchema)
    profiles: List[ProfileSchema] = Field(default_factory=list)

    @validator("profiles")
    def validate_profiles(cls, v, values):
        """Validate all model_ids in profiles exist in models."""
        model_ids = {m.model_id for m in values.get("models", [])}
        for profile in v:
            for model_id in profile.model_ids:
                if model_id not in model_ids:
                    raise ValueError(
                        f"Profile {profile.profile_id} references unknown model: {model_id}"
                    )
        return v


def validate_model_manifest(data: Dict[str, Any]) -> ModelManifestSchema:
    """
    Validate model manifest data against schema.

    Args:
        data: Parsed YAML/JSON data

    Returns:
        Validated ModelManifestSchema instance

    Raises:
        ValidationError: If validation fails
    """
    return ModelManifestSchema(**data)


def load_and_validate_manifest(file_path: str) -> ModelManifestSchema:
    """
    Load and validate a model-manifest.yaml file.

    Args:
        file_path: Path to the manifest file

    Returns:
        Validated ModelManifestSchema instance

    Raises:
        FileNotFoundError: If file doesn't exist
        ValidationError: If validation fails
    """
    import yaml
    from pathlib import Path

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Model manifest not found: {file_path}")

    with open(path) as f:
        data = yaml.safe_load(f)

    return validate_model_manifest(data)
