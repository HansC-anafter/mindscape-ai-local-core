"""
Data Locality Service - Enforces data_locality constraints across packs.

This service ensures that local_only assets are never uploaded to cloud storage
or exposed through cloud-accessible URLs.
"""

from typing import Any, Dict, List, Optional, Set
from enum import Enum
import os
import logging

logger = logging.getLogger(__name__)


class DataLocalityCategory(str, Enum):
    """Standard data locality categories."""

    # Local-only categories (never upload to cloud)
    VIDEO_RAW_FILES = "video_raw_files"
    AUDIO_RAW_FILES = "audio_raw_files"
    IMAGE_RAW_FILES = "image_raw_files"
    USER_MEDIA_FILES = "user_media_files"
    USER_PERSONAL_DATA = "user_personal_data"
    SCHEDULE_LEDGER = "schedule_ledger"
    USER_CREDENTIALS = "user_credentials"
    MODEL_WEIGHTS = "model_weights"

    # Cloud-allowed categories
    MANIFEST_JSON = "manifest_json"
    METADATA = "metadata"
    THUMBNAILS = "thumbnails"
    RENDER_METADATA = "render_metadata"
    JOB_RUN_METADATA = "job_run_metadata"
    ELEMENT_ASSETS = "element_assets"


# Default local-only categories that should never be uploaded
DEFAULT_LOCAL_ONLY: Set[str] = {
    DataLocalityCategory.VIDEO_RAW_FILES.value,
    DataLocalityCategory.AUDIO_RAW_FILES.value,
    DataLocalityCategory.IMAGE_RAW_FILES.value,
    DataLocalityCategory.USER_MEDIA_FILES.value,
    DataLocalityCategory.USER_PERSONAL_DATA.value,
    DataLocalityCategory.SCHEDULE_LEDGER.value,
    DataLocalityCategory.USER_CREDENTIALS.value,
    DataLocalityCategory.MODEL_WEIGHTS.value,
}


class DataLocalityViolation(Exception):
    """Raised when a data locality constraint is violated."""

    def __init__(self, message: str, category: str, asset_ref: Dict[str, Any] = None):
        super().__init__(message)
        self.category = category
        self.asset_ref = asset_ref


