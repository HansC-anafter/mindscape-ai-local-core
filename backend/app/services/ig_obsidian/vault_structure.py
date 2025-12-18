"""
Vault structure management for IG + Obsidian integration

Manages standard Vault folder structure for IG Post content workflow.
Supports initialization, validation, and content scanning.
"""
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class VaultStructureManager:
    """
    Manages Obsidian Vault structure for IG Post workflow

    Handles:
    - Standard folder structure initialization
    - Structure validation
    - Content scanning and indexing
    """

    # Standard folder structure (shared across all content types)
    STANDARD_FOLDERS = [
        "10-Ideas",
        "30-Assets",
        "40-Series",
        "50-Playbooks",
        "60-Reviews",
        "70-Metrics",
        "90-Export"
    ]

    # IG Post specific folder
    IG_POSTS_FOLDER = "20-Posts"

    # Future platform folders (for reference)
    FUTURE_PLATFORM_FOLDERS = [
        "21-Twitter",
        "22-LinkedIn",
        "23-Blog"
    ]

    def __init__(self, vault_path: str):
        """
        Initialize Vault Structure Manager

        Args:
            vault_path: Path to Obsidian Vault
        """
        self.vault_path = Path(vault_path).expanduser().resolve()

        if not self.vault_path.exists():
            raise ValueError(f"Vault path does not exist: {vault_path}")

        if not self.vault_path.is_dir():
            raise ValueError(f"Vault path is not a directory: {vault_path}")

    def get_all_required_folders(self) -> List[str]:
        """
        Get all required folders including IG Post folder

        Returns:
            List of required folder names
        """
        return self.STANDARD_FOLDERS + [self.IG_POSTS_FOLDER]

    def init_structure(self, create_missing: bool = True) -> Dict[str, Any]:
        """
        Initialize standard Vault structure

        Args:
            create_missing: Whether to create missing folders

        Returns:
            Dictionary with structure status and created folders
        """
        created_folders = []
        missing_folders = []

        required_folders = self.get_all_required_folders()

        for folder_name in required_folders:
            folder_path = self.vault_path / folder_name

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
        Validate Vault structure

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
            "vault_path": str(self.vault_path)
        }

    def scan_content(self) -> Dict[str, Any]:
        """
        Scan and index Vault content

        Returns:
            Dictionary with content index
        """
        content_index = {
            "posts": [],
            "series": [],
            "ideas": [],
            "timestamp": datetime.now().isoformat()
        }

        # Scan IG Posts folder
        posts_folder = self.vault_path / self.IG_POSTS_FOLDER
        if posts_folder.exists() and posts_folder.is_dir():
            for post_dir in posts_folder.iterdir():
                if post_dir.is_dir():
                    post_md = post_dir / "post.md"
                    if post_md.exists():
                        content_index["posts"].append({
                            "path": str(post_dir.relative_to(self.vault_path)),
                            "name": post_dir.name,
                            "has_post_md": True,
                            "has_assets": (post_dir / "assets").exists(),
                            "has_export": (post_dir / "export").exists()
                        })

        # Scan Series folder
        series_folder = self.vault_path / "40-Series"
        if series_folder.exists() and series_folder.is_dir():
            for series_file in series_folder.glob("*.md"):
                content_index["series"].append({
                    "path": str(series_file.relative_to(self.vault_path)),
                    "name": series_file.stem
                })

        # Scan Ideas folder
        ideas_folder = self.vault_path / "10-Ideas"
        if ideas_folder.exists() and ideas_folder.is_dir():
            for idea_file in ideas_folder.glob("*.md"):
                content_index["ideas"].append({
                    "path": str(idea_file.relative_to(self.vault_path)),
                    "name": idea_file.stem
                })

        return {
            "content_index": content_index,
            "post_count": len(content_index["posts"]),
            "series_count": len(content_index["series"]),
            "idea_count": len(content_index["ideas"]),
            "vault_path": str(self.vault_path)
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
        return self.vault_path / self.IG_POSTS_FOLDER / folder_name

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


