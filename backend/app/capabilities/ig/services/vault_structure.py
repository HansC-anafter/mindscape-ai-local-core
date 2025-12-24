"""
Workspace structure management for IG capability

Manages standard workspace folder structure for IG Post content workflow.
Supports initialization, validation, and content scanning.
"""
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

from capabilities.ig.services.workspace_storage import WorkspaceStorage

logger = logging.getLogger(__name__)


class WorkspaceStructureManager:
    """
    Manages workspace structure for IG Post workflow

    Handles:
    - Standard folder structure initialization
    - Structure validation
    - Content scanning and indexing
    """

    # Standard folder structure (mapped to WorkspaceStorage paths)
    STANDARD_FOLDERS = {
        "ideas": "ideas",  # Maps to capability root/ideas
        "assets": "assets",  # Maps to capability root/assets
        "series": "series",  # Maps to storage.get_series_path()
        "templates": "templates",  # Maps to storage.get_templates_path()
        "reviews": "reviews",  # Maps to capability root/reviews
        "metrics": "metrics",  # Maps to capability root/metrics
        "export": "export"  # Maps to capability root/export
    }

    def __init__(self, workspace_storage: WorkspaceStorage):
        """
        Initialize Workspace Structure Manager

        Args:
            workspace_storage: WorkspaceStorage instance
        """
        self.storage = workspace_storage
        self.capability_root = self.storage.get_capability_root()

    def get_all_required_folders(self) -> List[str]:
        """
        Get all required folders

        Returns:
            List of required folder names
        """
        return list(self.STANDARD_FOLDERS.keys()) + ["posts"]

    def _get_folder_path(self, folder_name: str) -> Path:
        """
        Get path for a folder name

        Args:
            folder_name: Folder name

        Returns:
            Path to folder
        """
        if folder_name == "posts":
            return self.storage.get_posts_path()
        elif folder_name == "series":
            return self.storage.get_series_path()
        elif folder_name == "templates":
            return self.storage.get_templates_path()
        elif folder_name in self.STANDARD_FOLDERS:
            return self.capability_root / self.STANDARD_FOLDERS[folder_name]
        else:
            return self.capability_root / folder_name

    def init_structure(self, create_missing: bool = True) -> Dict[str, Any]:
        """
        Initialize standard workspace structure

        Args:
            create_missing: Whether to create missing folders

        Returns:
            Dictionary with structure status and created folders
        """
        created_folders = []
        missing_folders = []

        required_folders = self.get_all_required_folders()

        for folder_name in required_folders:
            folder_path = self._get_folder_path(folder_name)

            if folder_path.exists():
                if not folder_path.is_dir():
                    logger.warning(f"Path exists but is not a directory: {folder_path}")
                    missing_folders.append(folder_name)
                else:
                    logger.debug(f"Folder already exists: {folder_path}")
            else:
                if create_missing:
                    try:
                        folder_path.mkdir(parents=True, exist_ok=True)
                        created_folders.append(folder_name)
                        logger.info(f"Created folder: {folder_path}")
                    except Exception as e:
                        logger.error(f"Failed to create folder {folder_path}: {e}")
                        missing_folders.append(folder_name)
                else:
                    missing_folders.append(folder_name)

        is_valid = len(missing_folders) == 0

        return {
            "is_valid": is_valid,
            "created_folders": created_folders,
            "missing_folders": missing_folders,
            "structure_status": "initialized" if is_valid else "incomplete"
        }

    def validate_structure(self, create_missing: bool = False) -> Dict[str, Any]:
        """
        Validate workspace structure

        Args:
            create_missing: Whether to create missing folders if validation fails

        Returns:
            Dictionary with validation results
        """
        result = self.init_structure(create_missing=create_missing)

        return {
            "is_valid": result["is_valid"],
            "missing_folders": result["missing_folders"],
            "structure_status": result["structure_status"],
            "workspace_root": str(self.capability_root)
        }

    def scan_content(self) -> Dict[str, Any]:
        """
        Scan and index workspace content

        Returns:
            Dictionary with content index
        """
        content_index = {
            "posts": [],
            "series": [],
            "ideas": [],
            "timestamp": datetime.now().isoformat()
        }

        # Scan Posts folder
        posts_folder = self.storage.get_posts_path()
        if posts_folder.exists() and posts_folder.is_dir():
            for post_dir in posts_folder.iterdir():
                if post_dir.is_dir():
                    post_md = post_dir / "post.md"
                    if post_md.exists():
                        content_index["posts"].append({
                            "path": str(post_dir.relative_to(self.capability_root)),
                            "name": post_dir.name,
                            "has_post_md": True,
                            "has_assets": (post_dir / "assets").exists(),
                            "has_export": (post_dir / "export").exists()
                        })

        # Scan Series folder
        series_folder = self.storage.get_series_path()
        if series_folder.exists() and series_folder.is_dir():
            for series_file in series_folder.glob("*.json"):
                content_index["series"].append({
                    "path": str(series_file.relative_to(self.capability_root)),
                    "name": series_file.stem
                })

        # Scan Ideas folder
        ideas_folder = self._get_folder_path("ideas")
        if ideas_folder.exists() and ideas_folder.is_dir():
            for idea_file in ideas_folder.glob("*.md"):
                content_index["ideas"].append({
                    "path": str(idea_file.relative_to(self.capability_root)),
                    "name": idea_file.stem
                })

        return {
            "content_index": content_index,
            "post_count": len(content_index["posts"]),
            "series_count": len(content_index["series"]),
            "idea_count": len(content_index["ideas"]),
            "workspace_root": str(self.capability_root)
        }

    def get_post_folder_path(self, date_str: str, slug: str) -> Path:
        """
        Get post folder path based on naming convention

        Args:
            date_str: Date string in format YYYY-MM-DD
            slug: Post slug (brand-topic format)

        Returns:
            Path to post folder
        """
        folder_name = f"{date_str}_{slug}"
        return self.storage.get_posts_path() / folder_name

    def create_post_folder(self, date_str: str, slug: str) -> Path:
        """
        Create post folder with standard structure

        Args:
            date_str: Date string in format YYYY-MM-DD
            slug: Post slug (brand-topic format)

        Returns:
            Path to created post folder
        """
        post_folder = self.get_post_folder_path(date_str, slug)

        if post_folder.exists():
            logger.warning(f"Post folder already exists: {post_folder}")
            return post_folder

        post_folder.mkdir(parents=True, exist_ok=True)
        (post_folder / "assets").mkdir(exist_ok=True)
        (post_folder / "export").mkdir(exist_ok=True)

        logger.info(f"Created post folder: {post_folder}")
        return post_folder