class DataLocalityService:
    """
    Service for enforcing data locality constraints.

    Provides methods to:
    - Validate if an asset can be uploaded to cloud
    - Check if an operation respects data_locality constraints
    - Block cloud operations on local_only assets
    """

    def __init__(self, custom_local_only: Optional[Set[str]] = None):
        """
        Initialize DataLocalityService.

        Args:
            custom_local_only: Additional categories to treat as local-only
        """
        self.local_only_categories = DEFAULT_LOCAL_ONLY.copy()
        if custom_local_only:
            self.local_only_categories.update(custom_local_only)

    def is_local_only(self, category: str) -> bool:
        """Check if a category is local-only."""
        return category.lower() in self.local_only_categories

    def can_upload_to_cloud(
        self,
        asset_ref: Dict[str, Any],
        data_locality_spec: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Check if an asset can be uploaded to cloud storage.

        Args:
            asset_ref: Asset reference containing metadata
            data_locality_spec: Optional data_locality specification

        Returns:
            Result with allowed status and reason
        """
        # Check explicit data_locality in asset_ref
        if isinstance(asset_ref.get("data_locality"), dict):
            local_only = asset_ref["data_locality"].get("local_only", [])
            if local_only:
                # Asset has local_only tags
                for category in local_only:
                    if self.is_local_only(category):
                        return {
                            "allowed": False,
                            "reason": f"Asset marked as local_only: {category}",
                            "category": category,
                        }

        # Check external data_locality spec
        if data_locality_spec:
            local_only = data_locality_spec.get("local_only", [])
            asset_type = asset_ref.get("artifact_type", "")
            if asset_type in local_only:
                return {
                    "allowed": False,
                    "reason": f"Asset type is local_only: {asset_type}",
                    "category": asset_type,
                }

        # Check if asset path suggests sensitive content
        file_path = asset_ref.get("file_path") or asset_ref.get("storage_key", "")
        if self._path_suggests_local_only(file_path):
            return {
                "allowed": False,
                "reason": f"File path suggests local-only content: {file_path}",
                "category": "path_inference",
            }

        return {"allowed": True, "reason": "No local_only restrictions found"}

    def _path_suggests_local_only(self, path: str) -> bool:
        """Check if file path suggests local-only content."""
        if not path:
            return False

        path_lower = path.lower()

        # Paths that suggest raw/sensitive content
        sensitive_patterns = [
            "/raw/",
            "/originals/",
            "/private/",
            "/credentials/",
            "/secrets/",
            "/user_data/",
            "/personal/",
        ]

        return any(pattern in path_lower for pattern in sensitive_patterns)

    def enforce_for_cloud_upload(
        self,
        asset_ref: Dict[str, Any],
        operation: str = "upload",
        data_locality_spec: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Enforce data locality for cloud upload operation.

        Raises DataLocalityViolation if the operation would violate constraints.

        Args:
            asset_ref: Asset reference
            operation: Operation type (upload, sync, share)
            data_locality_spec: Optional data_locality specification
        """
        check = self.can_upload_to_cloud(asset_ref, data_locality_spec)

        if not check["allowed"]:
            raise DataLocalityViolation(
                f"Cannot {operation} asset to cloud: {check['reason']}",
                category=check.get("category", "unknown"),
                asset_ref=asset_ref,
            )

    def validate_manifest_locality(
        self, manifest: Dict[str, Any], target_environment: str = "cloud"
    ) -> Dict[str, Any]:
        """
        Validate all assets in a manifest for data locality constraints.

        Args:
            manifest: Scene edit manifest or composition manifest
            target_environment: Target environment (local, cloud)

        Returns:
            Validation result with any violations
        """
        violations: List[Dict[str, Any]] = []
        warnings: List[Dict[str, Any]] = []

        if target_environment != "cloud":
            return {
                "valid": True,
                "violations": [],
                "warnings": [],
                "message": "Local execution - no cloud restrictions apply",
            }

        # Check manifest-level data_locality
        manifest_locality = manifest.get("data_locality", {})

        # Check timeline clips
        timeline = manifest.get("timeline", {})
        clips = timeline.get("clips", [])

        for i, clip in enumerate(clips):
            if not isinstance(clip, dict):
                continue

            source = clip.get("source", {})
            if not isinstance(source, dict):
                continue

            # Build asset ref from clip
            asset_ref = {
                "artifact_type": clip.get("track_type", "unknown"),
                "file_path": source.get("file_path"),
                "storage_key": source.get("storage_key"),
                "url": source.get("url"),
                "data_locality": clip.get("meta", {}).get("data_locality", {}),
            }

            check = self.can_upload_to_cloud(asset_ref, manifest_locality)

            if not check["allowed"]:
                violations.append(
                    {
                        "clip_index": i,
                        "clip_id": clip.get("item_id"),
                        "category": check.get("category"),
                        "reason": check["reason"],
                        "source": source,
                    }
                )

        # Check layers if present
        layers = manifest.get("layers", [])
        for i, layer in enumerate(layers):
            if not isinstance(layer, dict):
                continue

            paths = layer.get("paths", {})
            for path_type, path_value in paths.items():
                if self._path_suggests_local_only(path_value):
                    violations.append(
                        {
                            "layer_index": i,
                            "layer_id": layer.get("layer_id"),
                            "path_type": path_type,
                            "reason": f"Layer path suggests local-only content: {path_value}",
                        }
                    )

        is_valid = len(violations) == 0

        return {
            "valid": is_valid,
            "violations": violations,
            "warnings": warnings,
            "message": (
                "All assets can be processed in cloud"
                if is_valid
                else f"{len(violations)} data locality violations found"
            ),
        }


# Singleton instance
_DATA_LOCALITY_SERVICE: Optional[DataLocalityService] = None


def get_data_locality_service() -> DataLocalityService:
    """Get or create singleton DataLocalityService instance."""
    global _DATA_LOCALITY_SERVICE
    if _DATA_LOCALITY_SERVICE is None:
        _DATA_LOCALITY_SERVICE = DataLocalityService()
    return _DATA_LOCALITY_SERVICE


def enforce_local_only(asset_ref: Dict[str, Any], operation: str = "upload") -> None:
    """
    Convenience function to enforce data locality.

    Raises DataLocalityViolation if the asset is local-only.
    """
    service = get_data_locality_service()
    service.enforce_for_cloud_upload(asset_ref, operation)


def is_cloud_allowed(asset_ref: Dict[str, Any]) -> bool:
    """
    Convenience function to check if asset can be uploaded to cloud.

    Returns True if allowed, False if local-only.
    """
    service = get_data_locality_service()
    result = service.can_upload_to_cloud(asset_ref)
    return result["allowed"]
