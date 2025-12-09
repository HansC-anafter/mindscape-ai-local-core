"""
Local file system storage implementation for Sandbox system
"""

import os
import shutil
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging

from backend.app.services.sandbox.storage.base_storage import BaseStorage

logger = logging.getLogger(__name__)


class LocalStorage(BaseStorage):
    """
    Local file system storage implementation

    Stores sandbox files in local filesystem with version management.
    Directory structure:
        {base_path}/
            versions/
                v1/
                    {files}
                v2/
                    {files}
            current/
                {files}
    """

    def __init__(self, base_path: Path):
        """
        Initialize local storage

        Args:
            base_path: Base directory path for sandbox storage
        """
        self.base_path = Path(base_path)
        self.versions_path = self.base_path / "versions"
        self.current_path = self.base_path / "current"

        self.base_path.mkdir(parents=True, exist_ok=True)
        self.versions_path.mkdir(parents=True, exist_ok=True)
        self.current_path.mkdir(parents=True, exist_ok=True)

    def _get_version_path(self, version: Optional[str]) -> Path:
        """
        Get path for version directory

        Args:
            version: Version identifier or None for current

        Returns:
            Path to version directory
        """
        if version:
            return self.versions_path / version
        return self.current_path

    def _normalize_path(self, file_path: str) -> Path:
        """
        Normalize file path to prevent directory traversal

        Args:
            file_path: Relative file path

        Returns:
            Normalized Path object (relative path, not absolute)

        Raises:
            ValueError: If path is invalid or contains directory traversal
        """
        # Remove leading slashes and normalize
        clean_path = file_path.lstrip("/\\")
        normalized = Path(clean_path)
        
        # Check for directory traversal attempts
        if ".." in str(normalized):
            raise ValueError(f"Invalid path: {file_path}")
        
        return normalized

    async def read_file(self, file_path: str, version: Optional[str] = None) -> str:
        """Read file content from storage"""
        version_path = self._get_version_path(version)
        full_path = version_path / self._normalize_path(file_path)

        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        try:
            with open(full_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logger.error(f"Failed to read file {file_path}: {e}")
            raise IOError(f"Cannot read file: {file_path}") from e

    async def write_file(
        self,
        file_path: str,
        content: str,
        version: Optional[str] = None
    ) -> bool:
        """Write file content to storage"""
        version_path = self._get_version_path(version)
        full_path = version_path / self._normalize_path(file_path)

        try:
            full_path.parent.mkdir(parents=True, exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)
            return True
        except Exception as e:
            logger.error(f"Failed to write file {file_path}: {e}")
            return False

    async def delete_file(self, file_path: str, version: Optional[str] = None) -> bool:
        """Delete file from storage"""
        version_path = self._get_version_path(version)
        full_path = version_path / self._normalize_path(file_path)

        try:
            if full_path.exists():
                full_path.unlink()
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to delete file {file_path}: {e}")
            return False

    async def list_files(
        self,
        directory: str = "",
        version: Optional[str] = None,
        recursive: bool = True
    ) -> List[Dict[str, Any]]:
        """List files in directory"""
        version_path = self._get_version_path(version)
        search_path = version_path / self._normalize_path(directory) if directory else version_path

        if not search_path.exists():
            return []

        files = []
        try:
            if recursive:
                for root, dirs, filenames in os.walk(search_path):
                    for filename in filenames:
                        file_path = Path(root) / filename
                        rel_path = file_path.relative_to(version_path)
                        stat = file_path.stat()
                        files.append({
                            "path": str(rel_path),
                            "size": stat.st_size,
                            "modified": stat.st_mtime,
                            "type": "file"
                        })
            else:
                for item in search_path.iterdir():
                    if item.is_file():
                        rel_path = item.relative_to(version_path)
                        stat = item.stat()
                        files.append({
                            "path": str(rel_path),
                            "size": stat.st_size,
                            "modified": stat.st_mtime,
                            "type": "file"
                        })
        except Exception as e:
            logger.error(f"Failed to list files in {directory}: {e}")
            return []

        return files

    async def file_exists(self, file_path: str, version: Optional[str] = None) -> bool:
        """Check if file exists"""
        version_path = self._get_version_path(version)
        full_path = version_path / self._normalize_path(file_path)
        return full_path.exists()

    async def create_version(self, version: str, source_version: Optional[str] = None) -> bool:
        """Create a new version snapshot"""
        version_path = self.versions_path / version

        try:
            if source_version:
                source_path = self.versions_path / source_version
                if source_path.exists():
                    shutil.copytree(source_path, version_path)
                else:
                    version_path.mkdir(parents=True, exist_ok=True)
            else:
                version_path.mkdir(parents=True, exist_ok=True)
                if self.current_path.exists():
                    shutil.copytree(self.current_path, version_path, dirs_exist_ok=True)

            metadata_path = version_path / ".metadata.json"
            metadata = {
                "created_at": datetime.now().isoformat(),
                "source_version": source_version,
            }
            import json
            with open(metadata_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f)

            return True
        except Exception as e:
            logger.error(f"Failed to create version {version}: {e}")
            return False

    async def list_versions(self) -> List[str]:
        """List all available versions"""
        versions = []
        try:
            if self.versions_path.exists():
                for item in self.versions_path.iterdir():
                    if item.is_dir() and not item.name.startswith("."):
                        versions.append(item.name)
            versions.sort()
        except Exception as e:
            logger.error(f"Failed to list versions: {e}")
        return versions

    async def get_version_metadata(self, version: str) -> Optional[Dict[str, Any]]:
        """Get metadata for a specific version"""
        version_path = self.versions_path / version
        if not version_path.exists():
            return None

        metadata_path = version_path / ".metadata.json"
        metadata = {}

        if metadata_path.exists():
            try:
                import json
                with open(metadata_path, "r", encoding="utf-8") as f:
                    metadata = json.load(f)
            except Exception as e:
                logger.error(f"Failed to read version metadata: {e}")

        file_count = 0
        total_size = 0
        try:
            for root, dirs, filenames in os.walk(version_path):
                for filename in filenames:
                    if filename != ".metadata.json":
                        file_path = Path(root) / filename
                        file_count += 1
                        total_size += file_path.stat().st_size
        except Exception as e:
            logger.error(f"Failed to calculate version stats: {e}")

        metadata.update({
            "file_count": file_count,
            "total_size": total_size,
        })

        return metadata

    async def switch_version(self, version: str) -> bool:
        """
        Switch current version to a specific version

        Copies all files from the specified version to the current directory.

        Args:
            version: Version identifier to switch to

        Returns:
            True if switch successful, False otherwise
        """
        version_path = self.versions_path / version
        if not version_path.exists():
            return False

        try:
            if self.current_path.exists():
                shutil.rmtree(self.current_path)
            self.current_path.mkdir(parents=True, exist_ok=True)

            shutil.copytree(version_path, self.current_path, dirs_exist_ok=True)
            return True
        except Exception as e:
            logger.error(f"Failed to switch version: {e}")
            return False

