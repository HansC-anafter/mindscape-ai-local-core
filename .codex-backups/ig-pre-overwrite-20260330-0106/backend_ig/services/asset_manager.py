"""
Asset Manager for IG Post

Manages post assets (images, videos) with naming validation, size checking,
and format validation.
"""
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
import re
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("PIL (Pillow) not available, image size checking will be limited")

from capabilities.ig.services.workspace_storage import WorkspaceStorage

logger = logging.getLogger(__name__)


class AssetManager:
    """
    Manages IG Post assets

    Supports:
    - Asset naming rule validation
    - Asset list generation
    - Size/ratio checking
    - Cover generation spec checking
    """

    # Asset size specifications
    ASSET_SPECS = {
        "post": {
            "width": 1080,
            "height": 1080,
            "ratio": "1:1",
            "max_size_mb": 8
        },
        "carousel": {
            "width": 1080,
            "height": 1080,
            "ratio": "1:1",
            "max_size_mb": 8
        },
        "reel": {
            "width": 1080,
            "height": 1920,
            "ratio": "9:16",
            "max_size_mb": 100
        },
        "story": {
            "width": 1080,
            "height": 1920,
            "ratio": "9:16",
            "max_size_mb": 100
        }
    }

    def __init__(
        self,
        workspace_storage: WorkspaceStorage,
        post_folder: Optional[str] = None
    ):
        """
        Initialize Asset Manager

        Args:
            workspace_storage: WorkspaceStorage instance for accessing storage
            post_folder: Optional post folder path (relative to posts directory)
        """
        self.storage = workspace_storage
        self.post_folder = post_folder

    def scan_assets(self, post_folder: Optional[str] = None) -> Dict[str, Any]:
        """
        Scan assets in post folder

        Args:
            post_folder: Post folder path (relative to posts directory, optional if set in __init__)

        Returns:
            {
                "asset_list": List[Dict],
                "post_slug": str
            }
        """
        post_folder = post_folder or self.post_folder
        if not post_folder:
            return {
                "asset_list": [],
                "post_slug": None,
                "error": "post_folder is required"
            }

        # Parse post folder to extract date and slug
        folder_name = Path(post_folder).name
        match = re.match(r'(\d{4}-\d{2}-\d{2})_(.+)', folder_name)
        if match:
            date = match.group(1)
            post_slug = match.group(2)
            post_path = self.storage.get_post_path(post_slug, date)
        else:
            # Assume folder_name is the post_slug
            post_slug = folder_name
            post_path = self.storage.get_post_path(post_slug)

        assets_folder = post_path / "assets"

        asset_list = []

        if not post_path.exists():
            return {
                "asset_list": [],
                "post_slug": post_slug,
                "error": f"Post folder does not exist: {post_folder}"
            }

        if assets_folder.exists() and assets_folder.is_dir():
            for asset_file in assets_folder.iterdir():
                if asset_file.is_file():
                    asset_info = self._analyze_asset(asset_file, post_slug, post_path)
                    if asset_info:
                        asset_list.append(asset_info)

        return {
            "asset_list": asset_list,
            "post_slug": post_slug,
            "assets_folder": str(assets_folder.relative_to(self.storage.get_capability_root())) if assets_folder.exists() else None
        }

    def _analyze_asset(self, asset_path: Path, post_slug: Optional[str], post_path: Path) -> Optional[Dict[str, Any]]:
        """
        Analyze asset file

        Args:
            asset_path: Path to asset file
            post_slug: Post slug for validation

        Returns:
            Asset information dictionary
        """
        try:
            file_size = asset_path.stat().st_size
            file_size_mb = file_size / (1024 * 1024)

            asset_info = {
                "path": str(asset_path.relative_to(self.storage.get_capability_root())),
                "name": asset_path.name,
                "size_bytes": file_size,
                "size_mb": round(file_size_mb, 2),
                "extension": asset_path.suffix.lower()
            }

            # Check if image
            if asset_path.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp"]:
                asset_info["is_image"] = True
                if PIL_AVAILABLE:
                    try:
                        with Image.open(asset_path) as img:
                            asset_info["width"] = img.width
                            asset_info["height"] = img.height
                            asset_info["ratio"] = f"{img.width}:{img.height}"
                    except Exception as e:
                        logger.warning(f"Failed to read image: {e}")
                        asset_info["width"] = None
                        asset_info["height"] = None
                        asset_info["ratio"] = None
                else:
                    asset_info["width"] = None
                    asset_info["height"] = None
                    asset_info["ratio"] = None
            else:
                asset_info["is_image"] = False

            # Validate naming
            naming_validation = self._validate_naming(asset_path.name, post_slug)
            asset_info["naming_valid"] = naming_validation["is_valid"]
            asset_info["naming_errors"] = naming_validation["errors"]

            return asset_info

        except Exception as e:
            logger.error(f"Failed to analyze asset {asset_path}: {e}")
            return None

    def _validate_naming(self, filename: str, post_slug: Optional[str]) -> Dict[str, Any]:
        """
        Validate asset naming rule

        Format: {post_slug}__{number}_{type}.{ext}
        Example: brand-topic__01_cover.jpg

        Args:
            filename: Asset filename
            post_slug: Post slug for validation

        Returns:
            {
                "is_valid": bool,
                "errors": List[str]
            }
        """
        errors = []

        if not post_slug:
            return {
                "is_valid": False,
                "errors": ["Post slug not found, cannot validate naming"]
            }

        # Check format: {post_slug}__{number}_{type}.{ext}
        pattern = rf"^{re.escape(post_slug)}__(\d+)_(.+)\.(.+)$"
        match = re.match(pattern, filename)

        if not match:
            errors.append(f"Filename does not match pattern: {post_slug}__{{number}}_{{type}}.{{ext}}")
            return {
                "is_valid": False,
                "errors": errors
            }

        number = match.group(1)
        asset_type = match.group(2)
        extension = match.group(3)

        # Validate number (should be 01, 02, etc.)
        if not number.isdigit():
            errors.append("Number part must be digits")

        # Validate extension
        valid_extensions = [".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov"]
        if f".{extension.lower()}" not in valid_extensions:
            errors.append(f"Invalid extension: {extension}. Must be one of: {', '.join(valid_extensions)}")

        return {
            "is_valid": len(errors) == 0,
            "errors": errors
        }

    def validate_assets(
        self,
        asset_list: List[Dict[str, Any]],
        post_type: str
    ) -> Dict[str, Any]:
        """
        Validate assets against post type specifications

        Args:
            asset_list: List of asset information dictionaries
            post_type: Post type (post, carousel, reel, story)

        Returns:
            {
                "validation_results": Dict,
                "missing_assets": List[str],
                "size_warnings": List[str]
            }
        """
        spec = self.ASSET_SPECS.get(post_type, self.ASSET_SPECS["post"])

        validation_results = {
            "valid_assets": [],
            "invalid_assets": [],
            "warnings": []
        }

        missing_assets = []
        size_warnings = []

        for asset in asset_list:
            asset_errors = []
            asset_warnings = []

            # Check naming
            if not asset.get("naming_valid", False):
                asset_errors.extend(asset.get("naming_errors", []))

            # Check size (for images)
            if asset.get("is_image"):
                width = asset.get("width")
                height = asset.get("height")

                if width and height:
                    # Check dimensions
                    if width != spec["width"] or height != spec["height"]:
                        asset_warnings.append(
                            f"Size mismatch: {width}x{height} (expected {spec['width']}x{spec['height']})"
                        )
                        size_warnings.append(f"{asset['name']}: {width}x{height} (expected {spec['width']}x{spec['height']})")

                    # Check ratio
                    expected_ratio = spec["ratio"]
                    actual_ratio = asset.get("ratio", "")
                    if actual_ratio != expected_ratio:
                        asset_warnings.append(
                            f"Ratio mismatch: {actual_ratio} (expected {expected_ratio})"
                        )

            # Check file size
            size_mb = asset.get("size_mb", 0)
            if size_mb > spec["max_size_mb"]:
                asset_errors.append(
                    f"File size too large: {size_mb}MB (max: {spec['max_size_mb']}MB)"
                )

            if asset_errors:
                validation_results["invalid_assets"].append({
                    "asset": asset,
                    "errors": asset_errors
                })
            else:
                validation_results["valid_assets"].append(asset)
                if asset_warnings:
                    validation_results["warnings"].extend(asset_warnings)

        return {
            "validation_results": validation_results,
            "missing_assets": missing_assets,
            "size_warnings": size_warnings,
            "spec_used": spec
        }

    def generate_asset_list(self, post_folder: Optional[str] = None, post_type: str = "post") -> Dict[str, Any]:
        """
        Generate required asset list based on post type

        Args:
            post_folder: Post folder path (optional if set in __init__)
            post_type: Post type (post, carousel, reel, story)

        Returns:
            {
                "required_assets": List[str],
                "current_assets": List[str],
                "missing_assets": List[str]
            }
        """
        scan_result = self.scan_assets(post_folder)
        current_assets = [asset["name"] for asset in scan_result.get("asset_list", [])]

        # Generate required assets based on post type
        required_assets = []

        if post_type == "post":
            required_assets = ["cover.jpg"]
        elif post_type == "carousel":
            # Carousel typically needs 2-10 slides
            required_assets = [f"slide_{i:02d}.jpg" for i in range(1, 8)]
        elif post_type == "reel":
            required_assets = ["reel.mp4", "cover.jpg"]
        elif post_type == "story":
            required_assets = ["story_01.jpg", "story_02.jpg", "story_03.jpg"]

        missing_assets = [asset for asset in required_assets if asset not in current_assets]

        return {
            "required_assets": required_assets,
            "current_assets": current_assets,
            "missing_assets": missing_assets
        }

